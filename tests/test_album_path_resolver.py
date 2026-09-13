import asyncio
import io
import unittest

from fastapi import UploadFile

from backend.app.config import settings
from backend.app.models import Album, User
from backend.app.routes.uploads import (
    commit_upload_session,
    create_upload_session,
    get_pending_entities,
    update_folder_mapping,
    update_pending_album,
    upload_files_to_session,
)
from backend.app.schemas import FolderMappingRequest, PendingAlbumUpdate
from backend.app.utils.album_path_resolver import (
    apply_folder_mapping_to_path,
    build_pending_album_tree,
    resolve_album_path,
)
from tests.backup_test_base import BackupTestBase, make_dummy_jpeg

class TestAlbumPathResolver(BackupTestBase):
    def setUp(self):
        super().setUp()
        self.admin_user = User(id=1, username="admin", password_hash="hash")
        self.cache_dir = self.tmp_path / "media" / "cache"
        self.upload_sessions_dir = self.cache_dir / "upload-sessions"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.upload_sessions_dir.mkdir(parents=True, exist_ok=True)

        self.old_cache = settings.CACHE_DIR
        settings.CACHE_DIR = self.cache_dir

        import backend.app.routes.uploads as uploads_module
        self.old_module_sessions_dir = uploads_module.UPLOAD_SESSIONS_DIR
        uploads_module.UPLOAD_SESSIONS_DIR = self.upload_sessions_dir

    def tearDown(self):
        import backend.app.routes.uploads as uploads_module
        uploads_module.UPLOAD_SESSIONS_DIR = self.old_module_sessions_dir
        settings.CACHE_DIR = self.old_cache
        super().tearDown()

    def test_apply_folder_mapping_to_path(self):
        # Flatten mode
        self.assertIsNone(apply_folder_mapping_to_path("vacation/day1/img.jpg", mode="flatten"))
        self.assertIsNone(apply_folder_mapping_to_path("img.jpg", mode="use_root"))

        # Use root mode
        self.assertEqual(apply_folder_mapping_to_path("vacation/day1/img.jpg", mode="use_root"), "vacation/day1")
        self.assertEqual(apply_folder_mapping_to_path("vacation\\day1\\img.jpg", mode="use_root"), "vacation/day1")
        self.assertEqual(apply_folder_mapping_to_path("single_folder/img.jpg", mode="use_root"), "single_folder")

        # Skip root mode
        self.assertEqual(apply_folder_mapping_to_path("vacation/day1/img.jpg", mode="skip_root"), "day1")
        self.assertEqual(apply_folder_mapping_to_path("root/sub1/sub2/img.jpg", mode="skip_root"), "sub1/sub2")
        self.assertIsNone(apply_folder_mapping_to_path("root/img.jpg", mode="skip_root"))

    def test_resolve_album_path_against_db(self):
        # Create existing root album "Vacation 2024"
        root_alb = Album(name="Vacation 2024")
        self.db.add(root_alb)
        self.db.flush()

        # Create child album "Day 1"
        child_alb = Album(name="Day 1")
        self.db.add(child_alb)
        self.db.flush()
        root_alb.children.append(child_alb)
        self.db.commit()

        # Case-insensitive resolution of root and child
        resolved = resolve_album_path(self.db, "vacation 2024/day 1/beach")
        self.assertEqual(len(resolved), 3)

        self.assertEqual(resolved[0]["name"], "Vacation 2024")
        self.assertEqual(resolved[0]["existing_id"], root_alb.id)
        self.assertEqual(resolved[0]["depth"], 0)

        self.assertEqual(resolved[1]["name"], "Day 1")
        self.assertEqual(resolved[1]["existing_id"], child_alb.id)
        self.assertEqual(resolved[1]["depth"], 1)

        self.assertEqual(resolved[2]["name"], "beach")
        self.assertIsNone(resolved[2]["existing_id"])
        self.assertEqual(resolved[2]["depth"], 2)

    def test_build_pending_album_tree(self):
        root_alb = Album(name="Photos")
        self.db.add(root_alb)
        self.db.commit()

        items = {
            "item1": {
                "item_id": "item1",
                "suggested_album_path": "Photos/Trip/Day1",
            },
            "item2": {
                "item_id": "item2",
                "suggested_album_path": "Photos/Trip/Day1",
            },
            "item3": {
                "item_id": "item3",
                "suggested_album_path": "SoloFolder",
            },
        }

        tree = build_pending_album_tree(items, self.db)
        paths = {n["path"]: n for n in tree}

        # Existing album "Photos" should be excluded from pending tree
        self.assertNotIn("Photos", paths)

        self.assertIn("Photos/Trip", paths)
        self.assertIsNone(paths["Photos/Trip"]["existing_id"])
        self.assertEqual(paths["Photos/Trip"]["parent_path"], "Photos")
        self.assertEqual(paths["Photos/Trip"]["item_count"], 0)

        self.assertIn("Photos/Trip/Day1", paths)
        self.assertIsNone(paths["Photos/Trip/Day1"]["existing_id"])
        self.assertEqual(paths["Photos/Trip/Day1"]["item_count"], 2)
        self.assertFalse(paths["Photos/Trip/Day1"]["single_item_warning"])

        self.assertIn("SoloFolder", paths)
        self.assertEqual(paths["SoloFolder"]["item_count"], 1)
        self.assertTrue(paths["SoloFolder"]["single_item_warning"])

    def test_direct_item_counting_nested_folders(self):
        # Folder "good" with 1 direct file, and subfolder "good/test" with 1 direct file
        items = {
            "item1": {
                "item_id": "item1",
                "suggested_album_path": "good",
            },
            "item2": {
                "item_id": "item2",
                "suggested_album_path": "good/test",
            },
        }

        tree = build_pending_album_tree(items, self.db)
        paths = {n["path"]: n for n in tree}

        self.assertIn("good", paths)
        self.assertEqual(paths["good"]["item_count"], 1)
        self.assertEqual(paths["good"]["used_by"], ["item1"])

        self.assertIn("good/test", paths)
        self.assertEqual(paths["good/test"]["item_count"], 1)
        self.assertEqual(paths["good/test"]["used_by"], ["item2"])

    def test_folder_upload_and_pending_albums_api(self):
        session_res = asyncio.run(create_upload_session(current_user=self.admin_user))
        session_id = session_res["session_id"]

        f1 = UploadFile(filename="pic1.jpg", file=io.BytesIO(make_dummy_jpeg()))
        item1 = asyncio.run(
            upload_files_to_session(
                session_id=session_id,
                file=f1,
                relative_path="Travel/2026/pic1.jpg",
                current_user=self.admin_user,
                db=self.db,
            )
        )
        self.assertEqual(item1["suggested_album_path"], "Travel/2026")
        self.assertIsNotNone(item1["suggested_album_segments"])

        pending_res = asyncio.run(
            get_pending_entities(
                session_id=session_id,
                current_user=self.admin_user,
                db=self.db,
            )
        )
        album_paths = [a.path for a in pending_res.pending_albums]
        self.assertIn("Travel", album_paths)
        self.assertIn("Travel/2026", album_paths)

        # Update pending album: rename 2026 -> 2027
        update_res = asyncio.run(
            update_pending_album(
                session_id=session_id,
                update=PendingAlbumUpdate(
                    path="Travel/2026",
                    new_name="2027",
                ),
                current_user=self.admin_user,
                db=self.db,
            )
        )
        self.assertEqual(update_res["status"], "updated")

        pending_res2 = asyncio.run(
            get_pending_entities(
                session_id=session_id,
                current_user=self.admin_user,
                db=self.db,
            )
        )
        album_paths2 = [a.path for a in pending_res2.pending_albums]
        self.assertIn("Travel/2027", album_paths2)

        # Commit session
        commit_res = asyncio.run(
            commit_upload_session(
                session_id=session_id,
                current_user=self.admin_user,
                db=self.db,
            )
        )
        self.assertEqual(commit_res.total_created, 1)

        travel_alb = self.db.query(Album).filter(Album.name == "Travel").first()
        child_2027 = self.db.query(Album).filter(Album.name == "2027").first()
        self.assertIsNotNone(travel_alb)
        self.assertIsNotNone(child_2027)
        self.assertIn(child_2027, travel_alb.children)

    def test_reapply_folder_mapping_modes(self):
        session_res = asyncio.run(create_upload_session(current_user=self.admin_user))
        session_id = session_res["session_id"]

        f1 = UploadFile(filename="pic1.jpg", file=io.BytesIO(make_dummy_jpeg()))
        asyncio.run(
            upload_files_to_session(
                session_id=session_id,
                file=f1,
                relative_path="RootFolder/SubFolder/pic1.jpg",
                current_user=self.admin_user,
                db=self.db,
            )
        )

        # Switch to skip_root mode
        asyncio.run(
            update_folder_mapping(
                session_id=session_id,
                req=FolderMappingRequest(enabled=True, root_mode="skip_root"),
                current_user=self.admin_user,
                db=self.db,
            )
        )

        pending_res = asyncio.run(
            get_pending_entities(
                session_id=session_id,
                current_user=self.admin_user,
                db=self.db,
            )
        )
        paths = [a.path for a in pending_res.pending_albums]
        self.assertNotIn("RootFolder", paths)
        self.assertIn("SubFolder", paths)

        # Switch to flatten mode
        asyncio.run(
            update_folder_mapping(
                session_id=session_id,
                req=FolderMappingRequest(enabled=False, root_mode="flatten"),
                current_user=self.admin_user,
                db=self.db,
            )
        )

        pending_res_flat = asyncio.run(
            get_pending_entities(
                session_id=session_id,
                current_user=self.admin_user,
                db=self.db,
            )
        )
        self.assertEqual(len(pending_res_flat.pending_albums), 0)

    def test_folder_mapping_preserves_renames_removals_and_overrides(self):
        from backend.app.routes.uploads import get_upload_session, update_staged_item
        from backend.app.schemas import UploadSessionItemUpdate

        session_res = asyncio.run(create_upload_session(current_user=self.admin_user))
        session_id = session_res["session_id"]

        # Upload 3 files across 2 folders: Vacation/Beach/img1.jpg, Vacation/Beach/img2.jpg, Vacation/City/img3.jpg
        f1 = UploadFile(filename="img1.jpg", file=io.BytesIO(make_dummy_jpeg()))
        f2 = UploadFile(filename="img2.jpg", file=io.BytesIO(make_dummy_jpeg() + b"1"))
        f3 = UploadFile(filename="img3.jpg", file=io.BytesIO(make_dummy_jpeg() + b"2"))

        item1 = asyncio.run(upload_files_to_session(session_id=session_id, file=f1, relative_path="Vacation/Beach/img1.jpg", current_user=self.admin_user, db=self.db))
        item2 = asyncio.run(upload_files_to_session(session_id=session_id, file=f2, relative_path="Vacation/Beach/img2.jpg", current_user=self.admin_user, db=self.db))
        item3 = asyncio.run(upload_files_to_session(session_id=session_id, file=f3, relative_path="Vacation/City/img3.jpg", current_user=self.admin_user, db=self.db))

        # 1. Rename "Vacation" to "Holiday 2026"
        asyncio.run(
            update_pending_album(
                session_id=session_id,
                update=PendingAlbumUpdate(path="Vacation", new_name="Holiday 2026"),
                current_user=self.admin_user,
                db=self.db,
            )
        )

        # 2. Remove album from item2 specifically (media editor remove folder album)
        asyncio.run(
            update_staged_item(
                session_id=session_id,
                item_id=item2["item_id"],
                update=UploadSessionItemUpdate(suggested_album_path=None),
                current_user=self.admin_user,
                db=self.db,
            )
        )

        # 3. Toggle Root folder behavior to "skip_root"
        asyncio.run(
            update_folder_mapping(
                session_id=session_id,
                req=FolderMappingRequest(enabled=True, root_mode="skip_root"),
                current_user=self.admin_user,
                db=self.db,
            )
        )

        sess_data = asyncio.run(get_upload_session(session_id=session_id, current_user=self.admin_user))
        items_map = {it["item_id"]: it for it in sess_data["items"]}

        # item1 should have "Beach"
        self.assertEqual(items_map[item1["item_id"]]["suggested_album_path"], "Beach")
        # item2 should remain None (removed explicitly)
        self.assertIsNone(items_map[item2["item_id"]]["suggested_album_path"])
        # item3 should have "City"
        self.assertEqual(items_map[item3["item_id"]]["suggested_album_path"], "City")

        # 4. In skip_root mode, rename "Beach" to "Okinawa"
        asyncio.run(
            update_pending_album(
                session_id=session_id,
                update=PendingAlbumUpdate(path="Beach", new_name="Okinawa"),
                current_user=self.admin_user,
                db=self.db,
            )
        )

        # 5. Switch root mode back to "use_root"
        asyncio.run(
            update_folder_mapping(
                session_id=session_id,
                req=FolderMappingRequest(enabled=True, root_mode="use_root"),
                current_user=self.admin_user,
                db=self.db,
            )
        )

        sess_data = asyncio.run(get_upload_session(session_id=session_id, current_user=self.admin_user))
        items_map = {it["item_id"]: it for it in sess_data["items"]}

        # item1 should have "Holiday 2026/Okinawa" (both renames preserved!)
        self.assertEqual(items_map[item1["item_id"]]["suggested_album_path"], "Holiday 2026/Okinawa")
        # item2 should still be None
        self.assertIsNone(items_map[item2["item_id"]]["suggested_album_path"])
        # item3 should have "Holiday 2026/City" (Vacation -> Holiday 2026 preserved!)
        self.assertEqual(items_map[item3["item_id"]]["suggested_album_path"], "Holiday 2026/City")

        # 6. Uncheck "Create albums from folder structure" (enabled=False)
        asyncio.run(
            update_folder_mapping(
                session_id=session_id,
                req=FolderMappingRequest(enabled=False, root_mode="use_root"),
                current_user=self.admin_user,
                db=self.db,
            )
        )

        sess_data = asyncio.run(get_upload_session(session_id=session_id, current_user=self.admin_user))
        for it in sess_data["items"]:
            self.assertIsNone(it["suggested_album_path"])

        # 7. Re-check "Create albums from folder structure" (enabled=True)
        asyncio.run(
            update_folder_mapping(
                session_id=session_id,
                req=FolderMappingRequest(enabled=True, root_mode="use_root"),
                current_user=self.admin_user,
                db=self.db,
            )
        )

        sess_data = asyncio.run(get_upload_session(session_id=session_id, current_user=self.admin_user))
        items_map = {it["item_id"]: it for it in sess_data["items"]}

        # All customizations restored!
        self.assertEqual(items_map[item1["item_id"]]["suggested_album_path"], "Holiday 2026/Okinawa")
        self.assertIsNone(items_map[item2["item_id"]]["suggested_album_path"])
        self.assertEqual(items_map[item3["item_id"]]["suggested_album_path"], "Holiday 2026/City")

        # 8. Globally remove album "Holiday 2026/City"
        asyncio.run(
            update_pending_album(
                session_id=session_id,
                update=PendingAlbumUpdate(path="Holiday 2026/City", remove=True),
                current_user=self.admin_user,
                db=self.db,
            )
        )

        # Toggle root mode again and verify City is not restored
        asyncio.run(
            update_folder_mapping(
                session_id=session_id,
                req=FolderMappingRequest(enabled=True, root_mode="use_root"),
                current_user=self.admin_user,
                db=self.db,
            )
        )

        sess_data = asyncio.run(get_upload_session(session_id=session_id, current_user=self.admin_user))
        items_map = {it["item_id"]: it for it in sess_data["items"]}
        self.assertEqual(items_map[item1["item_id"]]["suggested_album_path"], "Holiday 2026/Okinawa")
        self.assertIsNone(items_map[item2["item_id"]]["suggested_album_path"])
        self.assertIsNone(items_map[item3["item_id"]]["suggested_album_path"])

if __name__ == "__main__":
    unittest.main()
