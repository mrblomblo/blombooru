import unittest
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database import Base
from backend.app.enums import FileTypeEnum, RatingEnum, TagCategoryEnum
from backend.app.models import Album, Media, Tag
from backend.app.utils.media_sort import get_media_sort_clauses
from backend.app.utils.search_parser import (apply_search_criteria,
                                            canonicalize_query,
                                            fold_condition_items,
                                            parse_search_query)

class TestSearchParser(unittest.TestCase):

    def test_fold_condition_items_exact_and_greater(self):
        # 4 and >4 fold to >=4, which swallows 6 and 8
        items = ["6", "4", "8", ">4"]
        folded = fold_condition_items(items)
        self.assertEqual(folded, [">=4"])

    def test_fold_condition_items_exact_and_less(self):
        # 4 and <4 fold to <=4, which swallows 1 and 2
        items = ["1", "2", "4", "<4", "10"]
        folded = fold_condition_items(items)
        self.assertEqual(folded, ["10", "<=4"])

    def test_fold_condition_items_subsumed_by_le(self):
        # gentags:5,6,<=15 -> <=15
        items = ["5", "6", "<=15"]
        folded = fold_condition_items(items)
        self.assertEqual(folded, ["<=15"])

    def test_fold_condition_items_subsumed_by_ge(self):
        # width:800,1024,1920,>=1000 -> 800,>=1000
        items = ["800", "1024", "1920", ">=1000"]
        folded = fold_condition_items(items)
        self.assertEqual(folded, ["800", ">=1000"])

    def test_fold_condition_items_subsumed_by_range(self):
        # id:5,10,1..20 -> 1..20
        items = ["5", "10", "1..20"]
        folded = fold_condition_items(items)
        self.assertEqual(folded, ["1..20"])

    def test_fold_condition_items_filesize_subsumption(self):
        # filesize:500kb,<=10mb -> <=10mb
        items = ["500kb", "<=10mb"]
        folded = fold_condition_items(items)
        self.assertEqual(folded, ["<=10mb"])

    def test_fold_condition_items_date_subsumption(self):
        # date:2024-01-01,<=2024-06-01 -> <=2024-06-01
        items = ["2024-01-01", "<=2024-06-01"]
        folded = fold_condition_items(items)
        self.assertEqual(folded, ["<=2024-06-01"])

    def test_fold_condition_items_custom_date_subsumption(self):
        items = ["2024-01-01", "<=2024-06-01"]
        folded = fold_condition_items(items, key="custom_date")
        self.assertEqual(folded, ["<=2024-06-01"])

    def test_canonicalize_custom_date(self):
        canonical = canonicalize_query("custom_date:2024-01-01 custom_date:<=2024-06-01")
        self.assertEqual(canonical, "custom_date:<=2024-06-01")

    def test_canonicalize_custom_age(self):
        canonical = canonicalize_query("custom_age:2w custom_age:<=1mo")
        self.assertEqual(canonical, "custom_age:<=1mo")

    def test_fold_condition_items_age_subsumption(self):
        # age:2w,<=1mo -> <=1mo
        items = ["2w", "<=1mo"]
        folded = fold_condition_items(items)
        self.assertEqual(folded, ["<=1mo"])

    def test_fold_condition_items_custom_age_subsumption(self):
        items = ["2w", "<=1mo"]
        folded = fold_condition_items(items, key="custom_age")
        self.assertEqual(folded, ["<=1mo"])

    def test_fold_condition_items_operator_subsumption(self):
        # <=10,<=20 -> <=20
        items = ["<=10", "<=20"]
        folded = fold_condition_items(items)
        self.assertEqual(folded, ["<=20"])

        # >=20,>=10 -> >=10
        items_ge = [">=20", ">=10"]
        folded_ge = fold_condition_items(items_ge)
        self.assertEqual(folded_ge, [">=10"])

    def test_fold_condition_items_non_overlapping(self):
        items = ["13", "16", "<8", ">91"]
        folded = fold_condition_items(items)
        self.assertEqual(folded, ["13", "16", "<8", ">91"])

    def test_fold_condition_items_deduplication(self):
        items = ["6,1", "8,<4", "1", "6"]
        folded = fold_condition_items(items)
        # 1 is swallowed by <4, 6 and 8 remain
        self.assertEqual(folded, ["6", "8", "<4"])

    def test_canonicalize_query_user_example_swallowed_number(self):
        query = "gentags:5,6,<=15"
        canonical = canonicalize_query(query)
        self.assertEqual(canonical, "gentags:<=15")

    def test_canonicalize_query_user_example_1(self):
        query = "rating:s human rating:q gentags:6,1 gentags:8,<4 hair"
        canonical = canonicalize_query(query)
        # 1 is swallowed by <4
        self.assertEqual(canonical, "rating:s,q human gentags:6,8,<4 hair")

    def test_canonicalize_query_user_example_2(self):
        query = "gentags:6,4 gentags:8,>4"
        canonical = canonicalize_query(query)
        self.assertEqual(canonical, "gentags:>=4")

    def test_canonicalize_query_negated(self):
        query = "-rating:e cat -rating:q -tagcount:0 -tagcount:>50"
        canonical = canonicalize_query(query)
        self.assertEqual(canonical, "-rating:e,q cat -tagcount:0,>50")

    def test_canonicalize_query_mixed_positive_and_negated(self):
        query = "rating:s human -rating:e gentags:6,1 rating:q gentags:8,<4 -rating:q"
        canonical = canonicalize_query(query)
        self.assertEqual(canonical, "rating:s,q human -rating:e,q gentags:6,8,<4")

    def test_canonicalize_query_singular_keys(self):
        query = "order:filesize_desc cat order:id_asc"
        canonical = canonicalize_query(query)
        self.assertEqual(canonical, "order:id_asc cat")

    def test_canonicalize_query_tag_deduplication(self):
        query = "cat dog cat -bird -bird *eyes* *eyes*"
        canonical = canonicalize_query(query)
        self.assertEqual(canonical, "cat dog -bird *eyes*")

    def test_canonicalize_query_empty_or_whitespace(self):
        self.assertEqual(canonicalize_query(""), "")
        self.assertEqual(canonicalize_query("   "), "")

    def test_canonicalize_query_album_tree(self):
        query = "album_tree:1 pool_tree:sub_album"
        canonical = canonicalize_query(query)
        self.assertEqual(canonical, "album_tree:1 pool_tree:sub_album")

    def test_parse_search_query_multi_values(self):
        parsed = parse_search_query("gentags:13,16,<8,>91 -rating:e,q width:>1920,<500")
        self.assertIn("gentags", parsed["meta"])
        self.assertEqual(parsed["meta"]["gentags"][0]["value"], "13,16,<8,>91")
        self.assertFalse(parsed["meta"]["gentags"][0]["negated"])

        self.assertIn("rating", parsed["meta"])
        self.assertEqual(parsed["meta"]["rating"][0]["value"], "e,q")
        self.assertTrue(parsed["meta"]["rating"][0]["negated"])

        self.assertIn("width", parsed["meta"])
        self.assertEqual(parsed["meta"]["width"][0]["value"], ">1920,<500")

    def test_fold_condition_items_age_minute_disambiguation(self):
        # age: 10m is 10 minutes, <=20m is <=20 minutes; 10m is swallowed by <=20m
        items = ["10m", "<=20m"]
        folded = fold_condition_items(items, key="age")
        self.assertEqual(folded, ["<=20m"])
        canonical = canonicalize_query("age:10m age:<=20m")
        self.assertEqual(canonical, "age:<=20m")

    def test_fold_condition_items_filesize_megabyte_disambiguation(self):
        # filesize: 10m is 10MB, <=20m is <=20MB; 10m is swallowed by <=20m
        items = ["10m", "<=20m"]
        folded = fold_condition_items(items, key="filesize")
        self.assertEqual(folded, ["<=20m"])
        canonical = canonicalize_query("filesize:10m filesize:<=20m")
        self.assertEqual(canonical, "filesize:<=20m")

    def test_tag_with_colon_parsed_as_tag(self):
        # re:zero -- "re" is not a known qualifier, so the whole thing is a tag
        parsed = parse_search_query("re:zero")
        self.assertEqual(parsed["tags"]["include"], ["re:zero"])
        self.assertEqual(parsed["meta"], {})

    def test_tag_with_colon_negated(self):
        parsed = parse_search_query("-re:zero")
        self.assertEqual(parsed["tags"]["exclude"], ["re:zero"])
        self.assertEqual(parsed["tags"]["include"], [])

    def test_tag_with_multiple_colons(self):
        # arknights:_endfield -- "arknights" is not a known qualifier
        parsed = parse_search_query("arknights:_endfield")
        self.assertEqual(parsed["tags"]["include"], ["arknights:_endfield"])
        self.assertEqual(parsed["meta"], {})

    def test_tag_with_colon_mixed_with_qualifiers(self):
        parsed = parse_search_query("re:zero rating:s")
        self.assertEqual(parsed["tags"]["include"], ["re:zero"])
        self.assertIn("rating", parsed["meta"])
        self.assertEqual(parsed["meta"]["rating"][0]["value"], "s")

    def test_canonicalize_tag_with_colon(self):
        # canonicalize_query preserves order of first appearance
        canonical = canonicalize_query("re:zero rating:s")
        self.assertEqual(canonical, "re:zero rating:s")

    def test_canonicalize_negated_tag_with_colon(self):
        canonical = canonicalize_query("-re:zero rating:s")
        self.assertEqual(canonical, "-re:zero rating:s")

    def test_leading_colon_tag_still_works(self):
        # :d has nothing before the colon, so it's always been a plain tag
        parsed = parse_search_query(":d")
        self.assertEqual(parsed["tags"]["include"], [":d"])
        self.assertEqual(parsed["meta"], {})

    def test_canonicalize_leading_colon_tags(self):
        canonical = canonicalize_query(":d :q -:d")
        self.assertEqual(canonical, ":d :q -:d")

    def test_tag_with_parentheses_and_colon(self):
        parsed = parse_search_query("the_dahlia_(honkai:_star_rail) -the_dahlia_(honkai:_star_rail)")
        self.assertEqual(parsed["tags"]["include"], ["the_dahlia_(honkai:_star_rail)"])
        self.assertEqual(parsed["tags"]["exclude"], ["the_dahlia_(honkai:_star_rail)"])
        self.assertEqual(parsed["meta"], {})

    def test_canonicalize_tag_with_parentheses_and_colon(self):
        canonical = canonicalize_query("the_dahlia_(honkai:_star_rail) rating:s")
        self.assertEqual(canonical, "the_dahlia_(honkai:_star_rail) rating:s")

    def test_known_qualifier_not_treated_as_tag(self):
        # rating:s must still be a qualifier, not a tag
        parsed = parse_search_query("rating:s")
        self.assertNotIn("rating:s", parsed["tags"]["include"])
        self.assertIn("rating", parsed["meta"])

class TestSearchParserDBIntegration(unittest.TestCase):

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

        # Seed tags
        self.t_general1 = Tag(name="blue_sky", category=TagCategoryEnum.general, post_count=1)
        self.t_general2 = Tag(name="clouds", category=TagCategoryEnum.general, post_count=1)
        self.t_general3 = Tag(name="sunset", category=TagCategoryEnum.general, post_count=1)
        self.t_artist = Tag(name="artist_foo", category=TagCategoryEnum.artist, post_count=1)
        self.t_char = Tag(name="miku", category=TagCategoryEnum.character, post_count=1)

        self.db.add_all([self.t_general1, self.t_general2, self.t_general3, self.t_artist, self.t_char])
        self.db.commit()

        # Seed album
        self.album1 = Album(id=1, name="favorites")
        self.db.add(self.album1)
        self.db.commit()

        # Seed media
        now = datetime.now()
        self.m1 = Media(
            id=1,
            filename="image1.png",
            path="media/image1.png",
            hash="hash1",
            file_type=FileTypeEnum.image,
            file_size=1000000,
            width=1920,
            height=1080,
            duration=None,
            rating=RatingEnum.safe,
            uploaded_at=now - timedelta(days=5),
            custom_date=datetime(2021, 5, 10, 12, 0, 0),
            source="https://source-a.example.com/post1"
        )
        self.m1.tags.extend([self.t_general1, self.t_artist])
        self.m1.albums.append(self.album1)

        self.m2 = Media(
            id=2,
            filename="image2.jpg",
            path="media/image2.jpg",
            hash="hash2",
            file_type=FileTypeEnum.image,
            file_size=5000000,
            width=800,
            height=600,
            duration=None,
            rating=RatingEnum.questionable,
            uploaded_at=now - timedelta(days=2),
            custom_date=datetime(2023, 8, 20, 15, 0, 0),
            source="https://source-b.example.com/art2"
        )
        self.m2.tags.extend([self.t_general1, self.t_general2, self.t_general3, self.t_char])
        self.m2.albums.append(self.album1)

        self.m3 = Media(
            id=3,
            filename="clip.mp4",
            path="media/clip.mp4",
            hash="hash3",
            file_type=FileTypeEnum.video,
            file_size=20000000,
            width=1280,
            height=720,
            duration=45.5,
            rating=RatingEnum.explicit,
            uploaded_at=now - timedelta(hours=1),
            custom_date=datetime(2020, 1, 1, 9, 0, 0),
            source=None
        )
        self.m3.tags.extend([self.t_char])

        # m4: Child of m1, FileTypeEnum.gif, ~52.45 MB (55000000 bytes)
        self.m4 = Media(
            id=4,
            filename="anim.gif",
            path="media/anim.gif",
            hash="hash4",
            file_type=FileTypeEnum.gif,
            file_size=55000000,
            width=500,
            height=500,
            duration=None,
            rating=RatingEnum.safe,
            uploaded_at=now - timedelta(days=10),
            custom_date=datetime(2024, 12, 25, 18, 0, 0),
            source="https://example.com/anim",
            parent_id=1
        )

        # m5: File with .gif filename but file_type image
        self.m5 = Media(
            id=5,
            filename="pic.gif",
            path="media/pic.gif",
            hash="hash5",
            file_type=FileTypeEnum.image,
            file_size=60000000,
            width=600,
            height=600,
            duration=None,
            rating=RatingEnum.safe,
            uploaded_at=now - timedelta(days=20),
            custom_date=datetime(2019, 6, 15, 8, 0, 0),
            source=None
        )

        self.db.add_all([self.m1, self.m2, self.m3, self.m4, self.m5])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_multi_gentags_filter(self):
        # m1 has 1 general tag, m2 has 3 general tags, m3 has 0 general tags
        # Query: gentags:1,3
        parsed = parse_search_query("gentags:1,3")
        q = apply_search_criteria(self.db.query(Media), parsed, self.db)
        results = q.all()
        ids = [m.id for m in results]
        self.assertIn(1, ids)
        self.assertIn(2, ids)
        self.assertNotIn(3, ids)

        # Query with operator: gentags:<1,>=3 (should match 0 or >=3 -> m3 and m2)
        parsed2 = parse_search_query("gentags:<1,>=3")
        q2 = apply_search_criteria(self.db.query(Media), parsed2, self.db)
        ids2 = [m.id for m in q2.all()]
        self.assertIn(2, ids2)
        self.assertIn(3, ids2)
        self.assertNotIn(1, ids2)

    def test_multi_rating_filter(self):
        # Query: rating:s,q
        parsed = parse_search_query("rating:s,q")
        q = apply_search_criteria(self.db.query(Media), parsed, self.db)
        ids = [m.id for m in q.all()]
        self.assertIn(1, ids)
        self.assertIn(2, ids)
        self.assertNotIn(3, ids)

        # Negated: -rating:e
        parsed_neg = parse_search_query("-rating:e")
        q_neg = apply_search_criteria(self.db.query(Media), parsed_neg, self.db)
        ids_neg = [m.id for m in q_neg.all()]
        self.assertIn(1, ids_neg)
        self.assertIn(2, ids_neg)
        self.assertNotIn(3, ids_neg)

    def test_multi_filetype_filter(self):
        # Query: filetype:png,video
        parsed = parse_search_query("filetype:png,video")
        q = apply_search_criteria(self.db.query(Media), parsed, self.db)
        ids = [m.id for m in q.all()]
        self.assertIn(1, ids)
        self.assertIn(3, ids)
        self.assertNotIn(2, ids)

    def test_multi_filesize_filter(self):
        # m1 is ~1MB (1000000), m2 is ~5MB (5000000), m3 is ~20MB (20000000)
        # Query: filesize:<2mb,>15mb
        parsed = parse_search_query("filesize:<2mb,>15mb")
        q = apply_search_criteria(self.db.query(Media), parsed, self.db)
        ids = [m.id for m in q.all()]
        self.assertIn(1, ids)
        self.assertIn(3, ids)
        self.assertNotIn(2, ids)

    def test_source_filter_with_none_and_prefix(self):
        # Query: source:none,source-a
        parsed = parse_search_query("source:none,source-a")
        q = apply_search_criteria(self.db.query(Media), parsed, self.db)
        ids = [m.id for m in q.all()]
        self.assertIn(1, ids)
        self.assertIn(3, ids)
        self.assertNotIn(2, ids)

    def test_filename_exact_with_extension(self):
        # filename:image1.png -> only m1
        parsed = parse_search_query("filename:image1.png")
        ids = [m.id for m in apply_search_criteria(self.db.query(Media), parsed, self.db).all()]
        self.assertIn(1, ids)
        self.assertNotIn(2, ids)
        self.assertNotIn(3, ids)

    def test_filename_stem_without_extension(self):
        # filename:image1 -> matches image1.png (m1) via stem-only match
        parsed = parse_search_query("filename:image1")
        ids = [m.id for m in apply_search_criteria(self.db.query(Media), parsed, self.db).all()]
        self.assertIn(1, ids)
        self.assertNotIn(2, ids)

    def test_filename_wildcard_prefix(self):
        # m2 = image2.jpg, m3 = clip.mp4 -- neither starts with "image1"
        # Use filetype:jpg which covers m2; here test wildcard "image*"
        parsed = parse_search_query("filename:image*")
        ids = [m.id for m in apply_search_criteria(self.db.query(Media), parsed, self.db).all()]
        self.assertIn(1, ids)
        self.assertIn(2, ids)
        self.assertNotIn(3, ids)

    def test_filename_wildcard_extension(self):
        # filename:*.jpg -> m2 (image2.jpg) only; m1 is .png, m3 is .mp4
        parsed = parse_search_query("filename:*.jpg")
        ids = [m.id for m in apply_search_criteria(self.db.query(Media), parsed, self.db).all()]
        self.assertIn(2, ids)
        self.assertNotIn(1, ids)
        self.assertNotIn(3, ids)

    def test_filename_negated(self):
        # -filename:*.jpg -> everything except m2
        parsed = parse_search_query("-filename:*.jpg")
        ids = [m.id for m in apply_search_criteria(self.db.query(Media), parsed, self.db).all()]
        self.assertNotIn(2, ids)
        self.assertIn(1, ids)
        self.assertIn(3, ids)

    def test_filename_name_alias(self):
        # name: is an alias for filename:
        parsed_fn = parse_search_query("filename:image1.png")
        parsed_n = parse_search_query("name:image1.png")
        ids_fn = sorted(m.id for m in apply_search_criteria(self.db.query(Media), parsed_fn, self.db).all())
        ids_n = sorted(m.id for m in apply_search_criteria(self.db.query(Media), parsed_n, self.db).all())
        self.assertEqual(ids_fn, ids_n)

    def test_dimensions_multi_filter(self):
        # Query: width:<1000,>1500 -> matches m2 (800) and m1 (1920), excludes m3 (1280)
        parsed = parse_search_query("width:<1000,>1500")
        q = apply_search_criteria(self.db.query(Media), parsed, self.db)
        ids = [m.id for m in q.all()]
        self.assertIn(1, ids)
        self.assertIn(2, ids)
        self.assertNotIn(3, ids)

    def test_duration_filter(self):
        # Query: duration:>30
        parsed = parse_search_query("duration:>30")
        q = apply_search_criteria(self.db.query(Media), parsed, self.db)
        ids = [m.id for m in q.all()]
        self.assertEqual(ids, [3])

    def test_custom_order_by_id_list(self):
        parsed = parse_search_query("id:2,3,1 order:custom")
        q = apply_search_criteria(self.db.query(Media), parsed, self.db)
        ids = [m.id for m in q.all()]
        self.assertEqual(ids, [2, 3, 1])

    def test_sort_filesize_asc_and_desc(self):
        # Descending (default for filesize): m5 (60MB), m4 (55MB), m3 (20MB), m2 (5MB), m1 (1MB)
        parsed_desc = parse_search_query("order:filesize_desc")
        q_desc = apply_search_criteria(self.db.query(Media), parsed_desc, self.db)
        ids_desc = [m.id for m in q_desc.all()]
        self.assertEqual(ids_desc, [5, 4, 3, 2, 1])

        # Ascending: m1, m2, m3, m4, m5
        parsed_asc = parse_search_query("order:filesize_asc")
        q_asc = apply_search_criteria(self.db.query(Media), parsed_asc, self.db)
        ids_asc = [m.id for m in q_asc.all()]
        self.assertEqual(ids_asc, [1, 2, 3, 4, 5])

    def test_sort_width_and_mpixels(self):
        # Width desc: m1 (1920), m3 (1280), m2 (800), m5 (600), m4 (500)
        parsed_width = parse_search_query("order:width_desc")
        q_width = apply_search_criteria(self.db.query(Media), parsed_width, self.db)
        ids_width = [m.id for m in q_width.all()]
        self.assertEqual(ids_width, [1, 3, 2, 5, 4])

        # Mpixels asc: m4 (250k), m5 (360k), m2 (480k), m3 (921.6k), m1 (2073.6k)
        parsed_res = parse_search_query("order:mpixels_asc")
        q_res = apply_search_criteria(self.db.query(Media), parsed_res, self.db)
        ids_res = [m.id for m in q_res.all()]
        self.assertEqual(ids_res, [4, 5, 2, 3, 1])

    def test_sort_tagcount_asc_and_desc(self):
        # m2 has 4 tags, m1 has 2 tags, m3 has 1 tag, m5 has 0 tags, m4 has 0 tags
        parsed_tc_desc = parse_search_query("order:tagcount_desc")
        q_tc_desc = apply_search_criteria(self.db.query(Media), parsed_tc_desc, self.db)
        ids_tc_desc = [m.id for m in q_tc_desc.all()]
        self.assertEqual(ids_tc_desc, [2, 1, 3, 5, 4])

        parsed_tc_asc = parse_search_query("order:tagcount_asc")
        q_tc_asc = apply_search_criteria(self.db.query(Media), parsed_tc_asc, self.db)
        ids_tc_asc = [m.id for m in q_tc_asc.all()]
        self.assertEqual(ids_tc_asc, [4, 5, 3, 1, 2])

    def test_filesize_fuzzy_matching(self):
        # m4 has size 55,000,000 bytes (52.45 MB), which matches filesize:52MB (52.0MB-52.99MB)
        # m5 has size 60,000,000 bytes (57.22 MB), does not match
        parsed = parse_search_query("filesize:52MB")
        q = apply_search_criteria(self.db.query(Media), parsed, self.db)
        ids = [m.id for m in q.all()]
        self.assertEqual(ids, [4])

    def test_date_ranges_and_comparisons(self):
        now = datetime.now().date()
        # Upload dates: m5 (20d ago), m4 (10d ago), m1 (5d ago), m2 (2d ago), m3 (today)
        d_15d_ago = (now - timedelta(days=15)).strftime("%Y-%m-%d")
        d_3d_ago = (now - timedelta(days=3)).strftime("%Y-%m-%d")

        # Range query: between 15 days ago and 3 days ago -> matches m4 (10d ago) and m1 (5d ago)
        parsed_range = parse_search_query(f"date:{d_15d_ago}..{d_3d_ago}")
        q_range = apply_search_criteria(self.db.query(Media), parsed_range, self.db)
        ids_range = [m.id for m in q_range.all()]
        self.assertIn(1, ids_range)
        self.assertIn(4, ids_range)
        self.assertNotIn(2, ids_range)
        self.assertNotIn(3, ids_range)
        self.assertNotIn(5, ids_range)

        # Comparison query: date:<{d_3d_ago} -> older than 3 days ago -> m1, m4, m5
        parsed_lt = parse_search_query(f"date:<{d_3d_ago}")
        q_lt = apply_search_criteria(self.db.query(Media), parsed_lt, self.db)
        ids_lt = [m.id for m in q_lt.all()]
        self.assertIn(1, ids_lt)
        self.assertIn(4, ids_lt)
        self.assertIn(5, ids_lt)
        self.assertNotIn(2, ids_lt)
        self.assertNotIn(3, ids_lt)

    def test_custom_date_ranges_and_comparisons(self):
        # Custom dates: m5 (2019-06-15), m3 (2020-01-01), m1 (2021-05-10), m2 (2023-08-20), m4 (2024-12-25)

        # 1. Exact match
        parsed_eq = parse_search_query("custom_date:2023-08-20")
        q_eq = apply_search_criteria(self.db.query(Media), parsed_eq, self.db)
        self.assertEqual([m.id for m in q_eq.all()], [2])

        # 2. Date qualifier does not match custom date
        parsed_date_eq = parse_search_query("date:2023-08-20")
        q_date_eq = apply_search_criteria(self.db.query(Media), parsed_date_eq, self.db)
        self.assertEqual([m.id for m in q_date_eq.all()], [])

        # 3. Greater than or equal
        parsed_ge = parse_search_query("custom_date:>=2023-01-01")
        q_ge = apply_search_criteria(self.db.query(Media), parsed_ge, self.db)
        ids_ge = [m.id for m in q_ge.all()]
        self.assertIn(2, ids_ge)
        self.assertIn(4, ids_ge)
        self.assertNotIn(1, ids_ge)
        self.assertNotIn(3, ids_ge)
        self.assertNotIn(5, ids_ge)

        # 4. Less than
        parsed_lt = parse_search_query("custom_date:<2021-01-01")
        q_lt = apply_search_criteria(self.db.query(Media), parsed_lt, self.db)
        ids_lt = [m.id for m in q_lt.all()]
        self.assertIn(3, ids_lt)
        self.assertIn(5, ids_lt)
        self.assertNotIn(1, ids_lt)
        self.assertNotIn(2, ids_lt)
        self.assertNotIn(4, ids_lt)

        # 5. Range between 2020-01-01 and 2022-01-01
        parsed_range = parse_search_query("custom_date:2020-01-01..2022-01-01")
        q_range = apply_search_criteria(self.db.query(Media), parsed_range, self.db)
        ids_range = [m.id for m in q_range.all()]
        self.assertIn(1, ids_range)
        self.assertIn(3, ids_range)
        self.assertNotIn(2, ids_range)
        self.assertNotIn(4, ids_range)
        self.assertNotIn(5, ids_range)

        # 6. Negated custom date
        parsed_neg = parse_search_query("-custom_date:>=2023-01-01")
        q_neg = apply_search_criteria(self.db.query(Media), parsed_neg, self.db)
        ids_neg = [m.id for m in q_neg.all()]
        self.assertIn(1, ids_neg)
        self.assertIn(3, ids_neg)
        self.assertIn(5, ids_neg)
        self.assertNotIn(2, ids_neg)
        self.assertNotIn(4, ids_neg)

    def test_custom_age_ranges_and_comparisons(self):
        # Upload dates are all <= 20 days old.
        # Custom dates are:
        # m4: 2024-12-25 (~2 years ago)
        # m2: 2023-08-20 (~3 years ago)
        # m1: 2021-05-10 (~5 years ago)
        # m3: 2020-01-01 (~6 years ago)
        # m5: 2019-06-15 (~7 years ago)

        # 1. custom_age:<30d matches nothing, whereas age:<30d matches all
        parsed_custom_lt30d = parse_search_query("custom_age:<30d")
        q_custom_lt30d = apply_search_criteria(self.db.query(Media), parsed_custom_lt30d, self.db)
        self.assertEqual([m.id for m in q_custom_lt30d.all()], [])

        parsed_age_lt30d = parse_search_query("age:<30d")
        q_age_lt30d = apply_search_criteria(self.db.query(Media), parsed_age_lt30d, self.db)
        self.assertEqual(len(q_age_lt30d.all()), 5)

        # 2. custom_age:>1y matches all media
        parsed_custom_gt1y = parse_search_query("custom_age:>1y")
        q_custom_gt1y = apply_search_criteria(self.db.query(Media), parsed_custom_gt1y, self.db)
        self.assertEqual(len(q_custom_gt1y.all()), 5)

        # 3. age:>1y matches no media (since all were uploaded within 20 days)
        parsed_age_gt1y = parse_search_query("age:>1y")
        q_age_gt1y = apply_search_criteria(self.db.query(Media), parsed_age_gt1y, self.db)
        self.assertEqual([m.id for m in q_age_gt1y.all()], [])

        # 4. Negated custom age
        parsed_neg = parse_search_query("-custom_age:>1y")
        q_neg = apply_search_criteria(self.db.query(Media), parsed_neg, self.db)
        self.assertEqual([m.id for m in q_neg.all()], [])

    def test_order_by_custom_date(self):
        # Custom dates: m4 (2024-12-25), m2 (2023-08-20), m1 (2021-05-10), m3 (2020-01-01), m5 (2019-06-15)
        # Upload dates: m3 (1h ago), m2 (2d ago), m1 (5d ago), m4 (10d ago), m5 (20d ago)

        # Descending custom date
        parsed_desc = parse_search_query("order:custom_date_desc")
        q_desc = apply_search_criteria(self.db.query(Media), parsed_desc, self.db)
        self.assertEqual([m.id for m in q_desc.all()], [4, 2, 1, 3, 5])

        # Default order:custom_date is descending
        parsed_def = parse_search_query("order:custom_date")
        q_def = apply_search_criteria(self.db.query(Media), parsed_def, self.db)
        self.assertEqual([m.id for m in q_def.all()], [4, 2, 1, 3, 5])

        # Ascending custom date
        parsed_asc = parse_search_query("order:custom_date_asc")
        q_asc = apply_search_criteria(self.db.query(Media), parsed_asc, self.db)
        self.assertEqual([m.id for m in q_asc.all()], [5, 3, 1, 2, 4])

        # Ensure order:date_desc strictly sorts by uploaded_at, not custom_date
        parsed_date_desc = parse_search_query("order:date_desc")
        q_date_desc = apply_search_criteria(self.db.query(Media), parsed_date_desc, self.db)
        self.assertEqual([m.id for m in q_date_desc.all()], [3, 2, 1, 4, 5])

        parsed_date_asc = parse_search_query("order:date_asc")
        q_date_asc = apply_search_criteria(self.db.query(Media), parsed_date_asc, self.db)
        self.assertEqual([m.id for m in q_date_asc.all()], [5, 4, 1, 2, 3])

    def test_get_media_sort_clauses_custom_date(self):
        clauses_desc = get_media_sort_clauses("custom_date", "desc")
        self.assertEqual(clauses_desc[0].element, Media.custom_date)

        clauses_asc = get_media_sort_clauses("custom_date", "asc")
        self.assertEqual(clauses_asc[0].element, Media.custom_date)

        clauses_date = get_media_sort_clauses("date", "desc")
        self.assertEqual(clauses_date[0].element, Media.uploaded_at)

    def test_parent_and_child_filters(self):
        # m4 has parent_id=1. m1 has children (m4). Others have no parent/children.
        # parent:none -> m1, m2, m3, m5
        parsed_p_none = parse_search_query("parent:none")
        q_p_none = apply_search_criteria(self.db.query(Media), parsed_p_none, self.db)
        ids_p_none = [m.id for m in q_p_none.all()]
        self.assertIn(1, ids_p_none)
        self.assertIn(2, ids_p_none)
        self.assertIn(3, ids_p_none)
        self.assertIn(5, ids_p_none)
        self.assertNotIn(4, ids_p_none)

        # parent:any -> m4
        parsed_p_any = parse_search_query("parent:any")
        q_p_any = apply_search_criteria(self.db.query(Media), parsed_p_any, self.db)
        ids_p_any = [m.id for m in q_p_any.all()]
        self.assertEqual(ids_p_any, [4])

        # parent:1 -> matches post 1 and its child post 4
        parsed_p1 = parse_search_query("parent:1")
        q_p1 = apply_search_criteria(self.db.query(Media), parsed_p1, self.db)
        ids_p1 = [m.id for m in q_p1.all()]
        self.assertIn(1, ids_p1)
        self.assertIn(4, ids_p1)
        self.assertNotIn(2, ids_p1)

        # child:any -> post 1
        parsed_c_any = parse_search_query("child:any")
        q_c_any = apply_search_criteria(self.db.query(Media), parsed_c_any, self.db)
        ids_c_any = [m.id for m in q_c_any.all()]
        self.assertEqual(ids_c_any, [1])

        # child:none -> posts without children (m2, m3, m4, m5)
        parsed_c_none = parse_search_query("child:none")
        q_c_none = apply_search_criteria(self.db.query(Media), parsed_c_none, self.db)
        ids_c_none = [m.id for m in q_c_none.all()]
        self.assertIn(2, ids_c_none)
        self.assertIn(3, ids_c_none)
        self.assertIn(4, ids_c_none)
        self.assertIn(5, ids_c_none)
        self.assertNotIn(1, ids_c_none)

        # child:4 -> post 1
        parsed_c4 = parse_search_query("child:4")
        q_c4 = apply_search_criteria(self.db.query(Media), parsed_c4, self.db)
        ids_c4 = [m.id for m in q_c4.all()]
        self.assertEqual(ids_c4, [1])

    def test_album_and_pool_filters(self):
        # m1 and m2 are in album 1 ("favorites")
        # album:any -> m1, m2
        parsed_a_any = parse_search_query("album:any")
        q_a_any = apply_search_criteria(self.db.query(Media), parsed_a_any, self.db)
        ids_a_any = [m.id for m in q_a_any.all()]
        self.assertIn(1, ids_a_any)
        self.assertIn(2, ids_a_any)
        self.assertNotIn(3, ids_a_any)
        self.assertNotIn(4, ids_a_any)

        # album:none -> m3, m4, m5
        parsed_a_none = parse_search_query("album:none")
        q_a_none = apply_search_criteria(self.db.query(Media), parsed_a_none, self.db)
        ids_a_none = [m.id for m in q_a_none.all()]
        self.assertIn(3, ids_a_none)
        self.assertIn(4, ids_a_none)
        self.assertIn(5, ids_a_none)
        self.assertNotIn(1, ids_a_none)
        self.assertNotIn(2, ids_a_none)

        # album:favorites (name lookup)
        parsed_a_fav = parse_search_query("album:favorites")
        q_a_fav = apply_search_criteria(self.db.query(Media), parsed_a_fav, self.db)
        ids_a_fav = [m.id for m in q_a_fav.all()]
        self.assertIn(1, ids_a_fav)
        self.assertIn(2, ids_a_fav)

        # pool:1 (id lookup)
        parsed_p1 = parse_search_query("pool:1")
        q_p1 = apply_search_criteria(self.db.query(Media), parsed_p1, self.db)
        ids_p1 = [m.id for m in q_p1.all()]
        self.assertIn(1, ids_p1)
        self.assertIn(2, ids_p1)

    def test_filetype_gif_filter(self):
        # m4 has FileTypeEnum.gif, m5 has filename pic.gif (FileTypeEnum.image)
        parsed = parse_search_query("filetype:gif")
        q = apply_search_criteria(self.db.query(Media), parsed, self.db)
        ids = [m.id for m in q.all()]
        self.assertIn(4, ids)
        self.assertIn(5, ids)
        self.assertNotIn(1, ids)
        self.assertNotIn(2, ids)
        self.assertNotIn(3, ids)

    def test_filter_by_tag_with_colon(self):
        # Seed a tag whose name contains a colon
        t_colon = Tag(name="re:zero", category=TagCategoryEnum.copyright, post_count=1)
        self.db.add(t_colon)
        self.db.commit()
        self.m1.tags.append(t_colon)
        self.db.commit()

        parsed = parse_search_query("re:zero")
        q = apply_search_criteria(self.db.query(Media), parsed, self.db)
        ids = [m.id for m in q.all()]
        self.assertIn(1, ids)
        self.assertNotIn(2, ids)
        self.assertNotIn(3, ids)

    def test_filter_by_tag_with_colon_negated(self):
        t_colon = Tag(name="re:zero", category=TagCategoryEnum.copyright, post_count=1)
        self.db.add(t_colon)
        self.db.commit()
        self.m1.tags.append(t_colon)
        self.db.commit()

        parsed = parse_search_query("-re:zero")
        q = apply_search_criteria(self.db.query(Media), parsed, self.db)
        ids = [m.id for m in q.all()]
        self.assertNotIn(1, ids)
        self.assertIn(2, ids)
        self.assertIn(3, ids)

    def test_filter_by_tag_with_parentheses_and_colon(self):
        t_complex = Tag(name="cool(tag:part_2)", category=TagCategoryEnum.character, post_count=1)
        self.db.add(t_complex)
        self.db.commit()
        self.m1.tags.append(t_complex)
        self.db.commit()

        parsed = parse_search_query("cool(tag:part_2)")
        q = apply_search_criteria(self.db.query(Media), parsed, self.db)
        ids = [m.id for m in q.all()]
        self.assertIn(1, ids)
        self.assertNotIn(2, ids)

if __name__ == "__main__":
    unittest.main()
