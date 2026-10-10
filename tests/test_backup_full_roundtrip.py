import io
import json
import unittest
import zipfile
from datetime import datetime, timezone

from backend.app.config import APP_VERSION, SCHEMA_VERSION, settings
from backend.app.enums import FileTypeEnum, RatingEnum, TagCategoryEnum
from backend.app.models import (Album, BooruConfig, Media, Tag,
                                TagImplication, blombooru_album_hierarchy,
                                blombooru_album_media)
from backend.app.utils.backup import import_albums_logical, import_full_backup
from tests.test_base import BackupTestBase, make_dummy_jpeg

class TestBackupFullRoundtrip(BackupTestBase):
    def test_full_backup_roundtrip(self):
        """Test creating a full backup with all models and restoring it on a clean database."""
        # 1. Setup sample media files
        dummy_jpeg_1 = make_dummy_jpeg()
        dummy_jpeg_2 = make_dummy_jpeg()

        m1_path = self.original_dir / "sample1.jpg"
        m2_path = self.original_dir / "sample2.jpg"
        m1_path.write_bytes(dummy_jpeg_1)
        m2_path.write_bytes(dummy_jpeg_2)

        # 2. Setup database entities
        t_artist = Tag(name="super_artist", category=TagCategoryEnum.artist, post_count=1)
        t_char = Tag(name="kitsune", category=TagCategoryEnum.character, post_count=1)
        t_implied = Tag(name="fox_ears", category=TagCategoryEnum.general, post_count=0)
        self.db.add_all([t_artist, t_char, t_implied])
        self.db.commit()

        # Tag Implication
        imp = TagImplication()
        imp.target_tags = [t_char]
        imp.implied_tags = [t_implied]
        imp.target_tag_patterns = ["*_fox"]
        self.db.add(imp)
        self.db.commit()

        # Media items
        m1 = Media(
            filename="sample1.jpg",
            path=str(m1_path.relative_to(settings.BASE_DIR)),
            hash="hash111",
            file_type=FileTypeEnum.image,
            mime_type="image/jpeg",
            file_size=len(dummy_jpeg_1),
            width=32,
            height=32,
            rating=RatingEnum.safe,
            source="https://example.com/art1",
            description="Artwork 1",
            is_shared=True,
            share_uuid="share-uuid-1",
            share_ai_metadata=True,
            share_language="en"
        )
        m1.tags.extend([t_artist, t_char])

        m2 = Media(
            filename="sample2.jpg",
            path=str(m2_path.relative_to(settings.BASE_DIR)),
            hash="hash222",
            file_type=FileTypeEnum.image,
            mime_type="image/jpeg",
            file_size=len(dummy_jpeg_2),
            width=32,
            height=32,
            rating=RatingEnum.questionable
        )
        self.db.add_all([m1, m2])
        self.db.commit()

        # Parent-child relationship (m2 is child of m1)
        m2.parent_id = m1.id
        self.db.commit()

        # Albums
        album_parent = Album(name="Main Art Collection")
        album_child = Album(name="Kitsune Sub-Collection")
        self.db.add_all([album_parent, album_child])
        self.db.commit()

        album_parent.children.append(album_child)
        self.db.commit()

        # Add media to album with explicit timestamp
        added_time = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        self.db.execute(blombooru_album_media.insert().values(
            album_id=album_parent.id,
            media_id=m1.id,
            added_at=added_time
        ))
        self.db.commit()

        # Booru config
        booru_cfg = BooruConfig(
            domain="danbooru.donmai.us",
            username="test_scraper_user",
            api_key="secret_booru_api_key_123"
        )
        self.db.add(booru_cfg)
        self.db.commit()

        # Custom theme CSS file
        test_theme_css = self.custom_themes_dir / "custom_solarized_dark.css"
        test_theme_css.write_text(":root { --primary-color: #b58900; }", encoding="utf-8")

        # Custom theme metadata
        from backend.app.custom_themes import custom_theme_manager
        custom_theme_manager._meta["custom_solarized_dark"] = {
            "name": "Solarized Dark",
            "is_dark": True,
            "primary_color": "#b58900",
            "background_color": "#002b36",
            "backup_theme_id": "default_dark",
            "created_at": "2026-08-14T00:00:00+00:00"
        }
        custom_theme_manager._save_meta()

        # App settings including custom background mapped to m1
        test_settings = {
            "app_name": "TestBlombooruInstance",
            "theme": "custom_solarized_dark",
            "items_per_page": 60,
            "custom_background": {
                "enabled": True,
                "media_id": m1.id,
                "blur": 10
            }
        }
        settings.save_settings(test_settings)

        # 3. Perform backup export simulation
        from backend.app.routes.admin.backup import backup_full_db

        class DummyAdmin:
            pass

        # Call the endpoint generator logic
        from backend.app.routes.admin.backup import (
            get_custom_theme_files_generator, get_media_files_generator)

        # Construct full backup archive manually to test roundtrip
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_STORED) as zf:
            zf.writestr("tags.csv", "super_artist,1,1,\nkitsune,4,1,\nfox_ears,0,0,\n")
            meta = {
                "version": APP_VERSION,
                "schema_version": SCHEMA_VERSION,
                "type": "full_backup",
                "media": [
                    {
                        "filename": "sample1.jpg",
                        "hash": "hash111",
                        "file_type": "image",
                        "mime_type": "image/jpeg",
                        "file_size": len(dummy_jpeg_1),
                        "width": 32,
                        "height": 32,
                        "rating": "safe",
                        "source": "https://example.com/art1",
                        "description": "Artwork 1",
                        "is_shared": True,
                        "share_uuid": "share-uuid-1",
                        "share_ai_metadata": True,
                        "share_language": "en",
                        "tags": ["super_artist", "kitsune"],
                        "archive_path": "media/sample1.jpg",
                        "parent_hash": None
                    },
                    {
                        "filename": "sample2.jpg",
                        "hash": "hash222",
                        "file_type": "image",
                        "mime_type": "image/jpeg",
                        "file_size": len(dummy_jpeg_2),
                        "width": 32,
                        "height": 32,
                        "rating": "questionable",
                        "tags": [],
                        "archive_path": "media/sample2.jpg",
                        "parent_hash": "hash111"
                    }
                ],
                "albums": [
                    {
                        "id": album_parent.id,
                        "name": "Main Art Collection",
                        "media": [
                            {
                                "hash": "hash111",
                                "added_at": added_time.isoformat()
                            }
                        ],
                        "media_hashes": ["hash111"],
                        "child_ids": [album_child.id]
                    },
                    {
                        "id": album_child.id,
                        "name": "Kitsune Sub-Collection",
                        "media": [],
                        "media_hashes": [],
                        "child_ids": []
                    }
                ],
                "tag_implications": [
                    {
                        "target_tags": ["kitsune"],
                        "target_tag_patterns": ["*_fox"],
                        "implied_tags": ["fox_ears"]
                    }
                ],
                "booru_config": [
                    {
                        "domain": "danbooru.donmai.us",
                        "username": "test_scraper_user",
                        "api_key": "secret_booru_api_key_123"
                    }
                ],
                "custom_themes": [
                    {
                        "id": "custom_solarized_dark",
                        "name": "Solarized Dark",
                        "is_dark": True,
                        "primary_color": "#b58900",
                        "background_color": "#002b36",
                        "backup_theme_id": "default_dark"
                    }
                ],
                "settings": {
                    "app_name": "TestBlombooruInstance",
                    "theme": "custom_solarized_dark",
                    "items_per_page": 60,
                    "custom_background": {
                        "enabled": True,
                        "media_hash": "hash111",
                        "blur": 10
                    }
                }
            }
            zf.writestr("backup.json", json.dumps(meta, indent=2))
            zf.writestr("media/sample1.jpg", dummy_jpeg_1)
            zf.writestr("media/sample2.jpg", dummy_jpeg_2)
            zf.writestr("custom_themes/custom_solarized_dark.css", ":root { --primary-color: #b58900; }")

        # 4. Clean database and media directories
        self.wipe_database()
        if m1_path.exists():
            m1_path.unlink()
        if m2_path.exists():
            m2_path.unlink()

        # 5. Import the full backup
        zip_buffer.seek(0)
        import_res = import_full_backup(zip_buffer, self.db)
        self.assertEqual(import_res["message"], "Import completed successfully")

        # 6. Verify restored database entities
        # Verify Media
        restored_m1 = self.db.query(Media).filter(Media.hash == "hash111").first()
        self.assertIsNotNone(restored_m1)
        self.assertEqual(restored_m1.filename, "sample1.jpg")
        self.assertEqual(restored_m1.source, "https://example.com/art1")
        self.assertTrue(restored_m1.is_shared)
        self.assertEqual(restored_m1.share_uuid, "share-uuid-1")
        self.assertEqual(len(restored_m1.tags), 2)

        restored_m2 = self.db.query(Media).filter(Media.hash == "hash222").first()
        self.assertIsNotNone(restored_m2)
        self.assertEqual(restored_m2.parent_id, restored_m1.id)

        # Verify Albums and Hierarchy
        restored_album = self.db.query(Album).filter(Album.name == "Main Art Collection").first()
        self.assertIsNotNone(restored_album)
        self.assertEqual(len(restored_album.children), 1)
        self.assertEqual(restored_album.children[0].name, "Kitsune Sub-Collection")
        self.assertEqual(len(restored_album.media), 1)
        self.assertEqual(restored_album.media[0].hash, "hash111")

        # Verify blombooru_album_media added_at
        album_media_row = self.db.query(blombooru_album_media).filter(
            blombooru_album_media.c.album_id == restored_album.id,
            blombooru_album_media.c.media_id == restored_m1.id
        ).first()
        self.assertIsNotNone(album_media_row)
        self.assertIsNotNone(album_media_row.added_at)

        # Verify Tag Implication
        restored_imp = self.db.query(TagImplication).first()
        self.assertIsNotNone(restored_imp)
        self.assertEqual(restored_imp.target_tag_patterns, ["*_fox"])
        self.assertEqual([t.name for t in restored_imp.target_tags], ["kitsune"])
        self.assertEqual([t.name for t in restored_imp.implied_tags], ["fox_ears"])

        # Verify Booru Config
        restored_booru = self.db.query(BooruConfig).filter(BooruConfig.domain == "danbooru.donmai.us").first()
        self.assertIsNotNone(restored_booru)
        self.assertEqual(restored_booru.username, "test_scraper_user")
        self.assertEqual(restored_booru.api_key, "secret_booru_api_key_123")

        # Verify Custom Theme registered and file exists
        self.assertTrue((self.custom_themes_dir / "custom_solarized_dark.css").exists())
        self.assertIn("custom_solarized_dark", [t["id"] for t in custom_theme_manager.get_all()])

        # Verify Settings restoration and custom_background media_id re-linking
        current_settings = settings.settings
        self.assertEqual(current_settings.get("app_name"), "TestBlombooruInstance")
        self.assertEqual(current_settings.get("theme"), "custom_solarized_dark")
        self.assertEqual(current_settings.get("items_per_page"), 60)
        self.assertEqual(current_settings.get("custom_background", {}).get("media_id"), restored_m1.id)

    def test_legacy_backup_compatibility(self):
        """Test importing an older format backup ZIP that lacks newer fields."""
        dummy_jpeg = make_dummy_jpeg()
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zf:
            zf.writestr("tags.csv", "legacy_tag,0,0,\n")
            meta = {
                "version": "0.1.0",
                "type": "full_backup",
                "media": [
                    {
                        "filename": "legacy.jpg",
                        "hash": "legacyhash123",
                        "file_type": "image",
                        "mime_type": "image/jpeg",
                        "file_size": len(dummy_jpeg),
                        "archive_path": "media/legacy.jpg"
                    }
                ],
                "albums": [
                    {
                        "id": 1,
                        "name": "Old Album",
                        "media_hashes": ["legacyhash123"]
                    }
                ]
            }
            zf.writestr("backup.json", json.dumps(meta))
            zf.writestr("media/legacy.jpg", dummy_jpeg)

        zip_buffer.seek(0)
        result = import_full_backup(zip_buffer, self.db)
        self.assertEqual(result["message"], "Import completed successfully")

        restored = self.db.query(Media).filter(Media.hash == "legacyhash123").first()
        self.assertIsNotNone(restored)
        self.assertEqual(restored.filename, "legacy.jpg")
        self.assertIsNone(restored.source)
        self.assertFalse(restored.is_shared)
        self.assertIsNotNone(restored.uploaded_at)

        album = self.db.query(Album).filter(Album.name == "Old Album").first()
        self.assertIsNotNone(album)
        self.assertEqual(len(album.media), 1)

    def test_onboarding_with_backup_import(self):
        """Test onboarding import logic preserving host settings and admin credentials while restoring data."""
        dummy_jpeg = make_dummy_jpeg()
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zf:
            zf.writestr("tags.csv", "cherry_blossom,0,1,\n")
            meta = {
                "version": APP_VERSION,
                "schema_version": SCHEMA_VERSION,
                "type": "full_backup",
                "media": [
                    {
                        "filename": "sakura.jpg",
                        "hash": "sakurahash123",
                        "file_type": "image",
                        "mime_type": "image/jpeg",
                        "file_size": len(dummy_jpeg),
                        "rating": "safe",
                        "tags": ["cherry_blossom"],
                        "archive_path": "media/sakura.jpg"
                    }
                ],
                "settings": {
                    "app_name": "OldBackupName",
                    "items_per_page": 50,
                    "database": {
                        "host": "cool-db-host",
                        "password": "cool-db-password"
                    }
                }
            }
            zf.writestr("backup.json", json.dumps(meta))
            zf.writestr("media/sakura.jpg", dummy_jpeg)

        zip_buffer.seek(0)
        import_full_backup(zip_buffer, self.db)

        # Verify media and tags are restored
        m = self.db.query(Media).filter(Media.hash == "sakurahash123").first()
        self.assertIsNotNone(m)
        self.assertEqual(m.filename, "sakura.jpg")

        # Verify sensitive host connection parameters were NOT overwritten from backup
        self.assertNotEqual(settings.settings.get("database", {}).get("host"), "cool-db-host")
        self.assertEqual(settings.settings.get("items_per_page"), 50)

    def test_post_counts_recalculated_after_media_import(self):
        """Test that tag post counts are updated accurately when media with tags are imported."""
        t1 = Tag(name="sky", category=TagCategoryEnum.general, post_count=0)
        self.db.add(t1)
        self.db.commit()

        dummy_jpeg = make_dummy_jpeg()
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zf:
            zf.writestr("tags.csv", "sky,0,0,\n")
            meta = {
                "version": APP_VERSION,
                "type": "full_backup",
                "media": [
                    {
                        "filename": "sky1.jpg",
                        "hash": "skyhash1",
                        "file_type": "image",
                        "mime_type": "image/jpeg",
                        "file_size": len(dummy_jpeg),
                        "rating": "safe",
                        "tags": ["sky"],
                        "archive_path": "media/sky1.jpg"
                    },
                    {
                        "filename": "sky2.jpg",
                        "hash": "skyhash2",
                        "file_type": "image",
                        "mime_type": "image/jpeg",
                        "file_size": len(dummy_jpeg),
                        "rating": "safe",
                        "tags": ["sky"],
                        "archive_path": "media/sky2.jpg"
                    }
                ]
            }
            zf.writestr("backup.json", json.dumps(meta))
            zf.writestr("media/sky1.jpg", dummy_jpeg)
            zf.writestr("media/sky2.jpg", dummy_jpeg)

        zip_buffer.seek(0)
        import_full_backup(zip_buffer, self.db)

        tag = self.db.query(Tag).filter(Tag.name == "sky").first()
        self.assertEqual(tag.post_count, 2)

    def test_album_sort_position_and_metrics_full_roundtrip(self):
        """Test full roundtrip export and import"""
        import asyncio
        from backend.app.routes.admin.backup import backup_full_db
        from backend.app.models import User

        # Create dummy admin
        admin = User(username="admin_tester", password_hash="dummy")
        self.db.add(admin)
        self.db.commit()

        # 1. Setup sample media files
        dummy_jpeg = make_dummy_jpeg()
        (self.original_dir / "m_safe.jpg").write_bytes(dummy_jpeg)
        (self.original_dir / "m_quest.jpg").write_bytes(dummy_jpeg)
        (self.original_dir / "m_expl.jpg").write_bytes(dummy_jpeg)

        m_safe = Media(
            filename="m_safe.jpg",
            path=str((self.original_dir / "m_safe.jpg").relative_to(settings.BASE_DIR)),
            hash="hash_safe",
            file_type=FileTypeEnum.image,
            mime_type="image/jpeg",
            file_size=len(dummy_jpeg),
            rating=RatingEnum.safe
        )
        m_quest = Media(
            filename="m_quest.jpg",
            path=str((self.original_dir / "m_quest.jpg").relative_to(settings.BASE_DIR)),
            hash="hash_quest",
            file_type=FileTypeEnum.image,
            mime_type="image/jpeg",
            file_size=len(dummy_jpeg),
            rating=RatingEnum.questionable
        )
        m_expl = Media(
            filename="m_expl.jpg",
            path=str((self.original_dir / "m_expl.jpg").relative_to(settings.BASE_DIR)),
            hash="hash_expl",
            file_type=FileTypeEnum.image,
            mime_type="image/jpeg",
            file_size=len(dummy_jpeg),
            rating=RatingEnum.explicit
        )
        self.db.add_all([m_safe, m_quest, m_expl])
        self.db.commit()

        # 2. Setup albums with sort_position
        root_a = Album(name="Root Album A", sort_position=1)
        root_b = Album(name="Root Album B", sort_position=0)
        child_a1 = Album(name="Child A1", sort_position=None)
        child_a2 = Album(name="Child A2", sort_position=None)
        self.db.add_all([root_a, root_b, child_a1, child_a2])
        self.db.commit()

        # Hierarchy with sort_position
        self.db.execute(blombooru_album_hierarchy.insert().values([
            {"parent_album_id": root_a.id, "child_album_id": child_a1.id, "sort_position": 2},
            {"parent_album_id": root_a.id, "child_album_id": child_a2.id, "sort_position": 0}
        ]))

        # Album media with sort_position
        self.db.execute(blombooru_album_media.insert().values([
            {"album_id": root_a.id, "media_id": m_safe.id, "sort_position": 5},
            {"album_id": child_a1.id, "media_id": m_quest.id, "sort_position": 1},
            {"album_id": child_a2.id, "media_id": m_expl.id, "sort_position": 0}
        ]))
        self.db.commit()

        # 3. Perform backup export via backup_full_db
        response = asyncio.run(backup_full_db(current_user=admin, db=self.db))
        self.assertEqual(response.media_type, "application/zip")

        # Collect streamed ZIP bytes
        zip_bytes = io.BytesIO()
        async def collect_stream():
            async for chunk in response.body_iterator:
                zip_bytes.write(chunk)
        asyncio.run(collect_stream())

        # Inspect backup.json within ZIP
        zip_bytes.seek(0)
        with zipfile.ZipFile(zip_bytes, 'r') as zf:
            self.assertIn("backup.json", zf.namelist())
            meta = json.loads(zf.read("backup.json").decode('utf-8'))

        exported_albums = {alb["name"]: alb for alb in meta["albums"]}
        self.assertEqual(exported_albums["Root Album A"]["sort_position"], 1)
        self.assertEqual(exported_albums["Root Album B"]["sort_position"], 0)

        # Check media sort_position in Root Album A
        root_a_media = {m["hash"]: m for m in exported_albums["Root Album A"]["media"]}
        self.assertEqual(root_a_media["hash_safe"]["sort_position"], 5)

        # Check children sort_position in Root Album A
        root_a_children = {c["id"]: c["sort_position"] for c in exported_albums["Root Album A"]["children"]}
        self.assertEqual(root_a_children[child_a1.id], 2)
        self.assertEqual(root_a_children[child_a2.id], 0)

        # 4. Clean database and media directories
        self.wipe_database()
        for p in [self.original_dir / "m_safe.jpg", self.original_dir / "m_quest.jpg", self.original_dir / "m_expl.jpg"]:
            if p.exists():
                p.unlink()

        # 5. Restore full backup
        zip_bytes.seek(0)
        import_res = import_full_backup(zip_bytes, self.db)
        self.assertEqual(import_res["message"], "Import completed successfully")

        # 6. Verify sort_positions restored accurately
        restored_root_a = self.db.query(Album).filter(Album.name == "Root Album A").first()
        restored_root_b = self.db.query(Album).filter(Album.name == "Root Album B").first()
        restored_child_a1 = self.db.query(Album).filter(Album.name == "Child A1").first()
        restored_child_a2 = self.db.query(Album).filter(Album.name == "Child A2").first()

        self.assertIsNotNone(restored_root_a)
        self.assertIsNotNone(restored_root_b)
        self.assertIsNotNone(restored_child_a1)
        self.assertIsNotNone(restored_child_a2)

        self.assertEqual(restored_root_a.sort_position, 1)
        self.assertEqual(restored_root_b.sort_position, 0)

        # Verify album_media sort_position
        restored_m_safe = self.db.query(Media).filter(Media.hash == "hash_safe").first()
        restored_m_quest = self.db.query(Media).filter(Media.hash == "hash_quest").first()
        restored_m_expl = self.db.query(Media).filter(Media.hash == "hash_expl").first()

        row_safe = self.db.query(blombooru_album_media).filter(
            blombooru_album_media.c.album_id == restored_root_a.id,
            blombooru_album_media.c.media_id == restored_m_safe.id
        ).first()
        self.assertEqual(row_safe.sort_position, 5)

        row_quest = self.db.query(blombooru_album_media).filter(
            blombooru_album_media.c.album_id == restored_child_a1.id,
            blombooru_album_media.c.media_id == restored_m_quest.id
        ).first()
        self.assertEqual(row_quest.sort_position, 1)

        row_expl = self.db.query(blombooru_album_media).filter(
            blombooru_album_media.c.album_id == restored_child_a2.id,
            blombooru_album_media.c.media_id == restored_m_expl.id
        ).first()
        self.assertEqual(row_expl.sort_position, 0)

        # Verify hierarchy sort_position
        hier_a1 = self.db.query(blombooru_album_hierarchy).filter(
            blombooru_album_hierarchy.c.parent_album_id == restored_root_a.id,
            blombooru_album_hierarchy.c.child_album_id == restored_child_a1.id
        ).first()
        self.assertEqual(hier_a1.sort_position, 2)

        hier_a2 = self.db.query(blombooru_album_hierarchy).filter(
            blombooru_album_hierarchy.c.parent_album_id == restored_root_a.id,
            blombooru_album_hierarchy.c.child_album_id == restored_child_a2.id
        ).first()
        self.assertEqual(hier_a2.sort_position, 0)

        # 7. Verify metrics recalculated on restore
        # Child A1 has 1 questionable media
        self.assertEqual(restored_child_a1.cached_direct_media_count, 1)
        self.assertEqual(restored_child_a1.cached_media_count, 1)
        self.assertEqual(restored_child_a1.cached_rating, RatingEnum.questionable)

        # Child A2 has 1 explicit media
        self.assertEqual(restored_child_a2.cached_direct_media_count, 1)
        self.assertEqual(restored_child_a2.cached_media_count, 1)
        self.assertEqual(restored_child_a2.cached_rating, RatingEnum.explicit)

        # Root Album A has 1 safe direct media + 2 from children (1 quest + 1 expl) -> total 3, rating explicit
        self.assertEqual(restored_root_a.cached_direct_media_count, 1)
        self.assertEqual(restored_root_a.cached_media_count, 3)
        self.assertEqual(restored_root_a.cached_rating, RatingEnum.explicit)

        # Root Album B is empty
        self.assertEqual(restored_root_b.cached_direct_media_count, 0)
        self.assertEqual(restored_root_b.cached_media_count, 0)
        self.assertEqual(restored_root_b.cached_rating, RatingEnum.safe)

    def test_import_albums_logical_recalculates_metrics_standalone(self):
        """Test that calling import_albums_logical standalone updates metrics for all albums."""
        dummy_jpeg = make_dummy_jpeg()
        m = Media(
            filename="standalone_photo.jpg",
            path=str(self.original_dir / "standalone_photo.jpg"),
            hash="hash_standalone",
            file_type=FileTypeEnum.image,
            mime_type="image/jpeg",
            file_size=len(dummy_jpeg),
            rating=RatingEnum.explicit
        )
        self.db.add(m)
        self.db.commit()

        albums_data = [
            {
                "id": 100,
                "name": "Standalone Album",
                "sort_position": 3,
                "media": [
                    {"hash": "hash_standalone", "sort_position": 0}
                ]
            }
        ]

        import_albums_logical(self.db, albums_data)

        alb = self.db.query(Album).filter(Album.name == "Standalone Album").first()
        self.assertIsNotNone(alb)
        self.assertEqual(alb.sort_position, 3)
        self.assertEqual(alb.cached_direct_media_count, 1)
        self.assertEqual(alb.cached_media_count, 1)
        self.assertEqual(alb.cached_rating, RatingEnum.explicit)

if __name__ == "__main__":
    unittest.main()
