import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from PIL import Image

from backend.app.enums import FileTypeEnum, RatingEnum
from backend.app.models import Media, User
from backend.app.routes.media import (
    bulk_update_metadata,
    get_media_batch,
    post_media_batch,
    post_media_batch_scan_dates,
)
from backend.app.schemas import (
    BatchMediaRequest,
    BatchMetadataRequest,
    BulkMediaMetadataItem,
    BulkMediaMetadataUpdateRequest,
)
from tests.test_base import AsyncBackupTestBase

def _to_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)

class TestBulkMediaUpdates(AsyncBackupTestBase):
    def setUp(self):
        super().setUp()
        self.user = User(id=1, username="admin", password_hash="testhash")
        self.db.add(self.user)

        self.uploaded_1 = datetime(2025, 1, 10, 8, 30, 0, tzinfo=timezone.utc)
        self.custom_1 = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        self.uploaded_2 = datetime(2025, 2, 20, 14, 15, 0, tzinfo=timezone.utc)

        self.m1 = Media(
            filename="first.jpg",
            path="media/original/first.jpg",
            hash="hash_first",
            file_type=FileTypeEnum.image,
            rating=RatingEnum.safe,
            uploaded_at=self.uploaded_1,
            custom_date=self.custom_1,
            source="https://example.com/original-1",
        )
        self.m2 = Media(
            filename="second.png",
            path="media/original/second.png",
            hash="hash_second",
            file_type=FileTypeEnum.image,
            rating=RatingEnum.questionable,
            uploaded_at=self.uploaded_2,
            custom_date=self.uploaded_2,
            source=None,
        )
        self.db.add_all([self.m1, self.m2])
        self.db.commit()
        self.db.refresh(self.m1)
        self.db.refresh(self.m2)

    async def test_batch_info_projection_post_and_get(self):
        post_res = await post_media_batch(
            payload=BatchMediaRequest(ids=[self.m2.id, self.m1.id], projection="info"),
            db=self.db,
        )
        items = post_res["items"]
        self.assertEqual([it["id"] for it in items], [self.m2.id, self.m1.id])
        self.assertEqual(items[0]["custom_date"], "2025-02-20T14:15:00+00:00")
        self.assertIsNone(items[0]["source"])
        self.assertEqual(items[1]["uploaded_at"], "2025-01-10T08:30:00+00:00")
        self.assertEqual(items[1]["custom_date"], "2024-06-15T12:00:00+00:00")
        self.assertEqual(items[1]["source"], "https://example.com/original-1")

        get_res = await get_media_batch(ids=f"{self.m1.id},{self.m2.id}", projection="info", db=self.db)
        self.assertEqual([it["id"] for it in get_res["items"]], [self.m1.id, self.m2.id])

    async def test_bulk_update_metadata_custom_dates_and_sources(self):
        with patch("backend.app.routes.media.listing.invalidate_media_cache") as mock_inv_all, \
             patch("backend.app.routes.media.listing.invalidate_media_item_cache") as mock_inv_item:
            # Update only custom_date on m1 (reset to uploaded_at) and m2 (explicit date); sources must stay untouched
            res = await bulk_update_metadata(
                payload=BulkMediaMetadataUpdateRequest(items=[
                    BulkMediaMetadataItem(id=self.m1.id, custom_date=None),
                    BulkMediaMetadataItem(id=self.m2.id, custom_date="2023-09-01T18:45:00Z"),
                ]),
                current_user=self.user,
                db=self.db,
            )

        self.assertEqual(res.updated_count, 2)
        self.assertEqual(set(res.updated_media_ids), {self.m1.id, self.m2.id})
        mock_inv_all.assert_called_once()
        self.assertEqual(mock_inv_item.call_count, 2)

        self.db.refresh(self.m1)
        self.db.refresh(self.m2)
        self.assertEqual(_to_utc(self.m1.custom_date), self.uploaded_1)
        self.assertEqual(_to_utc(self.m2.custom_date), datetime(2023, 9, 1, 18, 45, 0, tzinfo=timezone.utc))
        self.assertEqual(self.m1.source, "https://example.com/original-1")

        # Update only source (clear m1 via whitespace, trim m2); custom_dates must stay untouched
        res2 = await bulk_update_metadata(
            payload=BulkMediaMetadataUpdateRequest(items=[
                BulkMediaMetadataItem(id=self.m1.id, source="   "),
                BulkMediaMetadataItem(id=self.m2.id, source="  https://example.com/new  "),
            ]),
            current_user=self.user,
            db=self.db,
        )
        self.assertEqual(res2.updated_count, 2)
        self.db.refresh(self.m1)
        self.db.refresh(self.m2)
        self.assertIsNone(self.m1.source)
        self.assertEqual(self.m2.source, "https://example.com/new")
        self.assertEqual(_to_utc(self.m2.custom_date), datetime(2023, 9, 1, 18, 45, 0, tzinfo=timezone.utc))

        # No-op updates should not count or invalidate cache
        with patch("backend.app.routes.media.listing.invalidate_media_cache") as mock_inv_noop:
            res_noop = await bulk_update_metadata(
                payload=BulkMediaMetadataUpdateRequest(items=[
                    BulkMediaMetadataItem(id=self.m1.id, custom_date=self.uploaded_1.isoformat(), source=None),
                ]),
                current_user=self.user,
                db=self.db,
            )
        self.assertEqual(res_noop.updated_count, 0)
        mock_inv_noop.assert_not_called()

    async def test_bulk_update_metadata_validation_and_atomicity(self):
        empty = await bulk_update_metadata(
            payload=BulkMediaMetadataUpdateRequest(items=[]),
            current_user=self.user,
            db=self.db,
        )
        self.assertEqual(empty.updated_count, 0)

        # Invalid date rejects entire batch atomically
        with self.assertRaises(HTTPException) as ctx:
            await bulk_update_metadata(
                payload=BulkMediaMetadataUpdateRequest(items=[
                    BulkMediaMetadataItem(id=self.m1.id, custom_date="2020-01-01T00:00:00Z"),
                    BulkMediaMetadataItem(id=self.m2.id, custom_date="not-a-valid-date"),
                ]),
                current_user=self.user,
                db=self.db,
            )
        self.assertEqual(ctx.exception.status_code, 422)
        self.db.refresh(self.m1)
        self.assertEqual(_to_utc(self.m1.custom_date), self.custom_1)

        # Duplicate IDs and missing IDs return 400
        for bad_items in (
            [BulkMediaMetadataItem(id=self.m1.id, source="a"), BulkMediaMetadataItem(id=self.m1.id, source="b")],
            [BulkMediaMetadataItem(id=999999, source="a")],
        ):
            with self.assertRaises(HTTPException) as ctx:
                await bulk_update_metadata(
                    payload=BulkMediaMetadataUpdateRequest(items=bad_items),
                    current_user=self.user,
                    db=self.db,
                )
            self.assertEqual(ctx.exception.status_code, 400)

    async def test_batch_scan_dates_sources_and_fallback(self):
        # 1. Image with EXIF DateTimeOriginal
        exif_path = self.original_dir / "exif_photo.jpg"
        img = Image.new("RGB", (16, 16), color="blue")
        exif = img.getexif()
        exif[36867] = "2022:03:14 15:09:26"
        img.save(exif_path, format="JPEG", exif=exif)

        # 2. Image with gallery-dl sidecar JSON date
        sidecar_img = self.original_dir / "sidecar_art.jpg"
        Image.new("RGB", (16, 16), color="green").save(sidecar_img, format="JPEG")
        (self.original_dir / "sidecar_art.jpg.json").write_text(
            json.dumps({"category": "danbooru", "date": "2021-07-04 10:20:30", "tags": ["1girl"]}),
            encoding="utf-8",
        )

        # 3. Plain image with no metadata or booru source
        plain_img = self.original_dir / "plain.jpg"
        Image.new("RGB", (16, 16), color="white").save(plain_img, format="JPEG")

        m_exif = Media(filename="exif_photo.jpg", path="media/original/exif_photo.jpg", hash="h_exif", file_type=FileTypeEnum.image, rating=RatingEnum.safe)
        m_side = Media(filename="sidecar_art.jpg", path="media/original/sidecar_art.jpg", hash="h_side", file_type=FileTypeEnum.image, rating=RatingEnum.safe)
        m_plain = Media(filename="plain.jpg", path="media/original/plain.jpg", hash="h_plain", file_type=FileTypeEnum.image, rating=RatingEnum.safe)
        m_booru = Media(
            filename="booru.jpg",
            path="media/original/plain.jpg",
            hash="h_booru",
            file_type=FileTypeEnum.image,
            rating=RatingEnum.safe,
            source="https://danbooru.donmai.us/posts/12345",
        )
        # Use unique path for m_booru (path column is unique)
        booru_img = self.original_dir / "booru.jpg"
        Image.new("RGB", (16, 16), color="yellow").save(booru_img, format="JPEG")
        m_booru.path = "media/original/booru.jpg"

        self.db.add_all([m_exif, m_side, m_plain, m_booru])
        self.db.commit()

        class FakeBooruClient:
            def fetch_post_by_url(self, url):
                return SimpleNamespace(uploaded_at="2020-11-12T05:06:07Z")

        def fake_get_client(url, db=None):
            return FakeBooruClient() if url and "danbooru.donmai.us" in url else None

        with patch("backend.app.services.booru.get_client_for_url", side_effect=fake_get_client):
            res = await post_media_batch_scan_dates(
                payload=BatchMetadataRequest(ids=[m_exif.id, m_side.id, m_plain.id, m_booru.id]),
                current_user=self.user,
                db=self.db,
            )

        items = res["items"]
        self.assertEqual(items[str(m_exif.id)], {"custom_date": "2022-03-14T15:09:26+00:00", "origin": "exif"})
        self.assertEqual(items[str(m_side.id)], {"custom_date": "2021-07-04T10:20:30+00:00", "origin": "sidecar"})
        self.assertEqual(items[str(m_plain.id)], {"custom_date": None, "origin": None})
        self.assertEqual(items[str(m_booru.id)], {"custom_date": "2020-11-12T05:06:07+00:00", "origin": "booru"})
