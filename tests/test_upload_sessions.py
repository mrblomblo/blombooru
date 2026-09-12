import asyncio
import io
import json
from pathlib import Path
import time
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from backend.app.config import settings
from backend.app.enums import FileTypeEnum, RatingEnum, TagCategoryEnum
from backend.app.models import Album, Media, Tag, TagAlias, User
from backend.app.routes.media import preview_or_create_tags
from backend.app.routes.uploads import (
    BulkUpdateRequest,
    add_untracked_file_to_session,
    bulk_update_staged_items,
    cleanup_upload_sessions,
    commit_upload_session,
    create_upload_session,
    get_pending_entities,
    get_staged_item_file,
    get_staged_item_thumbnail,
    get_upload_session,
    update_pending_tag,
    update_staged_item,
    upload_files_to_session,
)
from backend.app.schemas import (
    PendingTagUpdate,
    UploadSessionAddUntrackedRequest,
    UploadSessionItemUpdate,
)
from tests.backup_test_base import BackupTestBase, make_dummy_jpeg

class TestUploadSessions(BackupTestBase):
    def setUp(self):
        super().setUp()
        self.admin_user = User(id=1, username="admin", password_hash="hash")
        self.cache_dir = self.tmp_path / "media" / "cache"
        self.upload_sessions_dir = self.cache_dir / "upload-sessions"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.upload_sessions_dir.mkdir(parents=True, exist_ok=True)

        self.old_cache = settings.CACHE_DIR
        settings.CACHE_DIR = self.cache_dir

        # Point UPLOAD_SESSIONS_DIR to the isolated test directory
        import backend.app.routes.uploads as uploads_module
        self.old_module_sessions_dir = uploads_module.UPLOAD_SESSIONS_DIR
        uploads_module.UPLOAD_SESSIONS_DIR = self.upload_sessions_dir

    def tearDown(self):
        import backend.app.routes.uploads as uploads_module
        uploads_module.UPLOAD_SESSIONS_DIR = self.old_module_sessions_dir
        settings.CACHE_DIR = self.old_cache
        super().tearDown()

    def test_preview_or_create_tags_dry_run(self):
        """Test preview_or_create_tags returns proposed tags without creating DB rows in dry_run mode."""
        existing_tag = Tag(name="cat", category="general", post_count=5)
        self.db.add(existing_tag)
        self.db.commit()

        # Alias: "feline" -> "cat"
        alias = TagAlias(alias_name="feline", target_tag_id=existing_tag.id)
        self.db.add(alias)
        self.db.commit()

        # 1. Dry run with existing tag, alias, and completely new tag
        tag_names = ["feline", "dog", "artist_bob"]
        category_hints = {"artist_bob": "artist"}

        proposed = preview_or_create_tags(
            self.db,
            tag_names,
            category_hints=category_hints,
            expand=True,
            dry_run=True,
        )

        # Ensure no new tags were inserted into the DB
        all_db_tags = self.db.query(Tag).all()
        self.assertEqual(len(all_db_tags), 1)
        self.assertEqual(all_db_tags[0].name, "cat")

        # Verify proposed results
        prop_map = {p.name: p for p in proposed}
        self.assertIn("cat", prop_map)
        self.assertFalse(prop_map["cat"].is_new)
        self.assertEqual(prop_map["cat"].category, "general")

        self.assertIn("dog", prop_map)
        self.assertTrue(prop_map["dog"].is_new)
        self.assertEqual(prop_map["dog"].category, "general")

        self.assertIn("artist_bob", prop_map)
        self.assertTrue(prop_map["artist_bob"].is_new)
        self.assertEqual(prop_map["artist_bob"].category, "artist")

    def test_upload_session_file_staging_and_duplicate_detection(self):
        """Test creating session, staging file, and detecting duplicate hash against DB."""
        jpeg_bytes = make_dummy_jpeg()

        # Pre-seed duplicate in DB
        import hashlib
        h = hashlib.md5(jpeg_bytes).hexdigest()
        existing_media = Media(
            filename="existing_pic.jpg",
            path="original/existing_pic.jpg",
            hash=h,
            file_type=FileTypeEnum.image,
            file_size=len(jpeg_bytes),
            rating=RatingEnum.safe,
        )
        self.db.add(existing_media)
        self.db.commit()

        # Create session
        session_res = asyncio.run(create_upload_session(current_user=self.admin_user))
        session_id = session_res["session_id"]

        # Upload duplicate file to session - should be rejected with 409
        file_obj = UploadFile(filename="new_upload.jpg", file=io.BytesIO(jpeg_bytes))
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(upload_files_to_session(
                session_id=session_id,
                file=file_obj,
                base_rating="questionable",
                base_tags="landscape mountain",
                current_user=self.admin_user,
                db=self.db,
            ))
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("error_duplicate", ctx.exception.detail)

    def test_new_tag_conflicting_assigned_category_harmonization(self):
        """Test that uploading a new media with conflicting category hints re-assigns new tags to the category in the upload queue."""
        session_res = asyncio.run(create_upload_session(current_user=self.admin_user))
        session_id = session_res["session_id"]

        # Item 1 with new tag "custom_artist" assigned to "artist" category
        jpeg1 = make_dummy_jpeg()
        f1 = UploadFile(filename="pic1.jpg", file=io.BytesIO(jpeg1))
        item1 = asyncio.run(upload_files_to_session(
            session_id=session_id,
            file=f1,
            base_tags="custom_artist",
            category_hints=json.dumps({"custom_artist": "artist"}),
            user_assigned_tags=json.dumps(["custom_artist"]),
            current_user=self.admin_user,
            db=self.db,
        ))
        self.assertEqual(item1["tags"][0]["category"], "artist")
        self.assertTrue(item1["tags"][0]["user_assigned"])

        # Item 2 uploaded via booru importer where "custom_artist" is tagged as "general" or "character"
        # Dummy jpeg with different bytes
        import struct
        jpeg2 = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\xff\xc0\x00\x0b\x08\x00\x02\x00\x02\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"
        f2 = UploadFile(filename="pic2.jpg", file=io.BytesIO(jpeg2))
        item2 = asyncio.run(upload_files_to_session(
            session_id=session_id,
            file=f2,
            base_tags="custom_artist",
            category_hints=json.dumps({"custom_artist": "general"}),
            current_user=self.admin_user,
            db=self.db,
        ))
        # Category for custom_artist on item2 should be harmonized to "artist"
        self.assertEqual(item2["tags"][0]["category"], "artist")
        self.assertTrue(item2["tags"][0]["user_assigned"])

    def test_item_update_and_pending_entities_aggregation(self):
        """Test modifying item tags and aggregating pending entities across the session."""
        import json
        session_res = asyncio.run(create_upload_session(current_user=self.admin_user))
        session_id = session_res["session_id"]

        # Upload item 1 with imported metadata tags
        jpeg1 = make_dummy_jpeg()
        f1 = UploadFile(filename="photo1.jpg", file=io.BytesIO(jpeg1))
        item1 = asyncio.run(upload_files_to_session(
            session_id=session_id,
            file=f1,
            base_tags="sky sunset",
            category_hints=json.dumps({"sky": "general", "sunset": "general"}),
            current_user=self.admin_user,
            db=self.db,
        ))

        # Upload item 2 with imported metadata tags
        jpeg2 = make_dummy_jpeg()
        f2 = UploadFile(filename="photo2.jpg", file=io.BytesIO(jpeg2 + b"salt"))
        item2 = asyncio.run(upload_files_to_session(
            session_id=session_id,
            file=f2,
            base_tags="sunset ocean",
            category_hints=json.dumps({"sunset": "general", "ocean": "general"}),
            current_user=self.admin_user,
            db=self.db,
        ))

        # Get pending entities: "sky", "sunset", "ocean" are all new unconfirmed metadata tags
        pending = asyncio.run(get_pending_entities(session_id=session_id, current_user=self.admin_user))
        pending_tag_map = {t.name: t for t in pending.pending_tags}

        self.assertEqual(len(pending.pending_tags), 3)
        self.assertIn("sunset", pending_tag_map)
        # sunset is used by both item 1 and item 2
        self.assertEqual(len(pending_tag_map["sunset"].used_by), 2)
        self.assertIn(item1["item_id"], pending_tag_map["sunset"].used_by)
        self.assertIn(item2["item_id"], pending_tag_map["sunset"].used_by)

        # Global update on pending tag: rename "sunset" to "dusk" and change category to "meta"
        asyncio.run(update_pending_tag(
            session_id=session_id,
            tag_name="sunset",
            update=PendingTagUpdate(new_name="dusk", category=TagCategoryEnum.meta),
            current_user=self.admin_user,
            db=self.db,
        ))

        # Verify session state reflects global update on both items
        session_state = asyncio.run(get_upload_session(session_id=session_id, current_user=self.admin_user))
        for it in session_state["items"]:
            tag_names = [t["name"] for t in it["tags"]]
            self.assertNotIn("sunset", tag_names)
            self.assertIn("dusk", tag_names)

        # Test bulk update with string list tags, description, and album IDs
        album = Album(name="Test Album")
        self.db.add(album)
        self.db.commit()

        bulk_res = asyncio.run(bulk_update_staged_items(
            session_id=session_id,
            req=BulkUpdateRequest(
                item_ids=[item1["item_id"], item2["item_id"]],
                add_tags=["blomblo"],
                rating=RatingEnum.explicit,
                description="Bulk description",
                add_album_ids=[album.id],
            ),
            current_user=self.admin_user,
            db=self.db,
        ))
        self.assertEqual(bulk_res["updated_count"], 2)
        for it in bulk_res["items"]:
            tag_names = [t["name"] for t in it["tags"]]
            self.assertIn("blomblo", tag_names)
            self.assertEqual(it["rating"], "explicit")
            self.assertEqual(it["description"], "Bulk description")
            self.assertIn(album.id, it["album_ids"])

    def test_session_commit_creates_media_tags_and_albums(self):
        """Test atomic commit creates confirmed tags, albums, media records, and cleans staging directory."""
        session_res = asyncio.run(create_upload_session(current_user=self.admin_user))
        session_id = session_res["session_id"]

        jpeg_bytes = make_dummy_jpeg()
        f = UploadFile(filename="cool_art.jpg", file=io.BytesIO(jpeg_bytes))
        item = asyncio.run(upload_files_to_session(
            session_id=session_id,
            file=f,
            base_tags="artist_alice masterpiece",
            current_user=self.admin_user,
            db=self.db,
        ))

        # Update item with a suggested album path
        asyncio.run(update_staged_item(
            session_id=session_id,
            item_id=item["item_id"],
            update=UploadSessionItemUpdate(
                suggested_album_path="Artworks/2026",
                source="https://example.com/art/123",
                description="Test description",
            ),
            current_user=self.admin_user,
            db=self.db,
        ))

        # Commit session
        commit_res = asyncio.run(commit_upload_session(
            session_id=session_id,
            current_user=self.admin_user,
            db=self.db,
        ))

        self.assertEqual(commit_res.total_created, 1)
        self.assertEqual(commit_res.total_failed, 0)

        # Verify Media created in DB
        saved_media = self.db.query(Media).filter(Media.id == commit_res.results[0].media_id).first()
        self.assertIsNotNone(saved_media)
        self.assertEqual(saved_media.source, "https://example.com/art/123")
        self.assertEqual(saved_media.description, "Test description")

        # Verify tags created and linked
        tag_names = {t.name for t in saved_media.tags}
        self.assertIn("artist_alice", tag_names)
        self.assertIn("masterpiece", tag_names)

        # Verify album hierarchy created and linked
        parent_album = self.db.query(Album).filter(Album.name == "Artworks").first()
        child_album = self.db.query(Album).filter(Album.name == "2026").first()
        self.assertIsNotNone(parent_album)
        self.assertIsNotNone(child_album)
        self.assertIn(child_album, parent_album.children)
        self.assertIn(child_album, saved_media.albums)

        # Verify session staging directory was cleaned up
        session_dir = self.upload_sessions_dir / session_id
        self.assertFalse(session_dir.exists())

    def test_cleanup_upload_sessions_removes_old_dirs(self):
        """Test cleanup_upload_sessions sweeps session directories older than max_age_seconds."""
        old_session_dir = self.upload_sessions_dir / "old-session"
        old_session_dir.mkdir(parents=True, exist_ok=True)
        meta_file = old_session_dir / "meta.json"
        meta_file.write_text('{"session_id": "old-session"}')

        # Set mtime to 2 hours ago
        two_hours_ago = time.time() - 7200
        import os
        os.utime(str(meta_file), (two_hours_ago, two_hours_ago))
        os.utime(str(old_session_dir), (two_hours_ago, two_hours_ago))

        # Fresh session
        fresh_session_dir = self.upload_sessions_dir / "fresh-session"
        fresh_session_dir.mkdir(parents=True, exist_ok=True)

        cleanup_upload_sessions(max_age_seconds=3600)

        self.assertFalse(old_session_dir.exists())
        self.assertTrue(fresh_session_dir.exists())

    def test_session_commit_duplicate_skipping(self):
        """Test that duplicate media items are skipped on commit and their new tags are not created."""
        session_res = asyncio.run(create_upload_session(current_user=self.admin_user))
        session_id = session_res["session_id"]

        # Item 1: Valid new image with unique tag
        jpeg1 = make_dummy_jpeg()
        f1 = UploadFile(filename="unique_pic.jpg", file=io.BytesIO(jpeg1))
        item1 = asyncio.run(upload_files_to_session(
            session_id=session_id,
            file=f1,
            base_tags="fresh_tag",
            current_user=self.admin_user,
            db=self.db,
        ))

        # Item 2: Image staged, but then inserted into DB beforehand to simulate duplicate at commit time
        jpeg2 = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\xff\xc0\x00\x0b\x08\x00\x02\x00\x02\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"
        f2 = UploadFile(filename="duplicate_candidate.jpg", file=io.BytesIO(jpeg2))
        item2 = asyncio.run(upload_files_to_session(
            session_id=session_id,
            file=f2,
            base_tags="unwanted_duplicate_tag",
            current_user=self.admin_user,
            db=self.db,
        ))

        # Insert a media record with item2's hash into DB right before commit
        import hashlib
        h2 = hashlib.md5(jpeg2).hexdigest()
        existing_dup = Media(
            filename="already_in_db.jpg",
            path="original/already_in_db.jpg",
            hash=h2,
            file_type=FileTypeEnum.image,
            file_size=len(jpeg2),
            rating=RatingEnum.safe,
        )
        self.db.add(existing_dup)
        self.db.commit()

        # Commit session
        commit_res = asyncio.run(commit_upload_session(
            session_id=session_id,
            current_user=self.admin_user,
            db=self.db,
        ))

        self.assertEqual(commit_res.total_created, 1)
        self.assertEqual(commit_res.total_duplicates, 1)
        self.assertEqual(commit_res.total_failed, 0)

        # fresh_tag should exist in DB, unwanted_duplicate_tag should NOT exist
        fresh_tag = self.db.query(Tag).filter(Tag.name == "fresh_tag").first()
        unwanted_tag = self.db.query(Tag).filter(Tag.name == "unwanted_duplicate_tag").first()
        self.assertIsNotNone(fresh_tag)
        self.assertIsNone(unwanted_tag)

    def test_add_untracked_file_to_session_and_commit(self):
        """Test staging and committing an untracked file residing on server disk in ORIGINAL_DIR."""
        # Create an untracked file in settings.ORIGINAL_DIR
        untracked_file = settings.ORIGINAL_DIR / "untracked_sample.jpg"
        jpeg_data = make_dummy_jpeg()
        untracked_file.write_bytes(jpeg_data)

        session_res = asyncio.run(create_upload_session(current_user=self.admin_user))
        session_id = session_res["session_id"]

        req = UploadSessionAddUntrackedRequest(
            file_path=str(untracked_file),
            base_tags="scanned_tag nature",
            base_rating="safe",
            base_source="camera_local",
        )

        item = asyncio.run(add_untracked_file_to_session(
            session_id=session_id,
            request=req,
            current_user=self.admin_user,
            db=self.db,
        ))

        self.assertEqual(item["filename"], "untracked_sample.jpg")
        self.assertTrue(item["is_untracked"])
        self.assertEqual(item["source_path"], str(untracked_file))
        self.assertIsNone(item["staged_filename"])
        self.assertEqual(item["file_size"], len(jpeg_data))

        # Check thumbnail and file endpoints serve correctly
        thumb_res = asyncio.run(get_staged_item_thumbnail(session_id=session_id, item_id=item["item_id"]))
        self.assertTrue(Path(thumb_res.path).exists())

        file_res = asyncio.run(get_staged_item_file(session_id=session_id, item_id=item["item_id"]))
        self.assertEqual(Path(file_res.path).resolve(), untracked_file.resolve())

        # Commit session
        commit_res = asyncio.run(commit_upload_session(
            session_id=session_id,
            current_user=self.admin_user,
            db=self.db,
        ))

        self.assertEqual(commit_res.total_created, 1)
        self.assertEqual(commit_res.total_duplicates, 0)
        self.assertEqual(commit_res.total_failed, 0)

        media = self.db.query(Media).filter(Media.filename == "untracked_sample.jpg").first()
        self.assertIsNotNone(media)
        self.assertTrue(untracked_file.exists())  # File kept in place
        self.assertEqual(media.source, "camera_local")
        tag_names = {t.name for t in media.tags}
        self.assertIn("scanned_tag", tag_names)
        self.assertIn("nature", tag_names)

    def test_untracked_file_security_and_missing_paths(self):
        """Test access denied for paths outside ORIGINAL_DIR and 404 for nonexistent files."""
        session_res = asyncio.run(create_upload_session(current_user=self.admin_user))
        session_id = session_res["session_id"]

        # Path outside ORIGINAL_DIR
        outside_path = self.tmp_path / "outside.jpg"
        outside_path.write_bytes(make_dummy_jpeg())

        req_outside = UploadSessionAddUntrackedRequest(file_path=str(outside_path))
        with self.assertRaises(HTTPException) as cm:
            asyncio.run(add_untracked_file_to_session(
                session_id=session_id,
                request=req_outside,
                current_user=self.admin_user,
                db=self.db,
            ))
        self.assertEqual(cm.exception.status_code, 403)

        # Nonexistent path inside ORIGINAL_DIR
        nonexistent = settings.ORIGINAL_DIR / "does_not_exist.jpg"
        req_nonexistent = UploadSessionAddUntrackedRequest(file_path=str(nonexistent))
        with self.assertRaises(HTTPException) as cm:
            asyncio.run(add_untracked_file_to_session(
                session_id=session_id,
                request=req_nonexistent,
                current_user=self.admin_user,
                db=self.db,
            ))
        self.assertEqual(cm.exception.status_code, 404)
