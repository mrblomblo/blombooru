import asyncio
import threading
import time
import unittest
from unittest.mock import MagicMock

from fastapi import HTTPException

from backend.app.enums import FileTypeEnum, RatingEnum, TagCategoryEnum
from backend.app.models import Album, Media, Tag, TagAlias, TagImplication, User
from backend.app.routes.admin.maintenance import (
    get_all_maintenance_statuses,
    get_maintenance_job_status,
)
from backend.app.routes.admin.media import (
    _maintenance_lock,
    _transcode_status,
    generate_missing_thumbnails,
    regenerate_all_thumbnails,
    relink_media,
)
from backend.app.routes.admin.tags import (
    simulate_apply_aliases,
    simulate_apply_tag_ratings,
)
from backend.app.routes.albums import (
    prune_all_albums_endpoint,
    recalculate_all_albums_endpoint,
)
from backend.app.routes.tag_implications import (
    backfill_implied_tags,
    simulate_apply_all_implications,
)
from backend.app.services import near_duplicates
from backend.app.services.maintenance_jobs import MaintenanceJobManager, maintenance_jobs
from tests.test_base import BlombooruTestSandboxMixin, make_dummy_jpeg

class TestMaintenanceJobManager(unittest.TestCase):
    def test_start_progress_completion_and_lock_contention(self):
        mgr = MaintenanceJobManager()
        shared_lock = threading.Lock()
        mgr.register("job_a", {"count": 0})
        mgr.register("job_b")

        started_gate = threading.Event()
        finish_gate = threading.Event()

        def worker_a(progress_cb):
            progress_cb(total=2, current=1, count=1, current_file="one.jpg")
            started_gate.set()
            finish_gate.wait(timeout=5)
            return {"done": True}

        started, snap = mgr.start_job("job_a", worker_a, execution_lock=shared_lock)
        self.assertTrue(started)
        self.assertTrue(snap["running"])
        self.assertTrue(started_gate.wait(timeout=2))

        # Re-starting the same running job returns (False, snapshot) instead of spawning another
        started_again, snap_again = mgr.start_job("job_a", worker_a, execution_lock=shared_lock)
        self.assertFalse(started_again)
        self.assertTrue(snap_again["running"])
        self.assertEqual(snap_again["current_file"], "one.jpg")

        # Starting a different job sharing the same execution lock raises 409
        with self.assertRaises(HTTPException) as ctx:
            mgr.start_job("job_b", lambda _cb: None, execution_lock=shared_lock)
        self.assertEqual(ctx.exception.status_code, 409)

        finish_gate.set()
        for _ in range(100):
            st = mgr.get_status("job_a", include_result=True)
            if not st["running"]:
                break
            time.sleep(0.02)

        final = mgr.get_status("job_a", include_result=True)
        self.assertFalse(final["running"])
        self.assertIsNone(final["error"])
        self.assertEqual(final["result"], {"done": True})
        self.assertIsNotNone(final["finished_at"])

        # Summary list omits large result payload
        summaries = mgr.get_all_statuses()
        self.assertNotIn("result", summaries["job_a"])

    def test_worker_error_records_error_and_releases_lock(self):
        mgr = MaintenanceJobManager()
        lock = threading.Lock()
        mgr.register("failing")

        def boom(_cb):
            raise RuntimeError("boom")

        started, _ = mgr.start_job("failing", boom, execution_lock=lock)
        self.assertTrue(started)
        for _ in range(100):
            st = mgr.get_status("failing")
            if not st["running"]:
                break
            time.sleep(0.02)

        st = mgr.get_status("failing")
        self.assertFalse(st["running"])
        self.assertEqual(st["error"], "boom")
        self.assertFalse(lock.locked())

class TestAdminMaintenanceBackgroundEndpoints(BlombooruTestSandboxMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.setup_sandbox()
        self.admin_user = MagicMock(spec=User)
        self.admin_user.id = 1
        self.admin_user.is_admin = True

    def tearDown(self):
        self._wait_for_all_jobs()
        self.teardown_sandbox()
        super().tearDown()

    def _wait_for_all_jobs(self, timeout: float = 5.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            statuses = maintenance_jobs.get_all_statuses()
            if not any(s.get("running") for s in statuses.values()):
                return
            time.sleep(0.02)

    def _wait_for_job(self, job_name: str, timeout: float = 5.0) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            status = asyncio.run(
                get_maintenance_job_status(job_name=job_name, current_user=self.admin_user)
            )
            if not status["running"]:
                return status
            time.sleep(0.02)
        self.fail(f"Timed out waiting for maintenance job '{job_name}'")

    def _seed_sample_image(self, filename: str = "sample.jpg", media_hash: str = "hash1") -> Media:
        img_bytes = make_dummy_jpeg()
        rel_path = f"media/original/{filename}"
        abs_path = self.tmp_path / rel_path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_bytes(img_bytes)

        media = Media(
            filename=filename,
            path=rel_path,
            hash=media_hash,
            file_type=FileTypeEnum.image,
            mime_type="image/jpeg",
            file_size=len(img_bytes),
            rating=RatingEnum.safe,
        )
        self.db.add(media)
        self.db.commit()
        self.db.refresh(media)
        return media

    def test_status_endpoint_lists_all_maintenance_jobs_and_rejects_unknown(self):
        res = asyncio.run(get_all_maintenance_statuses(current_user=self.admin_user))
        jobs = res["jobs"]
        expected = {
            "generate_missing_thumbnails",
            "regenerate_all_thumbnails",
            "relink_media",
            "transcode_media",
            "near_duplicate_backfill",
            "apply_aliases",
            "apply_implications",
            "backfill_implied_tags",
            "apply_tag_ratings",
            "recalculate_album_metrics",
            "prune_albums",
        }
        self.assertTrue(expected.issubset(set(jobs.keys())))

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(get_maintenance_job_status(job_name="does_not_exist", current_user=self.admin_user))
        self.assertEqual(ctx.exception.status_code, 404)

    def test_status_endpoint_reflects_running_transcode_and_near_duplicate(self):
        prev_transcode = dict(_transcode_status)
        prev_backfill = dict(near_duplicates._backfill_state)
        try:
            _transcode_status["running"] = True
            near_duplicates._backfill_state["running"] = True

            res = asyncio.run(get_all_maintenance_statuses(current_user=self.admin_user))
            self.assertTrue(res["jobs"]["transcode_media"]["running"])
            self.assertTrue(res["jobs"]["near_duplicate_backfill"]["running"])
        finally:
            _transcode_status.clear()
            _transcode_status.update(prev_transcode)
            near_duplicates._backfill_state.clear()
            near_duplicates._backfill_state.update(prev_backfill)

    def test_media_maintenance_jobs_background_execution(self):
        self._seed_sample_image("thumb_test.jpg", "hash_thumb")

        res_missing = asyncio.run(
            generate_missing_thumbnails(background=True, current_user=self.admin_user)
        )
        self.assertEqual(res_missing["status"], "started")
        final_missing = self._wait_for_job("generate_missing_thumbnails")
        self.assertIsNone(final_missing["error"])
        self.assertEqual(final_missing["result"]["generated"], 1)

        res_regen = asyncio.run(
            regenerate_all_thumbnails(background=True, current_user=self.admin_user)
        )
        self.assertEqual(res_regen["status"], "started")
        final_regen = self._wait_for_job("regenerate_all_thumbnails")
        self.assertIsNone(final_regen["error"])
        self.assertEqual(final_regen["result"]["generated"], 1)
        self.assertEqual(final_regen["result"]["deleted"], 1)

        res_relink = asyncio.run(relink_media(background=True, current_user=self.admin_user))
        self.assertEqual(res_relink["status"], "started")
        final_relink = self._wait_for_job("relink_media")
        self.assertIsNone(final_relink["error"])
        self.assertEqual(final_relink["result"]["relinked"], 0)
        self.assertFalse(_maintenance_lock.locked())

    def test_tag_maintenance_jobs_background_execution(self):
        media = self._seed_sample_image("tag_test.jpg", "hash_tag")
        old_tag = Tag(name="old_name", category=TagCategoryEnum.general)
        new_tag = Tag(name="new_name", category=TagCategoryEnum.general)
        implied_tag = Tag(name="implied_name", category=TagCategoryEnum.general)
        rated_tag = Tag(name="nsfw_tag", category=TagCategoryEnum.general, rating="explicit")
        self.db.add_all([old_tag, new_tag, implied_tag, rated_tag])
        self.db.flush()

        self.db.add(TagAlias(alias_name="old_name", target_tag_id=new_tag.id))
        imp = TagImplication()
        imp.target_tags.append(new_tag)
        imp.implied_tags.append(implied_tag)
        self.db.add(imp)

        media.tags.extend([old_tag, rated_tag])
        self.db.commit()

        # 1. apply_aliases
        res_aliases = asyncio.run(
            simulate_apply_aliases(background=True, current_user=self.admin_user)
        )
        self.assertEqual(res_aliases["status"], "started")
        final_aliases = self._wait_for_job("apply_aliases")
        self.assertIsNone(final_aliases["error"])
        self.assertEqual(len(final_aliases["result"]["affected_media"]), 1)

        # 2. apply_tag_ratings
        res_ratings = asyncio.run(
            simulate_apply_tag_ratings(background=True, current_user=self.admin_user)
        )
        self.assertEqual(res_ratings["status"], "started")
        final_ratings = self._wait_for_job("apply_tag_ratings")
        self.assertIsNone(final_ratings["error"])
        self.assertEqual(len(final_ratings["result"]["affected_media"]), 1)
        self.assertEqual(final_ratings["result"]["affected_media"][0]["new_rating"], "explicit")

        # 3. apply_implications & backfill_implied_tags
        media.tags.append(new_tag)
        self.db.commit()

        res_imp = asyncio.run(
            simulate_apply_all_implications(background=True, current_user=self.admin_user)
        )
        self.assertEqual(res_imp["status"], "started")
        final_imp = self._wait_for_job("apply_implications")
        self.assertIsNone(final_imp["error"])
        self.assertEqual(final_imp["result"]["affected_media"][0]["added_tags"], ["implied_name"])

        media.tags.append(implied_tag)
        self.db.commit()

        res_backfill = asyncio.run(
            backfill_implied_tags(background=True, current_user=self.admin_user)
        )
        self.assertEqual(res_backfill["status"], "started")
        final_backfill = self._wait_for_job("backfill_implied_tags")
        self.assertIsNone(final_backfill["error"])
        self.assertEqual(final_backfill["result"]["updated_tags_count"], 1)

    def test_album_maintenance_jobs_background_execution(self):
        empty_album = Album(name="Empty Album")
        self.db.add(empty_album)
        self.db.commit()

        res_recalc = asyncio.run(
            recalculate_all_albums_endpoint(
                background=True, current_user=self.admin_user, db=self.db
            )
        )
        self.assertEqual(res_recalc["status"], "started")
        final_recalc = self._wait_for_job("recalculate_album_metrics")
        self.assertIsNone(final_recalc["error"])
        self.assertIn("recalculated", final_recalc["result"]["message"])

        res_prune = asyncio.run(
            prune_all_albums_endpoint(
                background=True, current_user=self.admin_user, db=self.db
            )
        )
        self.assertEqual(res_prune["status"], "started")
        final_prune = self._wait_for_job("prune_albums")
        self.assertIsNone(final_prune["error"])
        self.assertEqual(final_prune["result"]["count"], 1)

if __name__ == "__main__":
    unittest.main()
