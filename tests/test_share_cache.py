import asyncio
import io
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

from fastapi import BackgroundTasks
from PIL import Image

from backend.app.config import settings
from backend.app.enums import FileTypeEnum, RatingEnum
from backend.app.models import Media, User
from backend.app.routes.admin.settings import clear_cache, get_cache_stats
from backend.app.routes.media import (
    PostUpdateRequest,
    share_media,
    unshare_media,
    update_from_source,
    update_share_settings,
)
from backend.app.schemas import ShareSettingsUpdate
from backend.app.utils.media_helpers import (
    _cache_locks,
    cleanup_dead_media_cache,
    create_stripped_media_cache,
    delete_media_cache,
    evict_stripped_cache_if_needed,
    get_effective_media_path,
    get_media_cache_status,
    get_stripped_cache_path,
    get_stripped_cache_stats,
    migrate_legacy_stripped_cache,
    rebuild_stripped_cache_if_needed,
)
from tests.test_base import AsyncBackupTestBase

class DummyRequest:
    def __init__(self):
        self.headers = {}
        self.client = MagicMock()
        self.client.host = "127.0.0.1"

class TestShareCacheRework(AsyncBackupTestBase):

    def setUp(self):
        super().setUp()
        self.admin_user = User(id=1, username="admin", password_hash="hash")

    def _create_image_file(self, rel_path: str, color="blue", size=(32, 32)) -> Path:
        full_path = self.base_path / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGB", size, color=color)
        img.save(full_path, format="PNG")
        return full_path

    def _create_media(
        self,
        filename: str,
        rel_path: str,
        media_hash: str,
        transcoded_path: str = None,
        mime_type: str = "image/png",
        is_shared: bool = False,
        share_ai_metadata: bool = False,
    ) -> Media:
        media = Media(
            filename=filename,
            path=rel_path,
            transcoded_path=transcoded_path,
            hash=media_hash,
            file_type=FileTypeEnum.image,
            mime_type=mime_type,
            file_size=1024,
            rating=RatingEnum.safe,
            is_shared=is_shared,
            share_uuid="uuid-" + media_hash if is_shared else None,
            share_ai_metadata=share_ai_metadata,
            uploaded_at=datetime.now(),
        )
        self.db.add(media)
        self.db.commit()
        self.db.refresh(media)
        return media

    async def test_share_and_unshare_transcoded_image_deletes_cache(self):
        # 1. Setup transcoded media (e.g. HEIC original with WEBP transcoded copy)
        orig_file = self._create_image_file("media/original/photo.heic")
        trans_file = self._create_image_file("media/transcoded/photo.webp")
        media = self._create_media(
            filename="photo.heic",
            rel_path="media/original/photo.heic",
            media_hash="hash_heic_123",
            transcoded_path="media/transcoded/photo.webp",
            mime_type="image/heic",
            is_shared=False,
        )

        bg = BackgroundTasks()
        share_res = await share_media(
            media_id=media.id,
            background_tasks=bg,
            current_user=self.admin_user,
            db=self.db,
        )
        self.assertTrue(share_res["share_url"].startswith("/shared/"))

        # Effective path points to transcoded copy
        eff = get_effective_media_path(media)
        self.assertEqual(eff, trans_file)

        # Expected stripped cache path
        cache_path = get_stripped_cache_path(media)
        self.assertEqual(cache_path, settings.STRIPPED_CACHE_DIR / "hash_heic_123.webp")

        # Generate stripped cache
        created = await create_stripped_media_cache(media, "image/webp")
        self.assertEqual(created, cache_path)
        self.assertTrue(cache_path.exists())

        # Unshare media
        unshare_res = await unshare_media(
            media_id=media.id,
            current_user=self.admin_user,
            db=self.db,
        )
        self.assertEqual(unshare_res["message"], "Share removed")

        # Assert the cache file is deleted upon unshare
        self.assertFalse(cache_path.exists())

    async def test_share_and_unshare_non_transcoded_image_deletes_cache(self):
        orig_file = self._create_image_file("media/original/art.png")
        media = self._create_media(
            filename="art.png",
            rel_path="media/original/art.png",
            media_hash="hash_png_456",
            transcoded_path=None,
            mime_type="image/png",
            is_shared=False,
        )

        bg = BackgroundTasks()
        await share_media(
            media_id=media.id,
            background_tasks=bg,
            current_user=self.admin_user,
            db=self.db,
        )

        cache_path = get_stripped_cache_path(media)
        self.assertEqual(cache_path, settings.STRIPPED_CACHE_DIR / "hash_png_456.png")

        created = await create_stripped_media_cache(media, "image/png")
        self.assertEqual(created, cache_path)
        self.assertTrue(cache_path.exists())

        # Unshare
        await unshare_media(
            media_id=media.id,
            current_user=self.admin_user,
            db=self.db,
        )
        self.assertFalse(cache_path.exists())

    async def test_dead_cache_sweep_preserves_live_shared_entries(self):
        # 1. Transcoded shared media
        self._create_image_file("media/original/live1.heic")
        self._create_image_file("media/transcoded/live1.webp")
        media1 = self._create_media(
            filename="live1.heic",
            rel_path="media/original/live1.heic",
            media_hash="hash_live_transcoded",
            transcoded_path="media/transcoded/live1.webp",
            mime_type="image/heic",
            is_shared=True,
        )
        cache1 = await create_stripped_media_cache(media1, "image/webp")
        self.assertTrue(cache1.exists())

        # 2. Non-transcoded shared media
        self._create_image_file("media/original/live2.png")
        media2 = self._create_media(
            filename="live2.png",
            rel_path="media/original/live2.png",
            media_hash="hash_live_plain",
            transcoded_path=None,
            mime_type="image/png",
            is_shared=True,
        )
        cache2 = await create_stripped_media_cache(media2, "image/png")
        self.assertTrue(cache2.exists())

        # Run sweep
        deleted = cleanup_dead_media_cache(self.db)
        self.assertEqual(deleted, 0)
        self.assertTrue(cache1.exists())
        self.assertTrue(cache2.exists())

    async def test_dead_cache_sweep_deletes_orphaned_entry_not_in_db(self):
        # Create an orphaned file directly in stripped cache dir
        orphan_file = settings.STRIPPED_CACHE_DIR / "ghost_hash_999.png"
        orphan_file.write_bytes(b"ORPHAN_DATA")
        self.assertTrue(orphan_file.exists())

        # Create also an in-progress .tmp file which should NOT be deleted
        tmp_file = settings.STRIPPED_CACHE_DIR / "inprogress.tmp"
        tmp_file.write_bytes(b"TMP_DATA")

        deleted = cleanup_dead_media_cache(self.db)
        self.assertGreaterEqual(deleted, 1)
        self.assertFalse(orphan_file.exists())
        self.assertTrue(tmp_file.exists())

    async def test_dead_cache_sweep_cleans_legacy_loose_files(self):
        # Legacy files stored directly in CACHE_DIR instead of stripped/
        legacy_file = settings.CACHE_DIR / "legacy_md5hash_photo.png"
        legacy_file.write_bytes(b"LEGACY_DATA")
        self.assertTrue(legacy_file.exists())

        deleted = cleanup_dead_media_cache(self.db)
        self.assertGreaterEqual(deleted, 1)
        self.assertFalse(legacy_file.exists())

    async def test_toggle_share_ai_metadata_re_generates_when_turned_on(self):
        self._create_image_file("media/original/meta.png")
        media = self._create_media(
            filename="meta.png",
            rel_path="media/original/meta.png",
            media_hash="hash_meta_toggle",
            is_shared=True,
            share_ai_metadata=False,
        )

        cache_path = await create_stripped_media_cache(media, "image/png")
        self.assertTrue(cache_path.exists())

        # Toggle share_ai_metadata to True (strip metadata turned off: full metadata shared)
        # Old stripped cache should be deleted
        await update_share_settings(
            media_id=media.id,
            updates=ShareSettingsUpdate(share_ai_metadata=True),
            current_user=self.admin_user,
            db=self.db,
        )
        self.assertFalse(cache_path.exists())

        # Toggle back to False (strip metadata switch flipped to on)
        # Stripped metadata cache should be immediately re-generated!
        await update_share_settings(
            media_id=media.id,
            updates=ShareSettingsUpdate(share_ai_metadata=False),
            current_user=self.admin_user,
            db=self.db,
        )
        self.assertTrue(cache_path.exists())

        # Toggle back to True
        await update_share_settings(
            media_id=media.id,
            updates=ShareSettingsUpdate(share_ai_metadata=True),
            current_user=self.admin_user,
            db=self.db,
        )
        self.assertFalse(cache_path.exists())

        # Toggle back to False with explicit BackgroundTasks
        bg = BackgroundTasks()
        await update_share_settings(
            media_id=media.id,
            updates=ShareSettingsUpdate(share_ai_metadata=False),
            background_tasks=bg,
            current_user=self.admin_user,
            db=self.db,
        )
        await bg()
        self.assertTrue(cache_path.exists())

    async def test_migrate_legacy_stripped_cache_migrates_active_and_removes_unused(self):
        # 1. Create active shared media with strip metadata enabled (share_ai_metadata=False)
        self._create_image_file("media/original/active_photo.png")
        media_active = self._create_media(
            filename="active_photo.png",
            rel_path="media/original/active_photo.png",
            media_hash="active_hash_123",
            is_shared=True,
            share_ai_metadata=False,
        )

        # 2. Create unshared media
        self._create_image_file("media/original/unshared_photo.png")
        media_unshared = self._create_media(
            filename="unshared_photo.png",
            rel_path="media/original/unshared_photo.png",
            media_hash="unshared_hash_456",
            is_shared=False,
            share_ai_metadata=False,
        )

        # 3. Create shared media but with AI metadata enabled (share_ai_metadata=True, so stripped cache not needed)
        self._create_image_file("media/original/full_meta_photo.png")
        media_full = self._create_media(
            filename="full_meta_photo.png",
            rel_path="media/original/full_meta_photo.png",
            media_hash="full_meta_hash_789",
            is_shared=True,
            share_ai_metadata=True,
        )

        # Populate legacy files directly in CACHE_DIR
        legacy_active = settings.CACHE_DIR / "11112222333344445555666677778888_active_photo.png"
        legacy_active.write_bytes(b"ACTIVE_STRIPPED_LEGACY_CONTENT")

        legacy_unshared = settings.CACHE_DIR / "22223333444455556666777788889999_unshared_photo.png"
        legacy_unshared.write_bytes(b"UNSHARED_LEGACY_CONTENT")

        legacy_full = settings.CACHE_DIR / "33334444555566667777888899990000_full_meta_photo.png"
        legacy_full.write_bytes(b"FULL_META_LEGACY_CONTENT")

        legacy_orphan = settings.CACHE_DIR / "44445555666677778888999900001111_nonexistent.png"
        legacy_orphan.write_bytes(b"ORPHAN_LEGACY_CONTENT")

        # Run migration
        res = migrate_legacy_stripped_cache(self.db)
        self.assertEqual(res["migrated"], 1)
        self.assertEqual(res["removed"], 3)

        # Active file should be migrated to STRIPPED_CACHE_DIR
        migrated_path = settings.STRIPPED_CACHE_DIR / "active_hash_123.png"
        self.assertTrue(migrated_path.exists())
        self.assertEqual(migrated_path.read_bytes(), b"ACTIVE_STRIPPED_LEGACY_CONTENT")
        self.assertFalse(legacy_active.exists())

        # Unshared, full-metadata, and orphaned legacy files should be removed
        self.assertFalse(legacy_unshared.exists())
        self.assertFalse(legacy_full.exists())
        self.assertFalse(legacy_orphan.exists())

    async def test_on_demand_legacy_migration_via_create_stripped_media_cache(self):
        self._create_image_file("media/original/ondemand.png")
        media = self._create_media(
            filename="ondemand.png",
            rel_path="media/original/ondemand.png",
            media_hash="ondemand_hash_555",
            is_shared=True,
            share_ai_metadata=False,
        )

        legacy_file = settings.CACHE_DIR / "aaaaabbbbbcccccdddddeeeeefffff00_ondemand.png"
        legacy_file.write_bytes(b"ONDEMAND_LEGACY_PAYLOAD")

        target_cache = settings.STRIPPED_CACHE_DIR / "ondemand_hash_555.png"
        self.assertFalse(target_cache.exists())

        # Calling create_stripped_media_cache should migrate the legacy file on demand
        cached = await create_stripped_media_cache(media, "image/png")
        self.assertEqual(cached, target_cache)
        self.assertTrue(target_cache.exists())
        self.assertEqual(target_cache.read_bytes(), b"ONDEMAND_LEGACY_PAYLOAD")
        self.assertFalse(legacy_file.exists())

    async def test_renaming_media_preserves_cache_entry(self):
        orig = self._create_image_file("media/original/initial.png")
        media = self._create_media(
            filename="initial.png",
            rel_path="media/original/initial.png",
            media_hash="hash_rename_test",
            is_shared=True,
        )

        cache_path = await create_stripped_media_cache(media, "image/png")
        self.assertTrue(cache_path.exists())

        # Rename file on disk and update model path/filename (hash remains unchanged)
        new_path = self.base_path / "media/original/renamed.png"
        orig.rename(new_path)
        media.filename = "renamed.png"
        media.path = "media/original/renamed.png"
        self.db.commit()

        # Cache path still resolves to hash_rename_test.png and exists
        resolved_cache = get_stripped_cache_path(media)
        self.assertEqual(resolved_cache, cache_path)
        self.assertTrue(resolved_cache.exists())

        # Dead cache sweep does not delete it
        cleanup_dead_media_cache(self.db)
        self.assertTrue(resolved_cache.exists())

    async def test_concurrent_stripped_cache_generation_deduplicates(self):
        from starlette.concurrency import run_in_threadpool

        self._create_image_file("media/original/concurrent.png")
        media = self._create_media(
            filename="concurrent.png",
            rel_path="media/original/concurrent.png",
            media_hash="hash_concurrent_lock",
            is_shared=True,
        )

        process_count = 0
        real_run = run_in_threadpool

        async def slow_run(func, *args, **kwargs):
            nonlocal process_count
            if getattr(func, "__name__", "") == "process_image":
                process_count += 1
            await asyncio.sleep(0.05)
            return await real_run(func, *args, **kwargs)

        with patch("backend.app.utils.media_helpers.run_in_threadpool", side_effect=slow_run):
            # Run two concurrent tasks
            task1 = asyncio.create_task(create_stripped_media_cache(media, "image/png"))
            task2 = asyncio.create_task(create_stripped_media_cache(media, "image/png"))

            res1, res2 = await asyncio.gather(task1, task2)

        self.assertEqual(res1, res2)
        self.assertIsNotNone(res1)
        self.assertTrue(res1.exists())
        # Deduplication lock ensured only 1 image generation occurred
        self.assertEqual(process_count, 1)

    async def test_get_media_cache_status_defensive_guard(self):
        # Missing file returns error
        missing_path = self.base_path / "does_not_exist.png"
        status_missing = get_media_cache_status(missing_path, "image/png")
        self.assertEqual(status_missing, "error")

        # Non-image mime returns not_stripped
        status_video = get_media_cache_status(missing_path, "video/mp4")
        self.assertEqual(status_video, "not_stripped")

        # Existing media not yet cached returns processing
        real_file = self._create_image_file("media/original/guard.png")
        media = self._create_media(
            filename="guard.png",
            rel_path="media/original/guard.png",
            media_hash="hash_guard_test",
            is_shared=True,
        )
        self.assertEqual(get_media_cache_status(media, "image/png"), "processing")

        # Cached returns ready
        await create_stripped_media_cache(media, "image/png")
        self.assertEqual(get_media_cache_status(media, "image/png"), "ready")

    async def test_cache_stats_and_lru_eviction(self):
        file1 = settings.STRIPPED_CACHE_DIR / "entry1.png"
        file2 = settings.STRIPPED_CACHE_DIR / "entry2.png"
        # Write ~1.2 MB to each file
        chunk = b"X" * (1024 * 1024 + 200 * 1024)
        file1.write_bytes(chunk)
        file2.write_bytes(chunk)

        stats = get_stripped_cache_stats()
        self.assertEqual(stats["count"], 2)
        self.assertGreater(stats["size_bytes"], 2 * 1024 * 1024)

        # Set older mtime on entry1
        import os
        os.utime(file1, (1000, 1000))
        os.utime(file2, (2000, 2000))

        # Evict with limit of 2 MB (total is ~2.4 MB, so entry1 should be evicted and entry2 kept)
        evicted = evict_stripped_cache_if_needed(max_mb=2)
        self.assertEqual(evicted, 1)
        self.assertFalse(file1.exists())
        self.assertTrue(file2.exists())

        # Test with limit disabled (0)
        settings.file_settings["stripped_cache_max_mb"] = 0
        self.assertEqual(evict_stripped_cache_if_needed(), 0)

    async def test_admin_cache_endpoints(self):
        # 1. Add some files to stripped cache
        f = settings.STRIPPED_CACHE_DIR / "admin_test.png"
        f.write_bytes(b"TEST_BYTES_FOR_ADMIN")

        stats = await get_cache_stats(current_user=self.admin_user)
        self.assertGreaterEqual(stats["count"], 1)
        self.assertGreaterEqual(stats["size_bytes"], 20)

        # 2. Clear cache endpoint
        clear_res = await clear_cache(current_user=self.admin_user, db=self.db)
        self.assertIn("deleted", clear_res)
        self.assertFalse(f.exists())

    async def test_replacing_media_file_invalidates_old_cache_and_generates_new(self):
        orig = self._create_image_file("media/original/replace_me.png", color="red")
        media = self._create_media(
            filename="replace_me.png",
            rel_path="media/original/replace_me.png",
            media_hash="hash_initial_replacement",
            is_shared=True,
        )

        old_cache = await create_stripped_media_cache(media, "image/png")
        self.assertTrue(old_cache.exists())

        # Invalidate old cache as done in update_file flow
        delete_media_cache(media)
        self.assertFalse(old_cache.exists())

        # Now media hash changes
        new_file = self._create_image_file("media/original/replace_me.png", color="green")
        media.hash = "hash_new_replacement"
        self.db.commit()

        new_cache = await create_stripped_media_cache(media, "image/png")
        self.assertTrue(new_cache.exists())
        self.assertEqual(new_cache, settings.STRIPPED_CACHE_DIR / "hash_new_replacement.png")
        self.assertNotEqual(old_cache, new_cache)

    async def test_rebuild_stripped_cache_if_needed(self):
        # 1. Unshared media: should return None and not create cache
        self._create_image_file("media/original/unshared_rebuild.png")
        media_unshared = self._create_media(
            filename="unshared_rebuild.png",
            rel_path="media/original/unshared_rebuild.png",
            media_hash="hash_unshared_rebuild",
            is_shared=False,
            share_ai_metadata=False,
        )
        res = await rebuild_stripped_cache_if_needed(media_unshared)
        self.assertIsNone(res)
        self.assertFalse((settings.STRIPPED_CACHE_DIR / "hash_unshared_rebuild.png").exists())

        # 2. Shared media with AI metadata shared: should return None
        self._create_image_file("media/original/fullmeta_rebuild.png")
        media_fullmeta = self._create_media(
            filename="fullmeta_rebuild.png",
            rel_path="media/original/fullmeta_rebuild.png",
            media_hash="hash_fullmeta_rebuild",
            is_shared=True,
            share_ai_metadata=True,
        )
        res = await rebuild_stripped_cache_if_needed(media_fullmeta)
        self.assertIsNone(res)
        self.assertFalse((settings.STRIPPED_CACHE_DIR / "hash_fullmeta_rebuild.png").exists())

        # 3. Shared media with strip metadata on: should rebuild cache
        self._create_image_file("media/original/shared_rebuild.png")
        media_shared = self._create_media(
            filename="shared_rebuild.png",
            rel_path="media/original/shared_rebuild.png",
            media_hash="hash_shared_rebuild",
            is_shared=True,
            share_ai_metadata=False,
        )
        res = await rebuild_stripped_cache_if_needed(media_shared)
        self.assertIsNotNone(res)
        self.assertTrue(res.exists())
        self.assertEqual(res, settings.STRIPPED_CACHE_DIR / "hash_shared_rebuild.png")

        # 4. With BackgroundTasks
        res.unlink()
        bg = BackgroundTasks()
        await rebuild_stripped_cache_if_needed(media_shared, background_tasks=bg)
        self.assertFalse(res.exists())
        await bg()
        self.assertTrue(res.exists())

    async def test_cache_locks_dict_does_not_leak(self):
        for i in range(5):
            self._create_image_file(f"media/original/lock_leak_{i}.png")
            m = self._create_media(
                filename=f"lock_leak_{i}.png",
                rel_path=f"media/original/lock_leak_{i}.png",
                media_hash=f"hash_lock_leak_{i}",
                is_shared=True,
                share_ai_metadata=False,
            )
            cache_p = await create_stripped_media_cache(m, "image/png")
            self.assertTrue(cache_p.exists())

        # All lock entries must have been cleaned up
        self.assertEqual(len(_cache_locks), 0)

    async def test_future_mtime_or_clock_skew_does_not_loop_processing(self):
        import os
        orig = self._create_image_file("media/original/future_clock.png", color="red")
        media = self._create_media(
            filename="future_clock.png",
            rel_path="media/original/future_clock.png",
            media_hash="hash_future_clock",
            is_shared=True,
            share_ai_metadata=False,
        )

        # Set source file mtime 1 hour into the future (simulating clock skew or preserved upload timestamp)
        import time
        future_time = time.time() + 3600
        os.utime(orig, (future_time, future_time))

        cache_path = await create_stripped_media_cache(media, "image/png")
        self.assertTrue(cache_path.exists())

        # Status must report 'ready', not perpetually 'processing'
        status = get_media_cache_status(media, "image/png")
        self.assertEqual(status, "ready")

    async def test_lru_touch_on_access_updates_mtime_and_protects_from_eviction(self):
        import os
        orig1 = self._create_image_file("media/original/lru_test1.png")
        media1 = self._create_media(
            filename="lru_test1.png",
            rel_path="media/original/lru_test1.png",
            media_hash="hash_lru_1",
            is_shared=True,
            share_ai_metadata=False,
        )
        orig2 = self._create_image_file("media/original/lru_test2.png")
        media2 = self._create_media(
            filename="lru_test2.png",
            rel_path="media/original/lru_test2.png",
            media_hash="hash_lru_2",
            is_shared=True,
            share_ai_metadata=False,
        )

        file1 = await create_stripped_media_cache(media1, "image/png")
        file2 = await create_stripped_media_cache(media2, "image/png")

        # Artificially set file1 and file2 mtimes to old timestamps
        os.utime(file1, (1000, 1000))
        os.utime(file2, (1500, 1500))

        # Access file1 via create_stripped_media_cache (cache hit)
        hit_file = await create_stripped_media_cache(media1, "image/png")
        self.assertEqual(hit_file, file1)
        # file1 mtime should now be updated to current time (greater than 1500)
        self.assertGreater(file1.stat().st_mtime, 1500)

        # Pad file1 and file2 to ~1.2 MB each
        file1.write_bytes(file1.read_bytes() + b"\x00" * (1200 * 1024))
        file2.write_bytes(file2.read_bytes() + b"\x00" * (1200 * 1024))
        # Keep file2 mtime at 1500, file1 at recent
        os.utime(file2, (1500, 1500))

        # Evict with limit of 2 MB: file2 (least recently accessed) should be evicted
        evicted = evict_stripped_cache_if_needed(max_mb=2)
        self.assertEqual(evicted, 1)
        self.assertFalse(file2.exists())
        self.assertTrue(file1.exists())

    async def test_noop_filename_update_does_not_rebuild_cache(self):
        self._create_image_file("media/original/noop_rename.png")
        media = self._create_media(
            filename="noop_rename.png",
            rel_path="media/original/noop_rename.png",
            media_hash="hash_noop_rename",
            is_shared=True,
            share_ai_metadata=False,
        )

        cache_path = await create_stripped_media_cache(media, "image/png")
        self.assertTrue(cache_path.exists())
        
        # Write marker bytes into cache file to detect if it gets overwritten
        marker = b"MARKER_CACHE_CONTENT"
        cache_path.write_bytes(marker)

        req = PostUpdateRequest(
            update_filename=True,
            filename="noop_rename.png",  # Same filename
        )

        await update_from_source(
            media_id=media.id,
            req=req,
            current_user=self.admin_user,
            db=self.db,
        )

        # Cache file must not have been deleted or rebuilt
        self.assertTrue(cache_path.exists())
        self.assertEqual(cache_path.read_bytes(), marker)

    async def test_update_from_source_auto_rebuilds_stripped_cache_for_shared_media(self):
        orig = self._create_image_file("media/original/update_test.png", color="red")
        media = self._create_media(
            filename="update_test.png",
            rel_path="media/original/update_test.png",
            media_hash="hash_before_update",
            is_shared=True,
            share_ai_metadata=False,
        )

        old_cache = await create_stripped_media_cache(media, "image/png")
        self.assertTrue(old_cache.exists())
        self.assertEqual(old_cache, settings.STRIPPED_CACHE_DIR / "hash_before_update.png")

        # Prepare replacement image
        new_img = Image.new("RGB", (100, 100), color="blue")
        buf = io.BytesIO()
        new_img.save(buf, format="PNG")
        new_bytes = buf.getvalue()

        with patch("backend.app.routes.media.safe_request") as mock_get:
            mock_resp = MagicMock()
            mock_resp.iter_content = lambda chunk_size: [new_bytes]
            mock_resp.raise_for_status = MagicMock()
            mock_get.return_value = mock_resp

            req = PostUpdateRequest(
                update_file=True,
                file_url="http://example.com/replacement.png",
            )

            await update_from_source(
                media_id=media.id,
                req=req,
                current_user=self.admin_user,
                db=self.db,
            )

        self.db.refresh(media)
        # Old cache must be gone
        self.assertFalse(old_cache.exists())
        # New cache must be automatically rebuilt
        new_cache = settings.STRIPPED_CACHE_DIR / f"{media.hash}.png"
        self.assertTrue(new_cache.exists())

    async def test_post_lock_legacy_migration_returns_immediately_without_reencode(self):
        self._create_image_file("media/original/post_lock_mig.png")
        media = self._create_media(
            filename="post_lock_mig.png",
            rel_path="media/original/post_lock_mig.png",
            media_hash="hash_post_lock_mig",
            is_shared=True,
            share_ai_metadata=False,
        )

        target_cache = settings.STRIPPED_CACHE_DIR / "hash_post_lock_mig.png"
        self.assertFalse(target_cache.exists())

        call_count = 0

        def selective_migrate(m_or_p, target):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return False  # Pre-lock check returns False
            # Post-lock check succeeds: create target file and return True
            target.write_bytes(b"MIGRATED_POST_LOCK_DATA")
            return True

        with patch("backend.app.utils.media_helpers.find_and_migrate_legacy_cache_file", side_effect=selective_migrate):
            with patch("PIL.Image.open") as mock_open:
                res = await create_stripped_media_cache(media, "image/png")
                self.assertEqual(res, target_cache)
                self.assertTrue(target_cache.exists())
                self.assertEqual(target_cache.read_bytes(), b"MIGRATED_POST_LOCK_DATA")
                # Image.open should NOT have been called because migration returned immediately
                mock_open.assert_not_called()
