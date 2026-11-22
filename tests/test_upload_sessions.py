import asyncio
from datetime import datetime, timezone
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
from tests.test_base import BackupTestBase, make_dummy_jpeg

class TestUploadSessions(BackupTestBase):
    def setUp(self):
        super().setUp()
        self.admin_user = User(id=1, username="admin", password_hash="hash")

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

    def test_upload_session_duplicate_within_session_and_cleanup(self):
        """Test that uploading a file identical to an already staged item in the same session is rejected with 409 error_duplicate_session and cleans up raw files."""
        session_res = asyncio.run(create_upload_session(current_user=self.admin_user))
        session_id = session_res["session_id"]
        session_dir = self.upload_sessions_dir / session_id

        # 1. Upload first unique file with sidecar
        jpeg1 = make_dummy_jpeg()
        sidecar1 = UploadFile(filename="pic1.json", file=io.BytesIO(b'{"tags": "one"}'))
        f1 = UploadFile(filename="pic1.jpg", file=io.BytesIO(jpeg1))
        item1 = asyncio.run(upload_files_to_session(
            session_id=session_id,
            file=f1,
            sidecar=sidecar1,
            base_tags="first_item",
            current_user=self.admin_user,
            db=self.db,
        ))
        self.assertIsNotNone(item1)
        item1_id = item1["item_id"]
        self.assertTrue((session_dir / "raw" / f"{item1_id}_pic1.jpg").exists())
        self.assertTrue((session_dir / "raw" / f"{item1_id}_pic1.json").exists())

        # 2. Upload duplicate of first file with sidecar
        sidecar2 = UploadFile(filename="pic1_dup.json", file=io.BytesIO(b'{"tags": "dup"}'))
        f2 = UploadFile(filename="pic1_dup.jpg", file=io.BytesIO(jpeg1))
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(upload_files_to_session(
                session_id=session_id,
                file=f2,
                sidecar=sidecar2,
                base_tags="dup_item",
                current_user=self.admin_user,
                db=self.db,
            ))
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("error_duplicate_session", ctx.exception.detail)

        # Verify no orphan files were left for the rejected duplicate
        raw_files = list((session_dir / "raw").iterdir())
        self.assertEqual(len(raw_files), 2)  # only item1's image and sidecar
        self.assertTrue(all(p.name.startswith(f"{item1_id}_") for p in raw_files))

        # 3. Upload a second unique file (different bytes)
        jpeg2 = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\xff\xc0\x00\x0b\x08\x00\x02\x00\x02\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"
        f3 = UploadFile(filename="pic3.jpg", file=io.BytesIO(jpeg2))
        item3 = asyncio.run(upload_files_to_session(
            session_id=session_id,
            file=f3,
            base_tags="third_item",
            current_user=self.admin_user,
            db=self.db,
        ))
        self.assertIsNotNone(item3)

        # 4. Commit session - both unique items are committed successfully
        commit_res = asyncio.run(commit_upload_session(
            session_id=session_id,
            current_user=self.admin_user,
            db=self.db,
        ))
        self.assertEqual(commit_res.total_created, 2)
        self.assertEqual(commit_res.total_duplicates, 0)
        self.assertEqual(commit_res.total_failed, 0)

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

    def test_upload_session_auto_apply_ai_tags(self):
        """Test that AI metadata prompt tags are automatically applied when auto_apply_ai_tags is enabled."""
        from PIL import Image, PngImagePlugin
        from backend.app.models import TagImplication

        # Create tag implication: cat_ears -> animal_ears
        cat_tag = Tag(name="cat_ears", category="general", post_count=0)
        animal_tag = Tag(name="animal_ears", category="general", post_count=0)
        self.db.add_all([cat_tag, animal_tag])
        self.db.commit()

        implication = TagImplication(
            target_tags=[cat_tag],
            target_tag_patterns=[],
            implied_tags=[animal_tag],
        )
        self.db.add(implication)
        self.db.commit()

        # Create PNG with AI generation metadata
        info = PngImagePlugin.PngInfo()
        ai_parameters = "1girl, solo, cat_ears, blue_hair\nNegative prompt: worst quality, low quality\nSteps: 20, Sampler: Euler a, CFG scale: 7"
        info.add_text("parameters", ai_parameters)

        png_io = io.BytesIO()
        img = Image.new("RGB", (64, 64), color="blue")
        img.save(png_io, format="PNG", pnginfo=info)
        png_bytes = png_io.getvalue()

        # Case A: auto_apply_ai_tags = False (default)
        settings.file_settings["auto_apply_ai_tags"] = False
        session_res1 = asyncio.run(create_upload_session(current_user=self.admin_user))
        s_id1 = session_res1["session_id"]

        upload_file1 = UploadFile(
            file=io.BytesIO(png_bytes),
            filename="ai_sample_disabled.png",
            headers={"content-type": "image/png"},
        )
        item1 = asyncio.run(upload_files_to_session(
            session_id=s_id1,
            file=upload_file1,
            current_user=self.admin_user,
            db=self.db,
        ))
        item1_tag_names = {t["name"] for t in item1.get("tags", [])}
        self.assertEqual(len(item1_tag_names), 0)

        # Case B: auto_apply_ai_tags = True
        settings.file_settings["auto_apply_ai_tags"] = True
        session_res2 = asyncio.run(create_upload_session(current_user=self.admin_user))
        s_id2 = session_res2["session_id"]

        upload_file2 = UploadFile(
            file=io.BytesIO(png_bytes),
            filename="ai_sample_enabled.png",
            headers={"content-type": "image/png"},
        )
        item2 = asyncio.run(upload_files_to_session(
            session_id=s_id2,
            file=upload_file2,
            current_user=self.admin_user,
            db=self.db,
        ))
        item2_tag_names = {t["name"] for t in item2.get("tags", [])}
        self.assertIn("1girl", item2_tag_names)
        self.assertIn("solo", item2_tag_names)
        self.assertIn("cat_ears", item2_tag_names)
        self.assertIn("animal_ears", item2_tag_names)
        self.assertIn("blue_hair", item2_tag_names)

        # Commit and verify DB media tags
        commit_res = asyncio.run(commit_upload_session(
            session_id=s_id2,
            current_user=self.admin_user,
            db=self.db,
        ))
        self.assertEqual(commit_res.total_created, 1)

        media = self.db.query(Media).filter(Media.filename.like("%ai_sample_enabled%")).first()
        self.assertIsNotNone(media)
        db_tag_names = {t.name for t in media.tags}
        self.assertIn("1girl", db_tag_names)
        self.assertIn("solo", db_tag_names)
        self.assertIn("cat_ears", db_tag_names)
        self.assertIn("animal_ears", db_tag_names)
        self.assertIn("blue_hair", db_tag_names)

    def test_upload_session_media_type_tags(self):
        """Test that media_type_tags are automatically applied during staging."""
        settings.file_settings["media_type_tags"] = {
            "image": ["photo", "still_image"],
            "gif": ["animation"],
            "video": ["movie_clip"],
        }

        session_res = asyncio.run(create_upload_session(current_user=self.admin_user))
        s_id = session_res["session_id"]

        upload_file = UploadFile(
            file=io.BytesIO(make_dummy_jpeg()),
            filename="test_type_tags.jpg",
            headers={"content-type": "image/jpeg"},
        )
        item = asyncio.run(upload_files_to_session(
            session_id=s_id,
            file=upload_file,
            current_user=self.admin_user,
            db=self.db,
        ))
        staged_tags = {t["name"] for t in item.get("tags", [])}
        self.assertIn("photo", staged_tags)
        self.assertIn("still_image", staged_tags)

    def test_clear_suggested_album_path_single_and_bulk(self):
        """Test that passing suggested_album_path=None explicitly clears folder album assignment in single and bulk update."""
        session_res = asyncio.run(create_upload_session(current_user=self.admin_user))
        s_id = session_res["session_id"]

        f1 = UploadFile(filename="item1.jpg", file=io.BytesIO(make_dummy_jpeg()))
        f2 = UploadFile(filename="item2.jpg", file=io.BytesIO(make_dummy_jpeg() + b"extra"))

        item1 = asyncio.run(upload_files_to_session(
            session_id=s_id,
            file=f1,
            relative_path="FolderA/Sub/item1.jpg",
            current_user=self.admin_user,
            db=self.db,
        ))
        item2 = asyncio.run(upload_files_to_session(
            session_id=s_id,
            file=f2,
            relative_path="FolderA/Sub/item2.jpg",
            current_user=self.admin_user,
            db=self.db,
        ))

        self.assertEqual(item1.get("suggested_album_path"), "FolderA/Sub")
        self.assertEqual(item2.get("suggested_album_path"), "FolderA/Sub")

        # 1. Clear item1 suggested_album_path via update_staged_item
        updated1 = asyncio.run(update_staged_item(
            session_id=s_id,
            item_id=item1["item_id"],
            update=UploadSessionItemUpdate.model_validate({"suggested_album_path": None}),
            current_user=self.admin_user,
            db=self.db,
        ))
        self.assertIsNone(updated1.get("suggested_album_path"))
        self.assertIsNone(updated1.get("suggested_album_segments"))

        # Verify persisted in session meta
        sess = asyncio.run(get_upload_session(session_id=s_id, current_user=self.admin_user))
        items_map = {it["item_id"]: it for it in sess["items"]}
        self.assertIsNone(items_map[item1["item_id"]].get("suggested_album_path"))
        self.assertEqual(items_map[item2["item_id"]].get("suggested_album_path"), "FolderA/Sub")

        # 2. Re-assign suggested_album_path to item1, then clear both in bulk update
        asyncio.run(update_staged_item(
            session_id=s_id,
            item_id=item1["item_id"],
            update=UploadSessionItemUpdate.model_validate({"suggested_album_path": "FolderB"}),
            current_user=self.admin_user,
            db=self.db,
        ))

        bulk_res = asyncio.run(bulk_update_staged_items(
            session_id=s_id,
            req=BulkUpdateRequest.model_validate({
                "item_ids": [item1["item_id"], item2["item_id"]],
                "suggested_album_path": None,
            }),
            current_user=self.admin_user,
            db=self.db,
        ))
        for it in bulk_res["items"]:
            self.assertIsNone(it.get("suggested_album_path"))
            self.assertIsNone(it.get("suggested_album_segments"))

    def test_upload_session_commit_recalculates_album_metrics(self):
        """Test that committing items linked to albums or suggested album paths properly recalculates metrics for albums and their ancestors."""
        parent_album = Album(
            name="Artworks",
            cached_rating=RatingEnum.safe,
            cached_media_count=0,
            cached_direct_media_count=0,
        )
        self.db.add(parent_album)
        self.db.commit()
        self.db.refresh(parent_album)

        session_res = asyncio.run(create_upload_session(current_user=self.admin_user))
        s_id = session_res["session_id"]

        f1 = UploadFile(filename="pic1.jpg", file=io.BytesIO(make_dummy_jpeg()))
        f2 = UploadFile(filename="pic2.jpg", file=io.BytesIO(make_dummy_jpeg() + b"extra_unique_bytes"))

        item1 = asyncio.run(upload_files_to_session(
            session_id=s_id,
            file=f1,
            base_rating="explicit",
            base_album_ids=str(parent_album.id),
            current_user=self.admin_user,
            db=self.db,
        ))

        item2 = asyncio.run(upload_files_to_session(
            session_id=s_id,
            file=f2,
            base_rating="questionable",
            relative_path="Artworks/2026/pic2.jpg",
            current_user=self.admin_user,
            db=self.db,
        ))

        commit_res = asyncio.run(commit_upload_session(
            session_id=s_id,
            current_user=self.admin_user,
            db=self.db,
        ))
        self.assertEqual(commit_res.total_created, 2)
        self.assertEqual(commit_res.total_failed, 0)

        # Query albums from DB
        self.db.refresh(parent_album)
        child_album = self.db.query(Album).filter(Album.name == "2026").first()
        self.assertIsNotNone(child_album)

        # Verify child album metrics
        self.assertEqual(child_album.cached_direct_media_count, 1)
        self.assertEqual(child_album.cached_media_count, 1)
        self.assertEqual(child_album.cached_rating, RatingEnum.questionable)

        # Verify parent album metrics
        self.assertEqual(parent_album.cached_direct_media_count, 1)
        self.assertEqual(parent_album.cached_media_count, 2)
        self.assertEqual(parent_album.cached_rating, RatingEnum.explicit)

    def test_upload_media_direct_endpoint_custom_date(self):
        """Test POST /api/media/ with custom_date parameter sets custom_date and raises 422 on invalid date."""
        from backend.app.routes.media import upload_media
        from datetime import datetime, timezone

        # 1. Valid custom_date
        f1 = UploadFile(filename="valid_date.jpg", file=io.BytesIO(make_dummy_jpeg() + b"test_1"))
        res = asyncio.run(upload_media(
            file=f1,
            scanned_path=None,
            rating=RatingEnum.safe,
            tags="",
            album_ids=None,
            source=None,
            category_hints=None,
            description=None,
            custom_date="2021-06-15T12:00:00Z",
            current_user=self.admin_user,
            db=self.db,
        ))
        media = self.db.query(Media).filter(Media.id == res.id).first()
        self.assertIsNotNone(media)
        cdate = media.custom_date if media.custom_date.tzinfo else media.custom_date.replace(tzinfo=timezone.utc)
        self.assertEqual(cdate, datetime(2021, 6, 15, 12, 0, 0, tzinfo=timezone.utc))

        # 2. Invalid custom_date raises 422
        f2 = UploadFile(filename="invalid_date.jpg", file=io.BytesIO(make_dummy_jpeg() + b"test_2"))
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(upload_media(
                file=f2,
                scanned_path=None,
                rating=RatingEnum.safe,
                tags="",
                album_ids=None,
                source=None,
                category_hints=None,
                description=None,
                custom_date="not-a-valid-date",
                current_user=self.admin_user,
                db=self.db,
            ))
        self.assertEqual(ctx.exception.status_code, 422)

    def test_upload_media_invalid_date_leaves_no_orphan_files(self):
        """Test that passing an invalid custom_date to upload_media raises 422 and leaves no files behind."""
        from backend.app.routes.media import upload_media

        orig_before = set(settings.ORIGINAL_DIR.glob("*"))
        thumb_before = set(settings.THUMBNAIL_DIR.glob("*"))

        f = UploadFile(filename="orphan_test.jpg", file=io.BytesIO(make_dummy_jpeg() + b"unique_orphan"))
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(upload_media(
                file=f,
                scanned_path=None,
                rating=RatingEnum.safe,
                tags="",
                album_ids=None,
                source=None,
                category_hints=None,
                description=None,
                custom_date="completely-invalid-date",
                current_user=self.admin_user,
                db=self.db,
            ))
        self.assertEqual(ctx.exception.status_code, 422)

        orig_after = set(settings.ORIGINAL_DIR.glob("*"))
        thumb_after = set(settings.THUMBNAIL_DIR.glob("*"))

        self.assertEqual(orig_before, orig_after)
        self.assertEqual(thumb_before, thumb_after)

    def test_process_and_save_media_post_commit_failure_retains_files(self):
        """Test that if an exception occurs after db.commit() in process_and_save_media, committed media and thumbnail are retained."""
        from unittest.mock import patch
        from backend.app.routes.media import process_and_save_media

        img_path = settings.ORIGINAL_DIR / "post_commit_test.jpg"
        img_path.write_bytes(make_dummy_jpeg() + b"post_commit_uniq")

        thumb_name = "post_commit_test.webp"
        expected_thumb = settings.THUMBNAIL_DIR / thumb_name

        with patch("backend.app.routes.media.ingestion.set_media_albums", side_effect=RuntimeError("Forced post-commit failure")):
            with self.assertRaises(RuntimeError):
                process_and_save_media(
                    db=self.db,
                    file_path=img_path,
                    unique_filename="post_commit_test.jpg",
                    rating=RatingEnum.safe,
                    tags="",
                    album_ids="999",
                    source=None,
                    category_hints=None,
                    description=None,
                )

        # Committed media row exists in database
        saved_media = self.db.query(Media).filter(Media.filename == "post_commit_test.jpg").first()
        self.assertIsNotNone(saved_media)

        # Thumbnail file exists on disk and was not unlinked
        self.assertTrue(expected_thumb.exists())

    def test_bulk_update_staged_items_custom_date_dedicated(self):
        """Dedicated test for bulk updating custom_date with valid date, 422 on invalid date, and reset with None, empty string, or whitespace."""
        session_res = asyncio.run(create_upload_session(current_user=self.admin_user))
        s_id = session_res["session_id"]

        f1 = UploadFile(filename="bulk1.jpg", file=io.BytesIO(make_dummy_jpeg() + b"bulk1"))
        f2 = UploadFile(filename="bulk2.jpg", file=io.BytesIO(make_dummy_jpeg() + b"bulk2"))
        f3 = UploadFile(filename="bulk3.jpg", file=io.BytesIO(make_dummy_jpeg() + b"bulk3"))

        item1 = asyncio.run(upload_files_to_session(session_id=s_id, file=f1, client_date="2023-01-01T00:00:00Z", current_user=self.admin_user, db=self.db))
        item2 = asyncio.run(upload_files_to_session(session_id=s_id, file=f2, client_date="2023-02-01T00:00:00Z", current_user=self.admin_user, db=self.db))
        item3 = asyncio.run(upload_files_to_session(session_id=s_id, file=f3, client_date="2023-03-01T00:00:00Z", current_user=self.admin_user, db=self.db))

        # 1. Bulk update item1 and item2 with explicit date
        res1 = asyncio.run(bulk_update_staged_items(
            session_id=s_id,
            req=BulkUpdateRequest(item_ids=[item1["item_id"], item2["item_id"]], custom_date="2025-06-01T15:30:00Z"),
            current_user=self.admin_user,
            db=self.db,
        ))
        self.assertEqual(res1["updated_count"], 2)
        res_map = {it["item_id"]: it for it in res1["items"]}
        self.assertEqual(res_map[item1["item_id"]]["custom_date"], "2025-06-01T15:30:00+00:00")
        self.assertEqual(res_map[item1["item_id"]]["custom_date_origin"], "explicit")
        self.assertEqual(res_map[item2["item_id"]]["custom_date"], "2025-06-01T15:30:00+00:00")
        self.assertEqual(res_map[item2["item_id"]]["custom_date_origin"], "explicit")

        # Item3 unaffected
        sess = asyncio.run(get_upload_session(session_id=s_id, current_user=self.admin_user))
        s_items = {it["item_id"]: it for it in sess["items"]}
        self.assertEqual(s_items[item3["item_id"]]["custom_date"], "2023-03-01T00:00:00+00:00")
        self.assertEqual(s_items[item3["item_id"]]["custom_date_origin"], "client")

        # 2. Invalid date raises 422
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(bulk_update_staged_items(
                session_id=s_id,
                req=BulkUpdateRequest(item_ids=[item1["item_id"]], custom_date="not-a-valid-date"),
                current_user=self.admin_user,
                db=self.db,
            ))
        self.assertEqual(ctx.exception.status_code, 422)

        # 3. Bulk reset with whitespace string "   "
        res_ws = asyncio.run(bulk_update_staged_items(
            session_id=s_id,
            req=BulkUpdateRequest(item_ids=[item1["item_id"], item2["item_id"]], custom_date="   "),
            current_user=self.admin_user,
            db=self.db,
        ))
        res_ws_map = {it["item_id"]: it for it in res_ws["items"]}
        self.assertEqual(res_ws_map[item1["item_id"]]["custom_date"], "2023-01-01T00:00:00+00:00")
        self.assertEqual(res_ws_map[item1["item_id"]]["custom_date_origin"], "client")
        self.assertEqual(res_ws_map[item2["item_id"]]["custom_date"], "2023-02-01T00:00:00+00:00")
        self.assertEqual(res_ws_map[item2["item_id"]]["custom_date_origin"], "client")

        # 4. Single-item update with whitespace string "   " resets to auto
        asyncio.run(update_staged_item(
            session_id=s_id,
            item_id=item1["item_id"],
            update=UploadSessionItemUpdate(custom_date="2025-01-01T00:00:00Z"),
            current_user=self.admin_user,
            db=self.db,
        ))
        reset_ws = asyncio.run(update_staged_item(
            session_id=s_id,
            item_id=item1["item_id"],
            update=UploadSessionItemUpdate(custom_date="   "),
            current_user=self.admin_user,
            db=self.db,
        ))
        self.assertEqual(reset_ws["custom_date"], "2023-01-01T00:00:00+00:00")
        self.assertEqual(reset_ws["custom_date_origin"], "client")

    def test_upload_session_custom_date_lifecycle(self):
        """Test client_date staging, single update, single reset, bulk update, bulk reset, and commit persistence."""
        from datetime import datetime, timezone

        session_res = asyncio.run(create_upload_session(current_user=self.admin_user))
        s_id = session_res["session_id"]

        # 1. Stage item with client_date
        f1 = UploadFile(filename="staged_pic1.jpg", file=io.BytesIO(make_dummy_jpeg() + b"uniq1"))
        item1 = asyncio.run(upload_files_to_session(
            session_id=s_id,
            file=f1,
            client_date="2023-04-01T10:00:00Z",
            current_user=self.admin_user,
            db=self.db,
        ))
        self.assertEqual(item1.get("custom_date"), "2023-04-01T10:00:00+00:00")
        self.assertEqual(item1.get("custom_date_origin"), "client")
        self.assertEqual(item1.get("custom_date_auto"), "2023-04-01T10:00:00+00:00")
        self.assertEqual(item1.get("custom_date_auto_origin"), "client")

        # 2. Update item custom_date via single PATCH
        updated_item = asyncio.run(update_staged_item(
            session_id=s_id,
            item_id=item1["item_id"],
            update=UploadSessionItemUpdate(custom_date="2022-02-02T00:00:00Z"),
            current_user=self.admin_user,
            db=self.db,
        ))
        self.assertEqual(updated_item.get("custom_date"), "2022-02-02T00:00:00+00:00")
        self.assertEqual(updated_item.get("custom_date_origin"), "explicit")

        # 3. Reset item custom_date via custom_date=None, restoring auto-detected client date
        reset_item = asyncio.run(update_staged_item(
            session_id=s_id,
            item_id=item1["item_id"],
            update=UploadSessionItemUpdate(custom_date=None),
            current_user=self.admin_user,
            db=self.db,
        ))
        self.assertEqual(reset_item.get("custom_date"), "2023-04-01T10:00:00+00:00")
        self.assertEqual(reset_item.get("custom_date_origin"), "client")

        # 4. Invalid single PATCH raises 422
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(update_staged_item(
                session_id=s_id,
                item_id=item1["item_id"],
                update=UploadSessionItemUpdate(custom_date="bad-date"),
                current_user=self.admin_user,
                db=self.db,
            ))
        self.assertEqual(ctx.exception.status_code, 422)

        # 5. Stage second item
        f2 = UploadFile(filename="staged_pic2.jpg", file=io.BytesIO(make_dummy_jpeg() + b"uniq2"))
        item2 = asyncio.run(upload_files_to_session(
            session_id=s_id,
            file=f2,
            current_user=self.admin_user,
            db=self.db,
        ))

        # 6. Bulk update custom_date
        bulk_res = asyncio.run(bulk_update_staged_items(
            session_id=s_id,
            req=BulkUpdateRequest(
                item_ids=[item1["item_id"], item2["item_id"]],
                custom_date="2020-01-01T00:00:00Z",
            ),
            current_user=self.admin_user,
            db=self.db,
        ))
        self.assertEqual(bulk_res["updated_count"], 2)
        for bi in bulk_res["items"]:
            self.assertEqual(bi.get("custom_date"), "2020-01-01T00:00:00+00:00")
            self.assertEqual(bi.get("custom_date_origin"), "explicit")

        # 7. Bulk reset custom_date with custom_date=None restores auto-detected dates
        bulk_reset_res = asyncio.run(bulk_update_staged_items(
            session_id=s_id,
            req=BulkUpdateRequest(
                item_ids=[item1["item_id"], item2["item_id"]],
                custom_date=None,
            ),
            current_user=self.admin_user,
            db=self.db,
        ))
        self.assertEqual(bulk_reset_res["updated_count"], 2)
        items_map = {it["item_id"]: it for it in bulk_reset_res["items"]}
        self.assertEqual(items_map[item1["item_id"]].get("custom_date"), "2023-04-01T10:00:00+00:00")
        self.assertEqual(items_map[item1["item_id"]].get("custom_date_origin"), "client")
        self.assertEqual(items_map[item2["item_id"]].get("custom_date_origin"), item2.get("custom_date_auto_origin"))

        # Re-set explicit date on both items before committing
        asyncio.run(bulk_update_staged_items(
            session_id=s_id,
            req=BulkUpdateRequest(
                item_ids=[item1["item_id"], item2["item_id"]],
                custom_date="2020-01-01T00:00:00Z",
            ),
            current_user=self.admin_user,
            db=self.db,
        ))

        # 8. Bulk update with invalid date raises 422
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(bulk_update_staged_items(
                session_id=s_id,
                req=BulkUpdateRequest(
                    item_ids=[item1["item_id"]],
                    custom_date="bad-bulk-date",
                ),
                current_user=self.admin_user,
                db=self.db,
            ))
        self.assertEqual(ctx.exception.status_code, 422)

        # 9. Commit session persists custom_date to DB
        commit_res = asyncio.run(commit_upload_session(
            session_id=s_id,
            current_user=self.admin_user,
            db=self.db,
        ))
        self.assertEqual(commit_res.total_created, 2)
        for result in commit_res.results:
            db_media = self.db.query(Media).filter(Media.id == result.media_id).first()
            self.assertIsNotNone(db_media)
            cdate = db_media.custom_date if db_media.custom_date.tzinfo else db_media.custom_date.replace(tzinfo=timezone.utc)
            self.assertEqual(cdate, datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc))

    def test_untracked_files_with_client_date(self):
        """Test adding untracked file to session propagates client_date into staged custom_date and custom_date_auto."""
        sample_path = settings.ORIGINAL_DIR / "untracked_sample.jpg"
        sample_path.write_bytes(make_dummy_jpeg() + b"untracked")

        session_res = asyncio.run(create_upload_session(current_user=self.admin_user))
        s_id = session_res["session_id"]

        req = UploadSessionAddUntrackedRequest(
            file_path=str(sample_path),
            client_date="2024-05-20T08:00:00Z",
        )
        item = asyncio.run(add_untracked_file_to_session(
            session_id=s_id,
            request=req,
            current_user=self.admin_user,
            db=self.db,
        ))

        self.assertEqual(item.get("custom_date"), "2024-05-20T08:00:00+00:00")
        self.assertEqual(item.get("custom_date_origin"), "client")
        self.assertEqual(item.get("custom_date_auto"), "2024-05-20T08:00:00+00:00")
        self.assertEqual(item.get("custom_date_auto_origin"), "client")

    def test_stage_file_with_booru_date(self):
        """Test uploading file to session with booru_date resolves origin to booru and persists on commit."""
        session_res = asyncio.run(create_upload_session(current_user=self.admin_user))
        s_id = session_res["session_id"]

        f1 = UploadFile(filename="booru_staged.jpg", file=io.BytesIO(make_dummy_jpeg() + b"booru1"))
        item = asyncio.run(upload_files_to_session(
            session_id=s_id,
            file=f1,
            booru_date="2021-11-17T16:32:23.400000-05:00",
            client_date="2026-10-23T19:00:00+00:00",
            current_user=self.admin_user,
            db=self.db,
        ))

        self.assertEqual(item.get("custom_date"), "2021-11-17T21:32:23.400000+00:00")
        self.assertEqual(item.get("custom_date_origin"), "booru")
        self.assertEqual(item.get("custom_date_auto"), "2021-11-17T21:32:23.400000+00:00")
        self.assertEqual(item.get("custom_date_auto_origin"), "booru")

        commit_res = asyncio.run(commit_upload_session(
            session_id=s_id,
            current_user=self.admin_user,
            db=self.db,
        ))
        self.assertEqual(commit_res.total_created, 1)
        media_id = commit_res.results[0].media_id
        db_media = self.db.query(Media).filter(Media.id == media_id).first()
        self.assertIsNotNone(db_media)
        cdate = db_media.custom_date if db_media.custom_date.tzinfo else db_media.custom_date.replace(tzinfo=timezone.utc)
        self.assertEqual(cdate, datetime(2021, 11, 17, 21, 32, 23, 400000, tzinfo=timezone.utc))

    def test_stage_untracked_file_with_booru_date(self):
        """Test adding untracked file to session with booru_date resolves origin to booru."""
        sample_path = settings.ORIGINAL_DIR / "untracked_booru.jpg"
        sample_path.write_bytes(make_dummy_jpeg() + b"untracked_booru")

        session_res = asyncio.run(create_upload_session(current_user=self.admin_user))
        s_id = session_res["session_id"]

        req = UploadSessionAddUntrackedRequest(
            file_path=str(sample_path),
            booru_date="2026-10-23T19:00:17+00:00",
            client_date="2026-10-23T20:00:00+00:00",
        )
        item = asyncio.run(add_untracked_file_to_session(
            session_id=s_id,
            request=req,
            current_user=self.admin_user,
            db=self.db,
        ))

        self.assertEqual(item.get("custom_date"), "2026-10-23T19:00:17+00:00")
        self.assertEqual(item.get("custom_date_origin"), "booru")
        self.assertEqual(item.get("custom_date_auto"), "2026-10-23T19:00:17+00:00")
        self.assertEqual(item.get("custom_date_auto_origin"), "booru")

    def test_booru_import_carries_booru_date(self):
        """Test download_and_import sets media.custom_date from booru post.uploaded_at."""
        from datetime import datetime, timezone
        from unittest.mock import MagicMock, patch
        from backend.app.routes.booru_import import ImportRequest, download_and_import
        from backend.app.services.booru.types import BooruPost, BooruTag

        mock_post = BooruPost(
            id=101,
            tags=[BooruTag(name="tag1", category="general")],
            rating="safe",
            source="https://example.com/source1",
            file_url="https://booru.example.com/data/sample.jpg",
            preview_url="https://booru.example.com/preview/sample.jpg",
            filename="booru_sample.jpg",
            file_size=len(make_dummy_jpeg()),
            width=100,
            height=100,
            booru_url="https://booru.example.com/posts/101",
            description="desc",
            uploaded_at="2022-08-15T14:30:00+00:00",
        )

        mock_client = MagicMock()
        mock_client.base_url = "https://booru.example.com"
        mock_client.fetch_post_by_url.return_value = mock_post

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_content.return_value = [make_dummy_jpeg()]

        req = ImportRequest(
            url="https://booru.example.com/posts/101",
            auto_create_tags=False,
        )

        with patch("backend.app.routes.booru_import.get_client_for_url", return_value=mock_client), \
             patch("backend.app.routes.booru_import.safe_request", return_value=mock_response):
            res = asyncio.run(download_and_import(
                req=req,
                current_user=self.admin_user,
                db=self.db,
            ))

        media = self.db.query(Media).filter(Media.id == res.id).first()
        self.assertIsNotNone(media)
        cdate = media.custom_date if media.custom_date.tzinfo else media.custom_date.replace(tzinfo=timezone.utc)
        self.assertEqual(cdate, datetime(2022, 8, 15, 14, 30, 0, tzinfo=timezone.utc))

    def test_url_import_carries_booru_date(self):
        """Test _do_import_media_url sets media.custom_date from booru post.uploaded_at."""
        import tempfile
        from datetime import datetime, timezone
        from unittest.mock import MagicMock, patch
        from backend.app.routes.url_import import ImportRequest, _do_import_media_url
        from backend.app.services.booru.types import BooruPost

        mock_post = BooruPost(
            id=202,
            tags=[],
            rating="safe",
            source="https://example.com/source2",
            file_url="https://booru.example.com/data/sample2.jpg",
            preview_url="https://booru.example.com/preview/sample2.jpg",
            filename="url_booru_sample.jpg",
            file_size=len(make_dummy_jpeg() + b"url"),
            width=100,
            height=100,
            booru_url="https://booru.example.com/posts/202",
            description="desc2",
            uploaded_at="2021-11-20T09:15:00+00:00",
        )

        mock_client = MagicMock()
        mock_client.fetch_post_by_url.return_value = mock_post

        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
            tmp.write(make_dummy_jpeg() + b"url")
            tmp_path = Path(tmp.name)

        req = ImportRequest(
            url="https://booru.example.com/posts/202",
        )

        with patch("backend.app.routes.url_import.get_client_for_url", return_value=mock_client), \
             patch("backend.app.routes.url_import.download_media_to_temp", return_value=(tmp_path, "url_booru_sample.jpg")):
            res = _do_import_media_url(req)

        media = self.db.query(Media).filter(Media.id == res.id).first()
        self.assertIsNotNone(media)
        cdate = media.custom_date if media.custom_date.tzinfo else media.custom_date.replace(tzinfo=timezone.utc)
        self.assertEqual(cdate, datetime(2021, 11, 20, 9, 15, 0, tzinfo=timezone.utc))
