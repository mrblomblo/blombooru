import asyncio
import unittest
from datetime import datetime
from sqlalchemy import event

from backend.app.enums import FileTypeEnum
from backend.app.models import (Album, Media, RatingEnum, User,
                                blombooru_album_hierarchy, blombooru_album_media)
from backend.app.routes.albums import (autocomplete_albums, get_album_statistics,
                                       get_albums, get_albums_tree)
from backend.app.utils.album_utils import (add_media_to_album, delete_album_cascade,
                                          get_bulk_album_thumbnails,
                                          handle_media_deleted, handle_media_rating_changed,
                                          recalculate_album_metrics,
                                          recalculate_all_album_metrics,
                                          reparent_album)
from backend.app.utils.search_parser import apply_search_criteria, parse_search_query
from tests.backup_test_base import BackupTestBase

class DummyRequest:
    pass

class TestAlbumArchitecture(BackupTestBase):
    def setUp(self):
        super().setUp()
        self.admin_user = User(id=1, username="admin", password_hash="hash")

    def _create_media(self, filename: str, rating: RatingEnum = RatingEnum.safe) -> Media:
        m = Media(
            filename=filename,
            path=f"media/original/{filename}",
            thumbnail_path=f"media/thumbnails/{filename}.jpg",
            hash=f"hash_{filename}",
            file_type=FileTypeEnum.image,
            mime_type="image/jpeg",
            file_size=1024,
            rating=rating,
            uploaded_at=datetime.now()
        )
        self.db.add(m)
        self.db.commit()
        self.db.refresh(m)
        return m

    def _create_album(self, name: str, parent_id: int = None) -> Album:
        album = Album(
            name=name,
            cached_rating=RatingEnum.safe.value,
            cached_media_count=0,
            cached_direct_media_count=0,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            last_modified=datetime.now()
        )
        self.db.add(album)
        self.db.commit()
        self.db.refresh(album)

        if parent_id:
            self.db.execute(
                blombooru_album_hierarchy.insert().values(
                    parent_album_id=parent_id,
                    child_album_id=album.id
                )
            )
            self.db.commit()
            recalculate_album_metrics(self.db, [parent_id])
            self.db.commit()
            self.db.refresh(album)

        return album

    def test_recalculate_metrics_and_folding(self):
        # Root -> Child -> Grandchild
        root = self._create_album("Root")
        child = self._create_album("Child", parent_id=root.id)
        grandchild = self._create_album("Grandchild", parent_id=child.id)

        m1 = self._create_media("m1.jpg", rating=RatingEnum.safe)
        m2 = self._create_media("m2.jpg", rating=RatingEnum.explicit)
        m3 = self._create_media("m3.jpg", rating=RatingEnum.questionable)

        # Add m1 to grandchild
        add_media_to_album(self.db, grandchild.id, [m1.id])
        self.db.refresh(grandchild)
        self.db.refresh(child)
        self.db.refresh(root)

        self.assertEqual(grandchild.cached_media_count, 1)
        self.assertEqual(grandchild.cached_direct_media_count, 1)
        self.assertEqual(child.cached_media_count, 1)
        self.assertEqual(child.cached_direct_media_count, 0)
        self.assertEqual(root.cached_media_count, 1)

        # Add m2 (explicit) to child
        add_media_to_album(self.db, child.id, [m2.id])
        self.db.refresh(grandchild)
        self.db.refresh(child)
        self.db.refresh(root)

        self.assertEqual(child.cached_media_count, 2)
        self.assertEqual(child.cached_direct_media_count, 1)
        self.assertEqual(child.cached_rating, RatingEnum.explicit)
        self.assertEqual(root.cached_media_count, 2)
        self.assertEqual(root.cached_rating, RatingEnum.explicit)
        self.assertEqual(grandchild.cached_rating, RatingEnum.safe)

        # Add m3 (questionable) to root
        add_media_to_album(self.db, root.id, [m3.id])
        self.db.refresh(root)
        self.assertEqual(root.cached_media_count, 3)
        self.assertEqual(root.cached_direct_media_count, 1)

    def test_reparenting_cycle_rejection(self):
        a = self._create_album("A")
        b = self._create_album("B", parent_id=a.id)
        c = self._create_album("C", parent_id=b.id)

        # Trying to make A a child of C should raise 400
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            reparent_album(self.db, a.id, c.id)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Circular reference detected", ctx.exception.detail)

        # Self-parenting rejection
        with self.assertRaises(HTTPException) as ctx:
            reparent_album(self.db, a.id, a.id)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_reparenting_metrics_update(self):
        p1 = self._create_album("Parent1")
        p2 = self._create_album("Parent2")
        child = self._create_album("Child", parent_id=p1.id)

        m = self._create_media("m.jpg", rating=RatingEnum.questionable)
        add_media_to_album(self.db, child.id, [m.id])

        self.db.refresh(p1)
        self.db.refresh(p2)
        self.assertEqual(p1.cached_media_count, 1)
        self.assertEqual(p1.cached_rating, RatingEnum.questionable)
        self.assertEqual(p2.cached_media_count, 0)

        # Move Child to Parent2
        reparent_album(self.db, child.id, p2.id)

        self.db.refresh(p1)
        self.db.refresh(p2)
        self.assertEqual(p1.cached_media_count, 0)
        self.assertEqual(p2.cached_media_count, 1)
        self.assertEqual(p2.cached_rating, RatingEnum.questionable)

    def test_media_rating_change_propagation(self):
        root = self._create_album("Root")
        m = self._create_media("m.jpg", rating=RatingEnum.safe)
        add_media_to_album(self.db, root.id, [m.id])

        self.db.refresh(root)
        self.assertEqual(root.cached_rating, RatingEnum.safe)

        # Update media rating to explicit
        m.rating = RatingEnum.explicit
        self.db.commit()
        handle_media_rating_changed(self.db, m.id, RatingEnum.explicit)

        self.db.refresh(root)
        self.assertEqual(root.cached_rating, RatingEnum.explicit)

    def test_media_delete_propagation(self):
        root = self._create_album("Root")
        m = self._create_media("m.jpg", rating=RatingEnum.explicit)
        add_media_to_album(self.db, root.id, [m.id])

        self.db.refresh(root)
        self.assertEqual(root.cached_media_count, 1)
        self.assertEqual(root.cached_rating, RatingEnum.explicit)

        # Delete media
        handle_media_deleted(self.db, [m.id])
        self.db.delete(m)
        self.db.commit()

        self.db.refresh(root)
        self.assertEqual(root.cached_media_count, 0)
        self.assertEqual(root.cached_rating, RatingEnum.safe)

    def test_delete_album_cascade(self):
        root = self._create_album("Root")
        child = self._create_album("Child", parent_id=root.id)
        m = self._create_media("m.jpg", rating=RatingEnum.explicit)
        add_media_to_album(self.db, child.id, [m.id])

        self.db.refresh(root)
        self.assertEqual(root.cached_media_count, 1)

        # Cascade delete child
        delete_album_cascade(self.db, child.id)

        self.db.refresh(root)
        self.assertEqual(root.cached_media_count, 0)
        self.assertEqual(root.cached_rating, RatingEnum.safe)
        self.assertIsNone(self.db.query(Album).filter(Album.id == child.id).first())

    def test_get_albums_tree(self):
        root = self._create_album("Root")
        child = self._create_album("Child", parent_id=root.id)
        m = self._create_media("m.jpg", rating=RatingEnum.safe)
        add_media_to_album(self.db, child.id, [m.id])

        res = asyncio.run(get_albums_tree(DummyRequest(), db=self.db))
        items = res["items"]
        self.assertEqual(len(items), 2)
        root_node = next(i for i in items if i["id"] == root.id)
        child_node = next(i for i in items if i["id"] == child.id)

        self.assertEqual(root_node["depth"], 0)
        self.assertEqual(root_node["children_count"], 1)
        self.assertEqual(root_node["media_count"], 1)

        self.assertEqual(child_node["depth"], 1)
        self.assertEqual(child_node["parent_id"], root.id)
        self.assertEqual(child_node["direct_media_count"], 1)

    def test_get_album_stats(self):
        root1 = self._create_album("Root1")
        root2 = self._create_album("Root2")
        child = self._create_album("Child", parent_id=root1.id)
        m1 = self._create_media("m1.jpg")
        m2 = self._create_media("m2.jpg")
        add_media_to_album(self.db, root1.id, [m1.id])
        add_media_to_album(self.db, child.id, [m2.id])

        res = asyncio.run(get_album_statistics(db=self.db))
        self.assertEqual(res["total_albums"], 3)
        self.assertEqual(res["root_albums"], 2)
        self.assertEqual(res["total_media_in_albums"], 2)

    def test_autocomplete_albums(self):
        root = self._create_album("Animals")
        cat = self._create_album("Cats", parent_id=root.id)

        res = asyncio.run(autocomplete_albums(DummyRequest(), q="cat", db=self.db))
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["id"], cat.id)
        self.assertEqual(res[0]["name"], "Cats")
        self.assertEqual(res[0]["parent_path"], "Animals")

    def test_search_parser_album_tree(self):
        root = self._create_album("Nature")
        child = self._create_album("Forests", parent_id=root.id)
        m1 = self._create_media("m1.jpg")
        m2 = self._create_media("m2.jpg")
        m3 = self._create_media("m3.jpg")

        add_media_to_album(self.db, child.id, [m1.id])
        add_media_to_album(self.db, root.id, [m2.id])

        # Search album:Forests -> only m1
        q_direct = parse_search_query(f"album:{child.id}")
        query1 = self.db.query(Media)
        query1 = apply_search_criteria(query1, q_direct, self.db)
        direct_ids = [m.id for m in query1.all()]
        self.assertEqual(direct_ids, [m1.id])

        # Search album_tree:Nature -> m1 and m2
        q_tree = parse_search_query(f"album_tree:{root.id}")
        query2 = self.db.query(Media)
        query2 = apply_search_criteria(query2, q_tree, self.db)
        tree_ids = [m.id for m in query2.all()]
        self.assertIn(m1.id, tree_ids)
        self.assertIn(m2.id, tree_ids)
        self.assertNotIn(m3.id, tree_ids)

    def test_backfill_recalculate_all_album_metrics(self):
        root = self._create_album("BackfillRoot")
        child = self._create_album("BackfillChild", parent_id=root.id)
        m1 = self._create_media("bf1.jpg", rating=RatingEnum.explicit)
        m2 = self._create_media("bf2.jpg", rating=RatingEnum.safe)

        # Directly insert into association table without calling helpers
        self.db.execute(blombooru_album_media.insert().values([
            {"album_id": child.id, "media_id": m1.id},
            {"album_id": root.id, "media_id": m2.id}
        ]))
        self.db.commit()

        # Metrics are currently 0
        self.db.refresh(root)
        self.db.refresh(child)
        self.assertEqual(root.cached_media_count, 0)
        self.assertEqual(child.cached_media_count, 0)

        # Run full backfill
        recalculate_all_album_metrics(self.db)

        self.db.refresh(root)
        self.db.refresh(child)
        self.assertEqual(child.cached_media_count, 1)
        self.assertEqual(child.cached_direct_media_count, 1)
        self.assertEqual(child.cached_rating, RatingEnum.explicit)

        self.assertEqual(root.cached_media_count, 2)
        self.assertEqual(root.cached_direct_media_count, 1)
        self.assertEqual(root.cached_rating, RatingEnum.explicit)

    def test_get_albums_pagination_and_query_count(self):
        for i in range(10):
            alb = self._create_album(f"Album_{i:02d}")
            m = self._create_media(f"m_{i}.jpg")
            add_media_to_album(self.db, alb.id, [m.id])

        queries = []
        def count_queries(conn, cursor, statement, parameters, context, executemany):
            queries.append(statement)

        event.listen(self.engine, "before_cursor_execute", count_queries)
        try:
            res = asyncio.run(get_albums(DummyRequest(), page=1, limit=5, sort="name", order="asc", db=self.db))
            self.assertEqual(len(res["items"]), 5)
            self.assertEqual(res["total"], 10)
            self.assertEqual(res["pages"], 2)
            # 1 count query, 1 paginated albums query, 1 hierarchy links query, 1 batched windowed thumbnails query = 4 SQL statements
            self.assertLessEqual(len(queries), 4)
        finally:
            event.remove(self.engine, "before_cursor_execute", count_queries)

    def test_root_album_thumbnails_from_descendants(self):
        # Root has 0 direct media, Child1 has 2 media, Child2 has 2 media
        root = self._create_album("RootContainer")
        child1 = self._create_album("Sub1", parent_id=root.id)
        child2 = self._create_album("Sub2", parent_id=root.id)

        m1 = self._create_media("s1_1.jpg")
        m2 = self._create_media("s1_2.jpg")
        m3 = self._create_media("s2_1.jpg")
        m4 = self._create_media("s2_2.jpg")

        add_media_to_album(self.db, child1.id, [m1.id, m2.id])
        add_media_to_album(self.db, child2.id, [m3.id, m4.id])

        thumbs = get_bulk_album_thumbnails([root.id], self.db, count=4)
        self.assertIn(root.id, thumbs)
        self.assertEqual(len(thumbs[root.id]), 4)
        expected_urls = {f"/api/media/{mid}/thumbnail" for mid in [m1.id, m2.id, m3.id, m4.id]}
        self.assertEqual(set(thumbs[root.id]), expected_urls)

    def test_recalculate_endpoint(self):
        from backend.app.routes.albums import recalculate_all_albums_endpoint
        root = self._create_album("RecalcRoot")
        child = self._create_album("RecalcChild", parent_id=root.id)
        m = self._create_media("recalc.jpg", rating=RatingEnum.explicit)

        # Directly insert to bypass automatic recalculation
        self.db.execute(blombooru_album_media.insert().values([
            {"album_id": child.id, "media_id": m.id}
        ]))
        self.db.commit()

        self.db.refresh(root)
        self.assertEqual(root.cached_media_count, 0)

        # Trigger admin recalculate endpoint
        res = asyncio.run(recalculate_all_albums_endpoint(current_user=self.admin_user, db=self.db))
        self.assertIn("message", res)

        self.db.refresh(root)
        self.db.refresh(child)
        self.assertEqual(child.cached_media_count, 1)
        self.assertEqual(child.cached_rating, RatingEnum.explicit)
        self.assertEqual(root.cached_media_count, 1)
        self.assertEqual(root.cached_rating, RatingEnum.explicit)

if __name__ == "__main__":
    unittest.main()
