import asyncio
import io
import json
import unittest
import zipfile

import numpy as np
from PIL import Image, ImageDraw, ImageOps
from starlette.datastructures import UploadFile

from backend.app.config import APP_VERSION, SCHEMA_VERSION, settings
from backend.app.enums import FileTypeEnum, RatingEnum
from backend.app.models import Media, User
from backend.app.routes.admin.backup import backup_full_db
from backend.app.routes.uploads import (commit_upload_session,
                                        create_upload_session,
                                        delete_staged_item,
                                        get_session_near_duplicates,
                                        update_staged_item,
                                        upload_files_to_session)
from backend.app.schemas import UploadSessionItemUpdate
from backend.app.services import near_duplicates as nd
from backend.app.utils import perceptual_hash as ph
from backend.app.utils.backup import import_full_backup
from tests.test_base import AsyncBackupTestBase, BackupTestBase

def make_structured_image(seed: int, size=(640, 480)) -> Image.Image:
    """Deterministic multi-scale noise plus shapes: stands in for 'real' artwork."""
    rng = np.random.default_rng(seed)
    w, h = size
    acc = np.zeros((h, w, 3), dtype=np.float32)
    for scale, amp in ((4, 120), (8, 60), (16, 30), (32, 15)):
        small = rng.random((scale * h // w + 2, scale + 2, 3)).astype(np.float32)
        big = Image.fromarray((small * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC)
        acc += (np.asarray(big, dtype=np.float32) - 127.5) / 255 * amp
    img = Image.fromarray(np.clip(acc + 128, 0, 255).astype(np.uint8))
    draw = ImageDraw.Draw(img)
    for _ in range(6):
        x, y, r = int(rng.integers(0, w)), int(rng.integers(0, h)), int(rng.integers(30, 120))
        draw.ellipse((x - r, y - r, x + r, y + r), fill=tuple(int(v) for v in rng.integers(0, 255, 3)))
    return img

def to_bytes(img: Image.Image, fmt="PNG", **kwargs) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format=fmt, **kwargs)
    return buf.getvalue()

class TestPerceptualHash(unittest.TestCase):
    def test_hex_and_words_roundtrip(self):
        samples = (
            0,
            1,
            (1 << 128) - 1,
            1 << 255,
            (1 << 256) - 1,
            int("902a83293fbe25f5" * 4, 16),
        )
        for value in samples:
            hex_str = ph.phash_to_hex(value)
            self.assertEqual(len(hex_str), 64)
            self.assertEqual(ph.phash_from_hex(hex_str), value)
            words = ph.phash_to_words(value)
            self.assertEqual(words.shape, (4,))
            self.assertEqual(words.dtype, np.uint64)
            reconstructed = int.from_bytes(words.astype(">u8").tobytes(), "big")
            self.assertEqual(reconstructed, value)
        self.assertIsNone(ph.phash_from_hex(None))
        self.assertIsNone(ph.phash_from_hex("not-hex"))
        self.assertIsNone(ph.phash_from_hex("0123456789abcdef"))  # 16-char legacy pHash rejected

    def test_hamming_distance_and_similarity(self):
        self.assertEqual(ph.hamming_distance(0, 0), 0)
        self.assertEqual(ph.hamming_distance(0b1011, 0b0001), 2)
        self.assertEqual(ph.hamming_distance(0, (1 << 256) - 1), 256)
        self.assertEqual(ph.similarity_percent(0), 100.0)
        self.assertEqual(ph.similarity_percent(256), 0.0)

    def test_mirror_phash_is_involution_and_128_bits_away(self):
        value = int("0123456789abcdef" * 4, 16)
        mirrored = ph.mirror_phash(value)
        self.assertEqual(ph.mirror_phash(mirrored), value)
        self.assertEqual(ph.hamming_distance(value, mirrored), 128)
        self.assertEqual(ph.mirror_hamming_distance(value, mirrored), 0)

    def test_popcount_matches_reference_for_both_implementations(self):
        rng = np.random.default_rng(0)
        values = rng.integers(0, 1 << 63, (200, 4), dtype=np.int64).astype(np.uint64) * np.uint64(2) + np.uint64(1)
        expected64 = np.vectorize(lambda v: int(v).bit_count(), otypes=[np.uint8])(values)
        np.testing.assert_array_equal(nd.popcount64(values), expected64)
        table = nd._POPCOUNT_TABLE[np.ascontiguousarray(values).view(np.uint8).reshape(values.shape + (8,))].sum(axis=-1)
        np.testing.assert_array_equal(table.astype(np.uint8), expected64)
        np.testing.assert_array_equal(nd.popcount256(values), expected64.sum(axis=-1, dtype=np.uint16))

    def test_variants_mirror_and_letterbox_are_close_and_unrelated_images_are_far(self):
        base = make_structured_image(1)
        h_base = ph.compute_phash_from_image(base)
        variants = {
            "downscaled": base.resize((320, 240), Image.LANCZOS),
            "upscaled": base.resize((1280, 960), Image.BICUBIC),
            "odd size": base.resize((317, 241), Image.BILINEAR),
            "jpeg": Image.open(io.BytesIO(to_bytes(base, "JPEG", quality=35))),
            "mirrored": ImageOps.mirror(base),
            "letterboxed_black": ImageOps.expand(base, border=(0, 90, 0, 90), fill=(0, 0, 0)),
            "pillarboxed_white": ImageOps.expand(base, border=(100, 0, 100, 0), fill=(255, 255, 255)),
            "framed_4_sides": ImageOps.expand(base, border=(60, 80, 60, 80), fill=(0, 0, 0)),
        }
        for name, variant in variants.items():
            distance = ph.mirror_hamming_distance(h_base, ph.compute_phash_from_image(variant))
            self.assertLessEqual(distance, 16, name)
        for seed in range(2, 8):
            other = ph.compute_phash_from_image(make_structured_image(seed))
            self.assertGreater(ph.mirror_hamming_distance(h_base, other), 64)

    def test_featureless_images_are_not_hashed(self):
        self.assertIsNone(ph.compute_phash_from_image(Image.new("RGB", (200, 200), "red")))
        self.assertIsNone(ph.compute_phash_from_image(Image.new("RGBA", (200, 200), (0, 0, 0, 0))))

    def test_transparency_is_flattened_onto_white(self):
        base = make_structured_image(3).convert("RGBA")
        transparent = base.copy()
        transparent.putalpha(255)
        self.assertEqual(ph.compute_phash_from_image(base), ph.compute_phash_from_image(transparent))

    def test_unreadable_file_returns_none(self):
        self.assertIsNone(ph.compute_media_phash(__import__("pathlib").Path("/nonexistent/file.png"), FileTypeEnum.image))

class TestNearDuplicateService(BackupTestBase):
    def setUp(self):
        super().setUp()
        nd.near_duplicate_index.invalidate()

    def _media(self, media_id, phash_value, **kwargs):
        media = Media(
            id=media_id, filename=f"m{media_id}.png", path=f"media/original/m{media_id}.png",
            hash=f"h{media_id}", file_type=FileTypeEnum.image, rating=RatingEnum.safe,
            file_size=kwargs.pop("file_size", 1000), width=kwargs.pop("width", 100),
            height=kwargs.pop("height", 100),
            phash=ph.phash_to_hex(phash_value) if phash_value is not None else None, **kwargs,
        )
        self.db.add(media)
        return media

    def test_search_orders_by_distance_and_respects_threshold_and_exclusions(self):
        base = int("0f0f0f0f0f0f0f0f" * 4, 16)
        self._media(1, base)                           # distance 0
        self._media(2, base ^ 0b111)                   # distance 3
        self._media(3, base ^ (1 << 255))              # distance 1, differs in the top bit
        self._media(4, base ^ ((1 << 50) - 1))         # distance 50 (too far for max_distance=10)
        self._media(5, None)                           # not hashed
        self._media(6, ph.mirror_phash(base) ^ 0b11)   # mirrored copy 2 bits away
        self.db.commit()

        hits = nd.near_duplicate_index.search(self.db, base, max_distance=10)
        self.assertEqual(hits, [(1, 0), (3, 1), (6, 2), (2, 3)])
        self.assertEqual(nd.near_duplicate_index.search(self.db, base, 10, exclude_ids=[1, 6]), [(3, 1), (2, 3)])
        self.assertEqual(nd.near_duplicate_index.search(self.db, base, 10, limit=1), [(1, 0)])

    def test_search_finds_neighbours_that_are_far_apart_in_sort_order(self):
        """Close hashes are not adjacent when sorted: a flipped top bit puts them at opposite ends."""
        base = (1 << 255) - 1
        self._media(1, base)
        self._media(2, base ^ (1 << 255))  # 1 bit apart, but numerically in the upper half
        for i in range(3, 20):
            self._media(i, (0x12345678 << 120) + i)
        self.db.commit()
        hits = dict(nd.near_duplicate_index.search(self.db, base, 2))
        self.assertEqual(hits, {1: 0, 2: 1})

    def test_index_refreshes_after_invalidate(self):
        target = int("a" * 64, 16)
        self._media(1, target)
        self.db.commit()
        self.assertEqual(len(nd.near_duplicate_index.search(self.db, target, 5)), 1)
        self._media(2, target ^ 1)
        self.db.commit()
        nd.near_duplicate_index.invalidate()
        self.assertEqual(len(nd.near_duplicate_index.search(self.db, target, 5)), 2)

    def test_find_existing_matches_hydrates_details(self):
        target = int("ffff0000" * 8, 16)
        self._media(7, target, width=1920, height=1080, file_size=2_500_000)
        self.db.commit()
        matches = nd.find_existing_matches(self.db, target ^ 1)
        self.assertEqual(len(matches), 1)
        m = matches[0]
        self.assertEqual((m["media_id"], m["distance"], m["width"], m["height"], m["file_size"]), (7, 1, 1920, 1080, 2_500_000))
        self.assertEqual(m["file_type"], "image")
        self.assertEqual(m["page_url"], "/media/7")
        self.assertEqual(m["confidence"], "identical")

    def test_find_queue_matches_is_symmetric_and_handles_many_matches(self):
        base = int("f0" * 32, 16)
        items = {
            "a": {"phash": ph.phash_to_hex(base), "filename": "a.png"},
            "b": {"phash": ph.phash_to_hex(base ^ 0b1), "filename": "b.png"},
            "c": {"phash": ph.phash_to_hex(ph.mirror_phash(base) ^ 0b110000), "filename": "c.png"},
            "d": {"phash": ph.phash_to_hex(base ^ ((1 << 100) - 1)), "filename": "d.png"},
            "e": {"phash": None, "filename": "e.png"},
        }
        matches = nd.find_queue_matches(items, max_distance=10)
        self.assertEqual([m["item_id"] for m in matches["a"]], ["b", "c"])
        self.assertEqual([m["distance"] for m in matches["a"]], [1, 2])
        self.assertEqual({m["item_id"] for m in matches["b"]}, {"a", "c"})
        self.assertEqual({m["item_id"] for m in matches["c"]}, {"a", "b"})
        self.assertNotIn("d", matches)
        self.assertNotIn("e", matches)

    def test_disabled_setting_skips_matching_but_still_computes_hashes(self):
        settings.save_settings({"near_duplicates": {"enabled": False, "max_distance": 31}})
        self._media(1, 0xAAAA)
        self.db.commit()
        self.assertEqual(nd.find_existing_matches(self.db, 0xAAAA), [])
        self.assertEqual(nd.find_queue_matches({"a": {"phash": "a" * 64}, "b": {"phash": "a" * 64}}), {})

        img_path = self.tmp_path / "x.png"
        img_path.write_bytes(to_bytes(make_structured_image(77)))
        self.assertIsNotNone(nd.compute_item_phash_hex(img_path, FileTypeEnum.image))

    def test_settings_are_clamped(self):
        settings.save_settings({"near_duplicates": {"enabled": True, "max_distance": 999}})
        self.assertEqual(settings.NEAR_DUPLICATE_SETTINGS["max_distance"], 64)
        settings.save_settings({"near_duplicates": {"enabled": True, "max_distance": "junk"}})
        self.assertEqual(settings.NEAR_DUPLICATE_SETTINGS["max_distance"], 31)

    def test_backfill_hashes_existing_posts(self):
        for media_id, seed in ((1, 11), (2, 12)):
            rel = f"media/original/b{media_id}.png"
            (self.tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.tmp_path / rel).write_bytes(to_bytes(make_structured_image(seed)))
            self.db.add(Media(
                id=media_id, filename=f"b{media_id}.png", path=rel, hash=f"bh{media_id}",
                file_type=FileTypeEnum.image, rating=RatingEnum.safe, file_size=1,
            ))
        # Missing file: counted as failed, must not abort the run
        self.db.add(Media(id=3, filename="gone.png", path="media/original/gone.png", hash="bh3",
                          file_type=FileTypeEnum.image, rating=RatingEnum.safe, file_size=1))
        self.db.commit()
        self.assertEqual(nd.count_unhashed(self.db), 3)

        status = nd.backfill_missing_phashes(self.SessionLocal, throttle_seconds=0)
        self.assertFalse(status["running"])
        self.assertEqual((status["total"], status["processed"], status["hashed"], status["failed"]), (3, 3, 2, 1))
        self.assertIsNone(status["current_file"])
        self.assertIsNone(status["error"])

        self.db.expire_all()
        self.assertIsNotNone(self.db.get(Media, 1).phash)
        self.assertIsNotNone(self.db.get(Media, 2).phash)
        self.assertIsNone(self.db.get(Media, 3).phash)
        self.assertEqual(nd.find_existing_matches(self.db, ph.phash_from_hex(self.db.get(Media, 1).phash))[0]["media_id"], 1)

        # Re-running hashes all existing hashable posts (including ones that already have a hash),
        # so missing files restored later or stale hashes are recomputed instead of skipped.
        self.db.get(Media, 1).phash = "0" * 64
        self.db.commit()
        rel3 = "media/original/gone.png"
        (self.tmp_path / rel3).write_bytes(to_bytes(make_structured_image(13)))
        retry = nd.backfill_missing_phashes(self.SessionLocal, throttle_seconds=0)
        self.assertEqual((retry["total"], retry["processed"], retry["hashed"], retry["failed"]), (3, 3, 3, 0))
        self.db.expire_all()
        self.assertIsNotNone(self.db.get(Media, 3).phash)
        self.assertNotEqual(self.db.get(Media, 1).phash, "0" * 64)

class TestSimilarToBuildingBlocks(BackupTestBase):
    BASE = int("0f0f0f0f0f0f0f0f" * 4, 16)

    def setUp(self):
        super().setUp()
        nd.near_duplicate_index.invalidate()
        for media_id, flips in ((1, 0), (2, 0b11), (3, 0b1111111), (4, (1 << 80) - 1)):
            self.db.add(Media(
                id=media_id, filename=f"p{media_id}.png", path=f"media/original/p{media_id}.png",
                hash=f"s{media_id}", file_type=FileTypeEnum.image, rating=RatingEnum.safe, file_size=1,
                phash=ph.phash_to_hex(self.BASE ^ flips)))
        self.db.add(Media(id=5, filename="nohash.png", path="x", hash="s5", file_type=FileTypeEnum.image,
                          rating=RatingEnum.safe, file_size=1))
        self.db.commit()

    def test_parse_values(self):
        hex_token = ph.phash_to_hex(self.BASE)
        ids, hashes, bad = nd.parse_similar_to_value(f"[12, 34,{hex_token}] zzz 99999999999999999999")
        self.assertEqual(ids, [12, 34])
        self.assertEqual(hashes, [self.BASE])
        self.assertEqual(bad, ["zzz", "99999999999999999999"])
        self.assertEqual(nd.parse_similar_to_value(""), ([], [], []))

    def test_similar_to_post_id_excludes_itself_and_orders_by_distance(self):
        cond, distances = nd.similar_to_condition(self.db, ["1"], max_distance=8)
        self.assertEqual(distances, {2: 2, 3: 7})
        self.assertEqual(sorted(m.id for m in self.db.query(Media).filter(cond)), [2, 3])

    def test_similar_to_phash_includes_exact_match(self):
        cond, distances = nd.similar_to_condition(self.db, [nd.phash_to_hex(self.BASE)], max_distance=8)
        self.assertEqual(distances, {1: 0, 2: 2, 3: 7})

    def test_multiple_targets_use_closest_distance(self):
        post_4_hash = nd.phash_to_hex(self.BASE ^ ((1 << 80) - 1))
        cond, distances = nd.similar_to_condition(self.db, ["2", post_4_hash], max_distance=4)
        # post 1 is 2 bits from the given post 2; post 4 matches the given hash exactly;
        # post 3 is 5 bits from post 2 (too far) and the given post 2 itself is excluded.
        self.assertEqual(distances, {4: 0, 1: 2})
        self.assertEqual(sorted(m.id for m in self.db.query(Media).filter(cond)), [1, 4])
        self.assertEqual([mid for mid, _ in nd.find_similar_media(self.db, [self.BASE ^ 0b11, self.BASE ^ ((1 << 80) - 1)], 4, exclude_ids=[2])], [4, 1])

    def test_negation_and_unusable_targets(self):
        cond, _ = nd.similar_to_condition(self.db, ["1"], negated=True, max_distance=8)
        self.assertEqual(sorted(m.id for m in self.db.query(Media).filter(cond)), [1, 4, 5])
        empty, d = nd.similar_to_condition(self.db, ["5", "404", "nonsense"])
        self.assertEqual((d, self.db.query(Media).filter(empty).count()), ({}, 0))
        everything, _ = nd.similar_to_condition(self.db, ["5"], negated=True)
        self.assertEqual(self.db.query(Media).filter(everything).count(), 5)
        targets = nd.resolve_similar_to_targets(self.db, ["5", "404", "nonsense", "1"])
        self.assertEqual((targets.unresolved_media_ids, targets.invalid_tokens), ([5, 404], ["nonsense"]))

    def test_media_phash_hex_roundtrip(self):
        self.assertEqual(nd.media_phash_hex(self.db.get(Media, 1)), nd.phash_to_hex(self.BASE))
        self.assertIsNone(nd.media_phash_hex(self.db.get(Media, 5)))

    def test_similar_to_works_even_when_upload_detection_is_disabled(self):
        settings.save_settings({"near_duplicates": {"enabled": False, "max_distance": 31}})
        _, distances = nd.similar_to_condition(self.db, ["1"], max_distance=8)
        self.assertEqual(distances, {2: 2, 3: 7})

class TestUploaderNearDuplicates(BackupTestBase):
    def setUp(self):
        super().setUp()
        nd.near_duplicate_index.invalidate()
        self.admin_user = User(id=1, username="admin", password_hash="hash")
        self.session_id = asyncio.run(create_upload_session(current_user=self.admin_user))["session_id"]
        self.base = make_structured_image(21)

    def _upload(self, name, data):
        return asyncio.run(upload_files_to_session(
            session_id=self.session_id,
            file=UploadFile(filename=name, file=io.BytesIO(data)),
            current_user=self.admin_user, db=self.db,
        ))

    def _report(self):
        return asyncio.run(get_session_near_duplicates(
            session_id=self.session_id, current_user=self.admin_user, db=self.db))

    def test_resized_variant_is_staged_not_rejected_and_reported(self):
        a = self._upload("big.png", to_bytes(self.base))
        b = self._upload("small.jpg", to_bytes(self.base.resize((320, 240), Image.LANCZOS), "JPEG", quality=70))
        self.assertTrue(a["phash"] and b["phash"])
        self.assertEqual(len(a["phash"]), 64)

        report = self._report()
        self.assertTrue(report["enabled"])
        self.assertEqual([m["item_id"] for m in report["items"][a["item_id"]]["queue"]], [b["item_id"]])
        self.assertEqual([m["item_id"] for m in report["items"][b["item_id"]]["queue"]], [a["item_id"]])
        small_entry = report["items"][a["item_id"]]["queue"][0]
        self.assertEqual((small_entry["width"], small_entry["height"], small_entry["file_type"]), (320, 240, "image"))
        self.assertEqual(report["items"][a["item_id"]]["existing"], [])

    def test_mirrored_and_letterboxed_variants_are_reported(self):
        a = self._upload("orig.png", to_bytes(self.base))
        b = self._upload("flipped.png", to_bytes(ImageOps.mirror(self.base)))
        c = self._upload("letterbox.png", to_bytes(ImageOps.expand(self.base, border=(0, 80, 0, 80), fill=(0, 0, 0))))
        report = self._report()
        queued_for_a = {m["item_id"] for m in report["items"][a["item_id"]]["queue"]}
        self.assertEqual(queued_for_a, {b["item_id"], c["item_id"]})

    def test_unrelated_images_are_not_reported(self):
        self._upload("one.png", to_bytes(make_structured_image(31)))
        self._upload("two.png", to_bytes(make_structured_image(32)))
        self.assertEqual(self._report()["items"], {})

    def test_item_with_several_existing_and_queued_matches(self):
        phash_value = ph.compute_phash_from_image(self.base)
        for media_id, flip in ((101, 0b1), (102, 0b11), (103, (1 << 50) - 1)):  # 1, 2 and 50 bits away
            self.db.add(Media(
                id=media_id, filename=f"lib{media_id}.png", path=f"media/original/lib{media_id}.png",
                hash=f"lib{media_id}", file_type=FileTypeEnum.image, rating=RatingEnum.safe,
                file_size=10_000 * media_id, width=800 + media_id, height=600,
                phash=ph.phash_to_hex(phash_value ^ flip),
            ))
        self.db.commit()
        nd.near_duplicate_index.invalidate()

        a = self._upload("a.png", to_bytes(self.base))
        b = self._upload("b.jpg", to_bytes(self.base.resize((400, 300)), "JPEG", quality=80))
        c = self._upload("c.png", to_bytes(self.base.resize((200, 150), Image.LANCZOS)))

        entry = self._report()["items"][a["item_id"]]
        self.assertEqual([(m["media_id"], m["distance"]) for m in entry["existing"]][:2], [(101, 1), (102, 2)])
        self.assertNotIn(103, [m["media_id"] for m in entry["existing"]])  # beyond the threshold
        self.assertEqual({m["item_id"] for m in entry["queue"]}, {b["item_id"], c["item_id"]})

    def test_removing_an_item_removes_it_from_the_others_matches(self):
        a = self._upload("a.png", to_bytes(self.base))
        b = self._upload("b.png", to_bytes(self.base.resize((300, 225), Image.LANCZOS)))
        self.assertIn(a["item_id"], self._report()["items"])
        asyncio.run(delete_staged_item(session_id=self.session_id, item_id=b["item_id"],
                                       current_user=self.admin_user))
        self.assertEqual(self._report()["items"], {})

    def test_exact_duplicates_are_still_rejected(self):
        from fastapi import HTTPException
        data = to_bytes(self.base)
        self._upload("a.png", data)
        with self.assertRaises(HTTPException) as ctx:
            self._upload("a_copy.png", data)
        self.assertEqual(ctx.exception.status_code, 409)

    def test_commit_keeps_near_duplicates_and_stores_hash(self):
        a = self._upload("a.png", to_bytes(self.base))
        b = self._upload("b.png", to_bytes(self.base.resize((300, 225), Image.LANCZOS)))
        result = asyncio.run(commit_upload_session(
            session_id=self.session_id, current_user=self.admin_user, db=self.db))
        self.assertEqual((result.total_created, result.total_duplicates, result.total_failed), (2, 0, 0))

        self.db.expire_all()
        rows = self.db.query(Media).order_by(Media.id).all()
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r.phash is not None for r in rows))
        stored = {r.phash for r in rows}
        self.assertEqual(stored, {a["phash"], b["phash"]})

    def test_later_session_sees_committed_posts_as_existing_matches(self):
        self._upload("a.png", to_bytes(self.base))
        asyncio.run(commit_upload_session(session_id=self.session_id, current_user=self.admin_user, db=self.db))

        self.session_id = asyncio.run(create_upload_session(current_user=self.admin_user))["session_id"]
        variant = self._upload("variant.jpg", to_bytes(self.base.resize((256, 192)), "JPEG", quality=60))
        existing = self._report()["items"][variant["item_id"]]["existing"]
        self.assertEqual(len(existing), 1)
        self.assertEqual((existing[0]["width"], existing[0]["height"]), (640, 480))

    def test_disabled_feature_stages_with_hash_and_no_report(self):
        settings.save_settings({"near_duplicates": {"enabled": False, "max_distance": 31}})
        a = self._upload("a.png", to_bytes(self.base))
        self._upload("b.png", to_bytes(self.base.resize((300, 225), Image.LANCZOS)))
        self.assertIsNotNone(a["phash"])
        report = self._report()
        self.assertFalse(report["enabled"])
        self.assertEqual(report["items"], {})

class TestDirectCreateAndAdmin(BackupTestBase):
    def setUp(self):
        super().setUp()
        nd.near_duplicate_index.invalidate()
        self.admin_user = User(id=1, username="admin", password_hash="hash")
        self.base = make_structured_image(41)

    def _save(self, name, img, **kwargs):
        from backend.app.routes.media import process_and_save_media
        path = settings.ORIGINAL_DIR / name
        img.convert("RGB").save(path, **kwargs)
        return process_and_save_media(
            db=self.db, file_path=path, unique_filename=name, rating=RatingEnum.safe,
            tags="", album_ids=None, source=None, category_hints=None,
        )

    def test_direct_creation_reports_but_does_not_block_near_duplicates(self):
        first = self._save("first.png", self.base)
        self.assertEqual(first.near_duplicates, [])

        second = self._save("second.jpg", self.base.resize((320, 240), Image.LANCZOS), quality=70)
        self.assertEqual(self.db.query(Media).count(), 2)  # created, not rejected
        self.assertEqual([m["media_id"] for m in second.near_duplicates], [first.id])
        self.assertEqual((second.near_duplicates[0]["width"], second.near_duplicates[0]["height"]), (640, 480))
        self.assertIsNotNone(self.db.get(Media, second.id).phash)

    def test_admin_settings_roundtrip_and_validation(self):
        from pydantic import ValidationError
        from backend.app.routes.admin.near_duplicates import (
            NearDuplicateSettingsUpdate, get_near_duplicate_settings,
            update_near_duplicate_settings)

        current = asyncio.run(get_near_duplicate_settings(current_user=self.admin_user, db=self.db))
        self.assertEqual((current["enabled"], current["max_distance"], current["pending"]), (True, 31, 0))

        updated = asyncio.run(update_near_duplicate_settings(
            NearDuplicateSettingsUpdate(enabled=False, max_distance=16),
            current_user=self.admin_user, db=self.db))
        self.assertEqual((updated["enabled"], updated["max_distance"]), (False, 16))
        self.assertFalse(updated["backfill_started"])
        self.assertEqual(settings.NEAR_DUPLICATE_SETTINGS, {"enabled": False, "max_distance": 16})

        with self.assertRaises(ValidationError):
            NearDuplicateSettingsUpdate(max_distance=99)

    def test_backfill_task_starts_even_though_session_factory_is_set_after_import(self):
        """Regression: SessionLocal is None until init_engine(); it must be looked up at call time."""
        from backend.app import database
        from backend.app.routes.admin import near_duplicates as admin_nd

        rel = "media/original/old.png"
        (self.tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (self.tmp_path / rel).write_bytes(to_bytes(self.base))
        self.db.add(Media(id=1, filename="old.png", path=rel, hash="old", file_type=FileTypeEnum.image,
                          rating=RatingEnum.safe, file_size=1))
        self.db.commit()

        previous = database.SessionLocal
        database.SessionLocal = self.SessionLocal
        try:
            async def run():
                self.assertTrue(admin_nd.start_backfill_task())
                for _ in range(100):
                    await asyncio.sleep(0.05)
                    if nd.count_unhashed(self.db) == 0:
                        break
            asyncio.run(run())
        finally:
            database.SessionLocal = previous

        self.db.expire_all()
        self.assertIsNotNone(self.db.get(Media, 1).phash)

    def test_backfill_task_refuses_to_start_before_database_init(self):
        from backend.app import database
        from backend.app.routes.admin import near_duplicates as admin_nd
        previous = database.SessionLocal
        database.SessionLocal = None
        try:
            async def run():
                return admin_nd.start_backfill_task()
            self.assertFalse(asyncio.run(run()))
        finally:
            database.SessionLocal = previous

    def test_replacing_a_posts_file_refreshes_its_hash(self):
        created = self._save("orig.png", self.base)
        media = self.db.get(Media, created.id)
        old_hash = media.phash
        (settings.BASE_DIR / media.path).write_bytes(to_bytes(make_structured_image(99)))
        nd.refresh_media_phash(media)
        self.db.commit()
        self.assertNotEqual(self.db.get(Media, created.id).phash, old_hash)

    def test_backup_export_and_import_preserves_pdq_hashes(self):
        first = self._save("backup_a.png", self.base)
        expected_phash = self.db.get(Media, first.id).phash
        self.assertEqual(len(expected_phash), 64)

        response = asyncio.run(backup_full_db(current_user=self.admin_user, db=self.db))
        zip_bytes = io.BytesIO()
        async def collect():
            async for chunk in response.body_iterator:
                zip_bytes.write(chunk)
        asyncio.run(collect())

        zip_bytes.seek(0)
        with zipfile.ZipFile(zip_bytes, "r") as zf:
            exported_meta = json.loads(zf.read("backup.json").decode("utf-8"))
        self.assertEqual(exported_meta["media"][0]["phash"], expected_phash)

        self.wipe_database()
        (settings.ORIGINAL_DIR / "backup_a.png").unlink(missing_ok=True)

        zip_bytes.seek(0)
        import_full_backup(zip_bytes, self.db)
        restored = self.db.query(Media).filter(Media.filename == "backup_a.png").one()
        self.assertEqual(restored.phash, expected_phash)
        self.assertEqual(nd.count_unhashed(self.db), 0)

class TestUpdatePostFromStagedItem(AsyncBackupTestBase):
    """The uploader's "Update Post" action: apply a queued file + metadata to an existing post."""

    async def asyncSetUp(self):
        await super().asyncSetUp()
        nd.near_duplicate_index.invalidate()
        self.admin_user = User(id=1, username="admin", password_hash="hash")
        self.base = make_structured_image(61)

    async def _create_post_and_stage_better_variant(self):
        from backend.app.routes.media import process_and_save_media
        small = self.base.resize((320, 240), Image.LANCZOS)
        path = settings.ORIGINAL_DIR / "post.png"
        small.convert("RGB").save(path)
        post = process_and_save_media(db=self.db, file_path=path, unique_filename="post.png",
                                      rating=RatingEnum.safe, tags="old_tag", album_ids=None, source=None,
                                      category_hints=None)
        session_id = (await create_upload_session(current_user=self.admin_user))["session_id"]
        item = await upload_files_to_session(
            session_id=session_id,
            file=UploadFile(filename="big.png", file=io.BytesIO(to_bytes(self.base))),
            current_user=self.admin_user, db=self.db)
        return post, session_id, item

    async def test_staged_file_replaces_post_file_and_applies_metadata_and_albums(self):
        from backend.app.models import Album
        from backend.app.routes.media import PostUpdateRequest, StagedFileRef, update_from_source
        post, session_id, item = await self._create_post_and_stage_better_variant()
        existing_album = Album(name="Existing")
        self.db.add(existing_album)
        self.db.commit()

        resp = await update_from_source(
            media_id=post.id,
            req=PostUpdateRequest(
                update_file=True, staged_file=StagedFileRef(session_id=session_id, item_id=item["item_id"]),
                update_tags=True, tags=["new_tag"], merge_tags=True,
                update_rating=True, rating="questionable",
                update_source=True, source="https://example.com/p/1",
                update_description=True, description="from the queue",
                update_albums=True, album_ids=[existing_album.id], album_path="Artists/New Album",
            ),
            current_user=self.admin_user, db=self.db)

        self.assertEqual((resp.width, resp.height), (640, 480))
        self.db.expire_all()
        media = self.db.get(Media, post.id)
        self.assertEqual(media.hash, item["hash"])
        self.assertEqual({t.name for t in media.tags}, {"old_tag", "new_tag"})
        self.assertEqual(media.source, "https://example.com/p/1")
        self.assertEqual(media.description, "from the queue")
        self.assertEqual(media.rating, RatingEnum.questionable)
        self.assertEqual({a.name for a in media.albums}, {"Existing", "New Album"})
        new_album = next(a for a in media.albums if a.name == "New Album")
        parent = self.db.query(Album).filter(Album.name == "Artists").one()
        self.assertEqual([c.id for c in parent.children], [new_album.id])  # created under its parent
        # The stored hash now describes the new file (it is a variant of the same picture, so it
        # may legitimately equal the old one; what matters is that it equals the staged item's)
        self.assertEqual(media.phash, item["phash"])

    async def test_staged_file_errors(self):
        from fastapi import HTTPException
        from backend.app.routes.media import PostUpdateRequest, StagedFileRef, update_from_source
        post, session_id, item = await self._create_post_and_stage_better_variant()
        with self.assertRaises(HTTPException) as ctx:
            await update_from_source(
                media_id=post.id,
                req=PostUpdateRequest(update_file=True, staged_file=StagedFileRef(session_id=session_id, item_id="nope")),
                current_user=self.admin_user, db=self.db)
        self.assertEqual(ctx.exception.status_code, 404)
        with self.assertRaises(HTTPException) as ctx:
            await update_from_source(media_id=post.id, req=PostUpdateRequest(update_file=True),
                                     current_user=self.admin_user, db=self.db)
        self.assertEqual(ctx.exception.status_code, 400)

    async def test_albums_are_added_without_removing_existing_ones(self):
        from backend.app.models import Album
        from backend.app.routes.media import PostUpdateRequest, update_from_source
        post, _, _ = await self._create_post_and_stage_better_variant()
        keep, add = Album(name="Keep"), Album(name="Add")
        self.db.add_all([keep, add])
        self.db.commit()
        media = self.db.get(Media, post.id)
        media.albums = [keep]
        self.db.commit()
        await update_from_source(
            media_id=post.id, req=PostUpdateRequest(update_albums=True, album_ids=[add.id]),
            current_user=self.admin_user, db=self.db)
        self.db.expire_all()
        self.assertEqual({a.name for a in self.db.get(Media, post.id).albums}, {"Keep", "Add"})

class TestUploadAsRelated(AsyncBackupTestBase):
    """Pending parent/child relations between an upload and existing posts."""

    async def asyncSetUp(self):
        await super().asyncSetUp()
        nd.near_duplicate_index.invalidate()
        self.admin_user = User(id=1, username="admin", password_hash="hash")
        self.session_id = (await create_upload_session(current_user=self.admin_user))["session_id"]
        self.base = make_structured_image(71)

    def _post(self, media_id, parent_id=None, phash_value=None):
        media = Media(
            id=media_id, filename=f"e{media_id}.png", path=f"media/original/e{media_id}.png",
            hash=f"rel{media_id}", file_type=FileTypeEnum.image, rating=RatingEnum.safe, file_size=1000,
            width=100, height=100, parent_id=parent_id,
            phash=ph.phash_to_hex(phash_value) if phash_value is not None else None)
        self.db.add(media)
        self.db.commit()
        return media

    async def _stage(self, name="up.png", seed=None):
        img = self.base if seed is None else make_structured_image(seed)
        return await upload_files_to_session(
            session_id=self.session_id,
            file=UploadFile(filename=name, file=io.BytesIO(to_bytes(img))),
            current_user=self.admin_user, db=self.db)

    async def _patch(self, item_id, **fields):
        return await update_staged_item(
            session_id=self.session_id, item_id=item_id,
            update=UploadSessionItemUpdate(**fields), current_user=self.admin_user, db=self.db)

    async def _commit(self):
        return await commit_upload_session(
            session_id=self.session_id, current_user=self.admin_user, db=self.db)

    async def test_matches_expose_the_library_posts_own_relations(self):
        item = await self._stage()
        phash_value = ph.phash_from_hex(item["phash"])
        parent = self._post(1)
        self._post(2, parent_id=1, phash_value=phash_value)             # a child
        self._post(3, phash_value=phash_value ^ 0b1)                    # standalone
        self._post(4, phash_value=phash_value ^ 0b11)                   # a parent...
        self._post(5, parent_id=4)                                      # ...of this child
        nd.near_duplicate_index.invalidate()
        report = await get_session_near_duplicates(
            session_id=self.session_id, current_user=self.admin_user, db=self.db)
        by_id = {m["media_id"]: m for m in report["items"][item["item_id"]]["existing"]}
        self.assertEqual((by_id[2]["parent_id"], by_id[2]["children_count"]), (1, 0))
        self.assertEqual((by_id[3]["parent_id"], by_id[3]["children_count"]), (None, 0))
        self.assertEqual((by_id[4]["parent_id"], by_id[4]["children_count"]), (None, 1))

    async def test_selecting_a_relation_is_validated_and_stored(self):
        from fastapi import HTTPException
        item = await self._stage()
        self._post(1)                       # standalone
        self._post(2, parent_id=1)          # a child
        self._post(3)                       # a parent...
        self._post(4, parent_id=3)          # ...with a child
        self._post(5)                       # another standalone post

        updated = await self._patch(item["item_id"], parent_media_id=1, child_media_ids=[])
        self.assertEqual((updated["parent_media_id"], updated["child_media_ids"]), (1, []))

        async def rejected(**fields):
            with self.assertRaises(HTTPException) as ctx:
                await self._patch(item["item_id"], **fields)
            return ctx.exception.status_code

        self.assertEqual(await rejected(parent_media_id=2), 400)        # target is a child already
        self.assertEqual(await rejected(parent_media_id=404), 404)      # target does not exist
        self.assertEqual(await rejected(parent_media_id=None, child_media_ids=[3]), 400)   # target has children
        self.assertEqual(await rejected(parent_media_id=1, child_media_ids=[2]), 400)      # child AND parent
        self.assertEqual(await rejected(child_media_ids=[2]), 400)      # still has parent 1 stored

        switched = await self._patch(item["item_id"], parent_media_id=None, child_media_ids=[2, 2, 5])
        self.assertEqual((switched["parent_media_id"], switched["child_media_ids"]), (None, [2, 5]))  # de-duplicated
        cleared = await self._patch(item["item_id"], parent_media_id=None, child_media_ids=[])
        self.assertEqual((cleared["parent_media_id"], cleared["child_media_ids"]), (None, []))

    async def test_commit_creates_the_upload_as_child(self):
        item = await self._stage()
        existing = self._post(1)
        await self._patch(item["item_id"], parent_media_id=1, child_media_ids=[])
        result = await self._commit()
        self.assertEqual(result.total_created, 1)
        self.db.expire_all()
        new_post = self.db.get(Media, result.results[0].media_id)
        self.assertEqual(new_post.parent_id, existing.id)
        self.assertEqual([c.id for c in self.db.get(Media, 1).children], [new_post.id])

    async def test_commit_creates_the_upload_as_parent_and_reparents(self):
        item = await self._stage()
        self._post(1)                        # standalone -> becomes a child of the upload
        self._post(10)
        self._post(2, parent_id=10)          # had another parent -> moved to the upload
        await self._patch(item["item_id"], parent_media_id=None, child_media_ids=[1, 2])
        result = await self._commit()
        self.db.expire_all()
        new_id = result.results[0].media_id
        self.assertIsNone(self.db.get(Media, new_id).parent_id)
        self.assertEqual({m.id for m in self.db.query(Media).filter(Media.parent_id == new_id)}, {1, 2})
        self.assertEqual(self.db.query(Media).filter(Media.parent_id == 10).count(), 0)

    async def test_relations_are_rechecked_at_commit(self):
        # Child-of target turns into a child itself after the relation was chosen
        item = await self._stage()
        self._post(1)
        self._post(2)
        await self._patch(item["item_id"], parent_media_id=1, child_media_ids=[])
        self.db.get(Media, 1).parent_id = 2
        self.db.commit()
        result = await self._commit()
        self.assertEqual((result.total_created, result.total_failed), (1, 0))   # upload itself still succeeds
        self.db.expire_all()
        self.assertIsNone(self.db.get(Media, result.results[0].media_id).parent_id)

    async def test_commit_skips_parent_targets_that_gained_children_or_vanished(self):
        item = await self._stage()
        self._post(1)
        self._post(2)
        self._post(3)
        await self._patch(item["item_id"], parent_media_id=None, child_media_ids=[1, 2, 3])
        self._post(4, parent_id=1)                  # 1 now has a child -> cannot become a child
        self.db.delete(self.db.get(Media, 3))       # 3 was deleted
        self.db.commit()
        result = await self._commit()
        self.db.expire_all()
        new_id = result.results[0].media_id
        self.assertEqual({m.id for m in self.db.query(Media).filter(Media.parent_id == new_id)}, {2})
        self.assertIsNone(self.db.get(Media, 1).parent_id)

    async def test_two_uploads_can_both_become_children_of_the_same_post(self):
        a = await self._stage("a.png", seed=81)
        b = await self._stage("b.png", seed=82)
        self._post(1)
        await self._patch(a["item_id"], parent_media_id=1, child_media_ids=[])
        await self._patch(b["item_id"], parent_media_id=1, child_media_ids=[])
        result = await self._commit()
        self.db.expire_all()
        self.assertEqual(self.db.query(Media).filter(Media.parent_id == 1).count(), 2)
        self.assertEqual(result.total_created, 2)

if __name__ == "__main__":
    unittest.main()
