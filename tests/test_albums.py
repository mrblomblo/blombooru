import asyncio
import unittest
from datetime import datetime
from sqlalchemy import event

from backend.app.auth import create_access_token
from backend.app.enums import FileTypeEnum
from backend.app.models import (Album, Media, RatingEnum, User,
                                blombooru_album_hierarchy, blombooru_album_media)
from backend.app.routes.albums import (autocomplete_albums, clear_album_media_order,
                                       clear_root_albums_order, clear_sub_albums_order,
                                       delete_album,
                                       get_album_contents, get_album_statistics,
                                       get_albums, get_albums_tree,
                                       reorder_album_media, reorder_root_albums,
                                       reorder_sub_albums)
from backend.app.schemas import AlbumReorderRequest, MediaReorderRequest
from backend.app.utils.album_utils import (add_media_to_album, delete_album_cascade,
                                          get_bulk_album_thumbnails,
                                          handle_media_deleted, handle_media_rating_changed,
                                          recalculate_album_metrics,
                                          recalculate_all_album_metrics,
                                          reparent_album)
from backend.app.utils.search_parser import apply_search_criteria, parse_search_query
from tests.test_base import BackupTestBase

class DummyURL:
    def __init__(self, path: str = "/api/albums"):
        self.path = path

    def __str__(self):
        return self.path

class DummyRequest:
    def __init__(self, path: str = "/api/albums", cookies=None, headers=None, query_params=None, user=None):
        self.url = DummyURL(path)
        self.cookies = cookies or {}
        self.headers = headers or {}
        self.query_params = query_params or {}
        self.state = type("State", (), {"current_api_key": None, "user": user})()

class TestAlbumArchitecture(BackupTestBase):
    def setUp(self):
        super().setUp()
        self.admin_user = User(username="admin", password_hash="hash")
        self.db.add(self.admin_user)
        self.db.commit()
        self.db.refresh(self.admin_user)
        self.admin_token = create_access_token({"sub": self.admin_user.username})

    def _admin_request(self):
        return DummyRequest(cookies={"admin_token": self.admin_token}, user=self.admin_user)

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

    def test_delete_album_endpoint_recalculates_ancestor_metrics(self):
        root = self._create_album("Root")
        child = self._create_album("Child", parent_id=root.id)
        m = self._create_media("m.jpg", rating=RatingEnum.explicit)
        add_media_to_album(self.db, child.id, [m.id])

        self.db.refresh(root)
        self.assertEqual(root.cached_media_count, 1)
        self.assertEqual(root.cached_rating, RatingEnum.explicit)

        # Delete child via route
        res = asyncio.run(delete_album(
            album_id=child.id,
            cascade=False,
            current_user=self.admin_user,
            db=self.db
        ))
        self.assertEqual(res["message"], "Album deleted successfully")

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
        self.assertEqual(len(thumbs[root.id]["paths"]), 4)
        self.assertEqual(len(thumbs[root.id]["ratings"]), 4)
        expected_urls = {f"/api/media/{mid}/thumbnail" for mid in [m1.id, m2.id, m3.id, m4.id]}
        self.assertEqual(set(thumbs[root.id]["paths"]), expected_urls)

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

    def test_prune_endpoint(self):
        from backend.app.routes.albums import prune_all_albums_endpoint
        
        root = self._create_album("Root")
        a = self._create_album("A", parent_id=root.id) # empty album (no media, no child); should be pruned
        b = self._create_album("B", parent_id=root.id) # album with a media; must not be pruned
        c1 = self._create_album("C1", parent_id=root.id) # album with no media and an empty child; should be pruned incl. the child
        c2 = self._create_album("C2", parent_id=c1.id)
        d1 = self._create_album("D1", parent_id=root.id) # album with no media and a child; should not be pruned because the child has a media
        d2 = self._create_album("D2", parent_id=d1.id)
        
        m = self._create_media("m1.jpg")
        add_media_to_album(self.db, b.id, [m.id])
        add_media_to_album(self.db, d2.id, [m.id])

        self.assertEqual(root.cached_media_count, 2)
        
        res = asyncio.run(prune_all_albums_endpoint(current_user=self.admin_user, db=self.db))
        self.assertIn("message", res)
        self.assertIn("count", res)
        self.assertEqual(res["count"], 3)

        self.db.refresh(root)
        self.assertEqual(root.cached_media_count, 2)
        self.assertIsNone(self.db.query(Album).filter(Album.id == a.id).first())
        self.assertIsNone(self.db.query(Album).filter(Album.id == c1.id).first())
        self.assertIsNone(self.db.query(Album).filter(Album.id == c2.id).first())
        self.assertIsNotNone(self.db.query(Album).filter(Album.id == b.id).first())
        self.assertIsNotNone(self.db.query(Album).filter(Album.id == d1.id).first())
        self.assertIsNotNone(self.db.query(Album).filter(Album.id == d2.id).first())

    def test_root_album_manual_reorder_and_sorting(self):
        a1 = self._create_album("Alpha")
        a2 = self._create_album("Beta")
        a3 = self._create_album("Gamma")

        # Initial sort positions should be None
        self.assertIsNone(a1.sort_position)
        self.assertIsNone(a2.sort_position)
        self.assertIsNone(a3.sort_position)

        # Prior to manual reorder, manual sort should use fallback sort (e.g. name asc/desc)
        fb_asc = asyncio.run(get_albums(
            DummyRequest(),
            sort="manual",
            fallback_sort="name",
            fallback_order="asc",
            root_only=True,
            db=self.db
        ))
        self.assertEqual([item.id for item in fb_asc["items"]], [a1.id, a2.id, a3.id])

        fb_desc = asyncio.run(get_albums(
            DummyRequest(),
            sort="manual",
            fallback_sort="name",
            fallback_order="desc",
            root_only=True,
            db=self.db
        ))
        self.assertEqual([item.id for item in fb_desc["items"]], [a3.id, a2.id, a1.id])

        # Reorder root albums: Gamma (a3), Alpha (a1), Beta (a2)
        res = asyncio.run(reorder_root_albums(
            AlbumReorderRequest(album_ids=[a3.id, a1.id, a2.id]),
            current_user=self.admin_user,
            db=self.db
        ))
        self.assertIn("message", res)

        self.db.refresh(a1)
        self.db.refresh(a2)
        self.db.refresh(a3)
        self.assertEqual(a3.sort_position, 0)
        self.assertEqual(a1.sort_position, 1)
        self.assertEqual(a2.sort_position, 2)

        # Get albums with manual sort asc
        albums_asc = asyncio.run(get_albums(
            DummyRequest(),
            sort="manual",
            order="asc",
            root_only=True,
            db=self.db
        ))
        returned_ids_asc = [item.id for item in albums_asc["items"]]
        self.assertEqual(returned_ids_asc, [a3.id, a1.id, a2.id])

        # Get albums with manual sort desc
        albums_desc = asyncio.run(get_albums(
            DummyRequest(),
            sort="manual",
            order="desc",
            root_only=True,
            db=self.db
        ))
        returned_ids_desc = [item.id for item in albums_desc["items"]]
        # Manual sorting should strictly preserve the manual order regardless of order parameter
        self.assertEqual(returned_ids_desc, [a3.id, a1.id, a2.id])

        # Clear root album ordering
        clear_res = asyncio.run(clear_root_albums_order(
            current_user=self.admin_user,
            db=self.db
        ))
        self.assertIn("message", clear_res)

        self.db.refresh(a1)
        self.db.refresh(a2)
        self.db.refresh(a3)
        self.assertIsNone(a1.sort_position)
        self.assertIsNone(a2.sort_position)
        self.assertIsNone(a3.sort_position)

        # After clearing manual order, manual sort should revert to using fallback sort
        fb_after_clear = asyncio.run(get_albums(
            DummyRequest(),
            sort="manual",
            fallback_sort="name",
            fallback_order="asc",
            root_only=True,
            db=self.db
        ))
        self.assertEqual([item.id for item in fb_after_clear["items"]], [a1.id, a2.id, a3.id])

    def test_sub_album_manual_reorder_and_sorting(self):
        parent = self._create_album("ParentFolder")
        sub1 = self._create_album("SubOne", parent_id=parent.id)
        sub2 = self._create_album("SubTwo", parent_id=parent.id)
        sub3 = self._create_album("SubThree", parent_id=parent.id)

        # Prior to manual reorder, manual sort should use fallback sort (e.g. name asc/desc)
        fb_sub_asc = asyncio.run(get_album_contents(
            DummyRequest(),
            album_id=parent.id,
            sort="manual",
            fallback_sort="name",
            fallback_order="asc",
            db=self.db
        ))
        self.assertEqual([album.id for album in fb_sub_asc["albums"]], [sub1.id, sub3.id, sub2.id])

        fb_sub_desc = asyncio.run(get_album_contents(
            DummyRequest(),
            album_id=parent.id,
            sort="manual",
            fallback_sort="name",
            fallback_order="desc",
            db=self.db
        ))
        self.assertEqual([album.id for album in fb_sub_desc["albums"]], [sub2.id, sub3.id, sub1.id])

        # Reorder sub-albums under parent: SubTwo (sub2), SubThree (sub3), SubOne (sub1)
        res = asyncio.run(reorder_sub_albums(
            album_id=parent.id,
            data=AlbumReorderRequest(album_ids=[sub2.id, sub3.id, sub1.id]),
            current_user=self.admin_user,
            db=self.db
        ))
        self.assertIn("message", res)

        # Verify through get_album_contents
        contents = asyncio.run(get_album_contents(
            DummyRequest(),
            album_id=parent.id,
            sort="manual",
            order="asc",
            db=self.db
        ))
        sub_ids = [album.id for album in contents["albums"]]
        self.assertEqual(sub_ids, [sub2.id, sub3.id, sub1.id])

        # Clear sub-albums reorder
        clear_res = asyncio.run(clear_sub_albums_order(
            album_id=parent.id,
            current_user=self.admin_user,
            db=self.db
        ))
        self.assertIn("message", clear_res)

        rows = self.db.execute(
            blombooru_album_hierarchy.select().where(
                blombooru_album_hierarchy.c.parent_album_id == parent.id
            )
        ).fetchall()
        for r in rows:
            self.assertIsNone(r.sort_position)

        # After clearing manual order, manual sort should revert to using fallback sort
        fb_sub_cleared = asyncio.run(get_album_contents(
            DummyRequest(),
            album_id=parent.id,
            sort="manual",
            fallback_sort="name",
            fallback_order="asc",
            db=self.db
        ))
        self.assertEqual([album.id for album in fb_sub_cleared["albums"]], [sub1.id, sub3.id, sub2.id])

    def test_media_manual_reorder_and_sorting(self):
        alb = self._create_album("MediaGallery")
        m1 = self._create_media("item1.jpg")
        m2 = self._create_media("item2.jpg")
        m3 = self._create_media("item3.jpg")

        add_media_to_album(self.db, alb.id, [m1.id, m2.id, m3.id])

        # Prior to manual reorder, manual sort should use fallback sort (e.g. filename asc/desc)
        fb_media_asc = asyncio.run(get_album_contents(
            DummyRequest(),
            album_id=alb.id,
            sort="manual",
            fallback_sort="filename",
            fallback_order="asc",
            db=self.db
        ))
        self.assertEqual([m.id for m in fb_media_asc["media"]], [m1.id, m2.id, m3.id])

        fb_media_desc = asyncio.run(get_album_contents(
            DummyRequest(),
            album_id=alb.id,
            sort="manual",
            fallback_sort="filename",
            fallback_order="desc",
            db=self.db
        ))
        self.assertEqual([m.id for m in fb_media_desc["media"]], [m3.id, m2.id, m1.id])

        # Reorder media: m3, m1, m2
        res = asyncio.run(reorder_album_media(
            album_id=alb.id,
            data=MediaReorderRequest(media_ids=[m3.id, m1.id, m2.id]),
            current_user=self.admin_user,
            db=self.db
        ))
        self.assertIn("message", res)

        # Query contents with sort=manual asc
        contents_asc = asyncio.run(get_album_contents(
            DummyRequest(),
            album_id=alb.id,
            sort="manual",
            order="asc",
            db=self.db
        ))
        media_ids_asc = [m.id for m in contents_asc["media"]]
        self.assertEqual(media_ids_asc, [m3.id, m1.id, m2.id])

        # Query contents with sort=manual desc
        contents_desc = asyncio.run(get_album_contents(
            DummyRequest(),
            album_id=alb.id,
            sort="manual",
            order="desc",
            db=self.db
        ))
        media_ids_desc = [m.id for m in contents_desc["media"]]
        # Manual sorting should strictly preserve the manual order regardless of order parameter
        self.assertEqual(media_ids_desc, [m3.id, m1.id, m2.id])

        # Clear media order
        clear_res = asyncio.run(clear_album_media_order(
            album_id=alb.id,
            current_user=self.admin_user,
            db=self.db
        ))
        self.assertIn("message", clear_res)

        rows = self.db.execute(
            blombooru_album_media.select().where(
                blombooru_album_media.c.album_id == alb.id
            )
        ).fetchall()
        for r in rows:
            self.assertIsNone(r.sort_position)

        # After clearing manual order, manual sort should revert to using fallback sort
        fb_media_cleared = asyncio.run(get_album_contents(
            DummyRequest(),
            album_id=alb.id,
            sort="manual",
            fallback_sort="filename",
            fallback_order="asc",
            db=self.db
        ))
        self.assertEqual([m.id for m in fb_media_cleared["media"]], [m1.id, m2.id, m3.id])

    def test_reparent_album_resets_sort_position(self):
        root1 = self._create_album("Parent1")
        root2 = self._create_album("ToBeChild")

        # Manually assign sort_position to root2
        root2.sort_position = 15
        self.db.commit()
        self.db.refresh(root2)
        self.assertEqual(root2.sort_position, 15)

        # Reparent root2 under root1
        reparent_album(self.db, root2.id, root1.id)
        self.db.refresh(root2)

        # Root sort_position should now be None
        self.assertIsNone(root2.sort_position)

        # Hierarchy link should have sort_position as None
        row = self.db.execute(
            blombooru_album_hierarchy.select().where(
                blombooru_album_hierarchy.c.parent_album_id == root1.id,
                blombooru_album_hierarchy.c.child_album_id == root2.id
            )
        ).first()
        self.assertIsNotNone(row)
        self.assertIsNone(row.sort_position)

    def test_album_thumbnails_ordering(self):
        alb = self._create_album("ThumbTestAlbum")
        m1 = self._create_media("t1.jpg")
        m2 = self._create_media("t2.jpg")
        m3 = self._create_media("t3.jpg")
        m4 = self._create_media("t4.jpg")

        add_media_to_album(self.db, alb.id, [m1.id, m2.id, m3.id, m4.id])

        # Initially no sort_position set: thumbnails returned without error
        thumbs_initial = get_bulk_album_thumbnails([alb.id], self.db, count=4)
        self.assertEqual(len(thumbs_initial[alb.id]["paths"]), 4)
        self.assertEqual(len(thumbs_initial[alb.id]["ratings"]), 4)

        # Set manual sort order: m4 first, m2 second
        asyncio.run(reorder_album_media(
            alb.id,
            MediaReorderRequest(media_ids=[m4.id, m2.id]),
            current_user=self.admin_user,
            db=self.db
        ))

        thumbs_ordered = get_bulk_album_thumbnails([alb.id], self.db, count=4)
        self.assertEqual(len(thumbs_ordered[alb.id]["paths"]), 4)
        # First two thumbnails must correspond to m4 and m2
        self.assertEqual(thumbs_ordered[alb.id]["paths"][0], f"/api/media/{m4.id}/thumbnail")
        self.assertEqual(thumbs_ordered[alb.id]["paths"][1], f"/api/media/{m2.id}/thumbnail")
    def test_album_pagination_large_limit(self):
        # Plain limit=5000 is preserved and not clamped
        large_limit_res = asyncio.run(get_albums(
            DummyRequest(),
            limit=5000,
            db=self.db
        ))
        self.assertEqual(large_limit_res["limit"], 5000)

if __name__ == "__main__":
    unittest.main()
