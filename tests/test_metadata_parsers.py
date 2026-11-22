import asyncio
import io
import json
from pathlib import Path
import zipfile
from PIL import Image, PngImagePlugin
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from backend.app.config import settings
from backend.app.models import Tag, TagAlias, TagImplication, User
from backend.app.routes.media import extract_archive, get_archive_file
from backend.app.routes.uploads import (
    add_untracked_file_to_session,
    create_upload_session,
    upload_files_to_session,
)
from backend.app.services.booru.types import BooruTag
from backend.app.services.metadata_parsers import (
    ExifXmpParser,
    GalleryDlParser,
    LoliSnatcherParser,
    get_parser_for_file,
)
from backend.app.utils.tag_utils import dtext_to_plain, enrich_and_resolve_tags
from tests.test_base import BackupTestBase, make_dummy_jpeg

class TestMetadataParsers(BackupTestBase):
    def setUp(self):
        super().setUp()
        self.admin_user = User(id=1, username="admin", password_hash="hash")

    def test_dtext_to_plain(self):
        """Test conversion of Danbooru DText markup into plain text."""
        raw_dtext = (
            '[b]Important Note[/b]: Check "Source Link":[https://example.com/art] and <https://example.com/direct>.\n'
            'Artist notes: [i]Very nice[/i] [s]scratch that[/s] [spoiler]secret[/spoiler] [[wiki_tag|Custom Label]].\n'
            '[section=Details]Hidden content[/section]'
        )
        plain = dtext_to_plain(raw_dtext)
        self.assertIn("**Important Note**: Check [Source Link](https://example.com/art) and <https://example.com/direct>.", plain)
        self.assertIn("Artist notes: *Very nice* ~~scratch that~~ secret Custom Label.", plain)
        self.assertIn("Hidden content", plain)
        self.assertIn("[#zzzero](https://x.com/hashtag/zzzero)", dtext_to_plain('"#zzzero":[https://x.com/hashtag/zzzero]'))
        self.assertEqual(dtext_to_plain("h1. Heading 1\nh3. Heading 3"), "# Heading 1\n### Heading 3")
        self.assertNotIn("[b]", plain)
        self.assertNotIn("[section", plain)

    def test_danbooru_artist_commentary_title_bolded(self):
        """Test Danbooru artist commentary title is bolded like on the booru site."""
        from unittest.mock import MagicMock
        from backend.app.services.booru.danbooru import DanbooruClient

        client = DanbooruClient("https://safebooru.example.com")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "id": 10150284,
            "post_id": 12440922,
            "original_title": "Closure",
            "original_description": "<https://x.com/ichika087/status/2113827824532635751?s=20>",
            "translated_title": "",
            "translated_description": "",
        }
        client.session.get = MagicMock(return_value=mock_resp)
        commentary = client._fetch_artist_commentary(12440922)
        self.assertEqual(
            commentary,
            "**Closure**\n\n<https://x.com/ichika087/status/2113827824532635751?s=20>",
        )

    def test_enrich_and_resolve_tags_with_aliases_and_implications(self):
        """Test tag enrichment pipeline preserves categories for new tags and resolves DB tags/aliases/implications."""
        # 1. Existing DB tag with category "character"
        db_char_tag = Tag(name="char_tag", category="character", post_count=10)
        # 2. Existing DB tag for implied target
        implied_tag = Tag(name="copyright_tag", category="copyright", post_count=50)
        self.db.add_all([db_char_tag, implied_tag])
        self.db.commit()

        # Alias: "char_alias" -> "char_tag"
        alias = TagAlias(alias_name="char_alias", target_tag_id=db_char_tag.id)
        self.db.add(alias)

        # Implication: "char_tag" -> implies "copyright_tag"
        implication = TagImplication(
            target_tags=[db_char_tag],
            target_tag_patterns=[],
            implied_tags=[implied_tag],
        )
        self.db.add(implication)
        self.db.commit()

        # Input tags:
        # - "char_alias" (alias to char_tag)
        # - "feature_one" (new tag with category hint "general")
        # - "creator_one" (new tag with category hint "artist")
        input_tags = [
            BooruTag(name="char_alias", category="general"),
            {"name": "feature_one", "category": "general"},
            BooruTag(name="creator_one", category="artist"),
        ]

        enriched = enrich_and_resolve_tags(self.db, input_tags, dry_run=True)
        tag_map = {t.name: t for t in enriched}

        # char_alias resolved to char_tag (character, not new)
        self.assertIn("char_tag", tag_map)
        self.assertFalse(tag_map["char_tag"].is_new)
        self.assertEqual(tag_map["char_tag"].category, "character")

        # Implied copyright_tag automatically expanded
        self.assertIn("copyright_tag", tag_map)
        self.assertFalse(tag_map["copyright_tag"].is_new)
        self.assertEqual(tag_map["copyright_tag"].category, "copyright")

        # feature_one is new, category general
        self.assertIn("feature_one", tag_map)
        self.assertTrue(tag_map["feature_one"].is_new)
        self.assertEqual(tag_map["feature_one"].category, "general")

        # creator_one is new, category artist
        self.assertIn("creator_one", tag_map)
        self.assertTrue(tag_map["creator_one"].is_new)
        self.assertEqual(tag_map["creator_one"].category, "artist")

    def test_gallery_dl_parser_danbooru_categorized(self):
        """Test GalleryDlParser parsing Danbooru-style categorized JSON sidecar."""
        sidecar_data = {
            "id": 12345,
            "category": "danbooru",
            "rating": "q",
            "source": "https://example.com/artist/post/123",
            "description": 'Drawing of "Character":[https://example.com] in [b]summer[/b].',
            "tags_artist": ["test_artist"],
            "tags_character": ["test_character"],
            "tags_copyright": ["test_series"],
            "tags_general": ["feature_one", "feature_two"],
            "tags_meta": ["highres"],
            "pool": [{"name": "Test Collection 2026"}],
            "parent_id": 9999,
        }

        media_path = self.tmp_path / "sample.jpg"
        media_path.write_bytes(make_dummy_jpeg())
        sidecar_path = self.tmp_path / "sample.jpg.json"
        sidecar_path.write_text(json.dumps(sidecar_data))

        parser = GalleryDlParser()
        self.assertTrue(parser.can_handle(media_path, [media_path, sidecar_path]))

        parsed = parser.parse(media_path, [media_path, sidecar_path])
        self.assertEqual(parsed.rating, "questionable")
        self.assertEqual(parsed.source, "https://example.com/artist/post/123")
        self.assertEqual(parsed.description, "Drawing of [Character](https://example.com) in **summer**.")
        self.assertEqual(parsed.pool_names, ["Test Collection 2026"])
        self.assertEqual(parsed.parent_source_id, "9999")

        tag_dict = {t.name: t.category for t in parsed.tags}
        self.assertEqual(tag_dict.get("test_artist"), "artist")
        self.assertEqual(tag_dict.get("test_character"), "character")
        self.assertEqual(tag_dict.get("test_series"), "copyright")
        self.assertEqual(tag_dict.get("feature_one"), "general")
        self.assertEqual(tag_dict.get("highres"), "meta")

    def test_gallery_dl_parser_artist_commentary_dict(self):
        """Test GalleryDlParser parsing nested artist_commentary dict from Danbooru-style API."""
        sidecar_data = {
            "id": 55555,
            "category": "danbooru",
            "tags_general": ["scenery"],
            "artist_commentary": {
                "original_title": "Original Title",
                "translated_title": "Translated Title",
                "original_description": "Original description text.",
                "translated_description": "Translated description text.",
            },
        }

        media_path = self.tmp_path / "night_sky.jpg"
        media_path.write_bytes(make_dummy_jpeg())
        sidecar_path = self.tmp_path / "night_sky.jpg.json"
        sidecar_path.write_text(json.dumps(sidecar_data))

        parser = GalleryDlParser()
        self.assertTrue(parser.can_handle(media_path, [media_path, sidecar_path]))

        parsed = parser.parse(media_path, [media_path, sidecar_path])
        self.assertIn("**Translated Title**", parsed.description)
        self.assertEqual(
            parsed.description,
            "**Translated Title**\n\nTranslated description text.\n\n---\n\nOriginal description text.",
        )

    def test_artist_commentary_separator_layout(self):
        """Translated text goes first, original below a `---` separator; empty parts skip the separator."""
        from backend.app.utils.tag_utils import build_artist_commentary
        self.assertEqual(
            build_artist_commentary("Title", "Translated", "Original"),
            "**Title**\n\nTranslated\n\n---\n\nOriginal",
        )
        self.assertEqual(build_artist_commentary("Title", "", "Original"), "**Title**\n\nOriginal")
        self.assertEqual(build_artist_commentary("Title", "  \n", "Original"), "**Title**\n\nOriginal")
        self.assertEqual(build_artist_commentary("Title", "Translated", None), "**Title**\n\nTranslated")
        self.assertEqual(build_artist_commentary("", "Same", "Same"), "Same")
        self.assertIsNone(build_artist_commentary("", " ", None))

    def test_description_markdown_renders_hr_classes(self):
        from backend.app.utils.markdown import render_description_markdown
        html_out = render_description_markdown("a\n\n---\n\nb")
        self.assertIn('<hr class="text-tertiary my-2" />', html_out)

    def test_gallery_dl_non_dtext_category_not_converted(self):
        """Text from non-Danbooru sites (e.g. pixiv) must not be treated as DText."""
        parser = GalleryDlParser()
        desc = parser._parse_description({"category": "pixiv", "caption": "h1. keep [b]this[/b] &amp; that"})
        self.assertEqual(desc, "h1. keep [b]this[/b] & that")

    def test_gallery_dl_parser_gelbooru_flat(self):
        """Test GalleryDlParser parsing Gelbooru-style flat tags and source reconstruction."""
        sidecar_data = {
            "id": 67890,
            "category": "gelbooru",
            "subcategory": "post",
            "rating": "e",
            "tags": "tag_one tag_two tag_three",
            "post_url": "https://booru.example.com/index.php?page=post&s=view&id=67890",
        }

        media_path = self.tmp_path / "illust.png"
        media_path.write_bytes(b"\x89PNG\r\n\x1a\n")
        sidecar_path = self.tmp_path / "illust.json"
        sidecar_path.write_text(json.dumps(sidecar_data))

        parser = GalleryDlParser()
        self.assertTrue(parser.can_handle(media_path, [media_path, sidecar_path]))

        parsed = parser.parse(media_path, [media_path, sidecar_path])
        self.assertEqual(parsed.rating, "explicit")
        self.assertEqual(parsed.source, "https://booru.example.com/index.php?page=post&s=view&id=67890")
        tag_names = [t.name for t in parsed.tags]
        self.assertIn("tag_one", tag_names)
        self.assertIn("tag_two", tag_names)
        self.assertIn("tag_three", tag_names)

    def test_lolisnatcher_parser(self):
        """Test LoliSnatcherParser detection and parsing."""
        sidecar_data = {
            "booru": "danbooru",
            "md5": "d41d8cd98f00b204e9800998ecf8427e",
            "rating": "safe",
            "post_url": "https://example.com/posts/111",
            "tagsList": [
                {"name": "test_artist", "category": "artist"},
                {"name": "landscape", "category": "general"},
            ],
            "pools": ["Test Pool"],
            "notes": "LoliSnatcher test notes",
        }

        media_path = self.tmp_path / "snatched.jpg"
        media_path.write_bytes(make_dummy_jpeg())
        sidecar_path = self.tmp_path / "snatched.json"
        sidecar_path.write_text(json.dumps(sidecar_data))

        parser = LoliSnatcherParser()
        self.assertTrue(parser.can_handle(media_path, [media_path, sidecar_path]))

        parsed = parser.parse(media_path, [media_path, sidecar_path])
        self.assertEqual(parsed.rating, "safe")
        self.assertEqual(parsed.source, "https://example.com/posts/111")
        self.assertEqual(parsed.description, "LoliSnatcher test notes")
        self.assertEqual(parsed.pool_names, ["Test Pool"])

        tag_dict = {t.name: t.category for t in parsed.tags}
        self.assertEqual(tag_dict.get("test_artist"), "artist")
        self.assertEqual(tag_dict.get("landscape"), "general")

    def test_lolisnatcher_parser_camelcase_format(self):
        """Test LoliSnatcherParser on camelCase LoliSnatcher JSON sidecar format."""
        real_lolisnatcher_json = {
            "postURL": "https://safebooru.example.com/posts/12345",
            "fileURL": "https://cdn.example.com/original/ab/25/test_sample_image.jpg",
            "sampleURL": "https://cdn.example.com/sample/ab/25/test_sample_image.jpg",
            "thumbnailURL": "https://cdn.example.com/180x180/ab/25/test_sample_image.jpg",
            "tags": [
                {"fullString": "tag_one", "updatedAt": 1790167883776, "tagType": "none"},
                {"fullString": "tag_two", "updatedAt": 1790167883776, "tagType": "none"},
                {"fullString": "test_artist", "updatedAt": 1790167883776, "tagType": "artist"},
                {"fullString": "test_character", "updatedAt": 1790167883776, "tagType": "character"},
                {"fullString": "test_series", "updatedAt": 1790167883776, "tagType": "copyright"},
            ],
            "fileExt": "jpg",
            "isFavourite": False,
            "isSnatched": True,
            "serverId": None,
            "rating": None,
            "score": None,
            "sources": None,
            "md5String": None,
            "postDate": None,
            "postDateFormat": None,
        }

        media_path = self.tmp_path / "sample_art.jpg"
        media_path.write_bytes(make_dummy_jpeg())
        sidecar_path = self.tmp_path / "sample_art.json"
        sidecar_path.write_text(json.dumps(real_lolisnatcher_json))

        parser = LoliSnatcherParser()
        self.assertTrue(parser.can_handle(media_path, [media_path, sidecar_path]))

        parsed = parser.parse(media_path, [media_path, sidecar_path])
        self.assertEqual(parsed.rating, "safe")
        self.assertEqual(parsed.source, "https://safebooru.example.com/posts/12345")

        tag_dict = {t.name: t.category for t in parsed.tags}
        self.assertEqual(tag_dict.get("tag_one"), "general")
        self.assertEqual(tag_dict.get("tag_two"), "general")
        self.assertEqual(tag_dict.get("test_artist"), "artist")
        self.assertEqual(tag_dict.get("test_character"), "character")
        self.assertEqual(tag_dict.get("test_series"), "copyright")

    def test_exif_xmp_parser_sidecar_and_embedded(self):
        """Test ExifXmpParser for both .xmp sidecar files and embedded image metadata."""
        xmp_xml = """<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
    <rdf:Description xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:xmp="http://ns.adobe.com/xap/1.0/">
      <dc:subject>
        <rdf:Bag>
          <rdf:li>grabber_tag1</rdf:li>
          <rdf:li>grabber_tag2</rdf:li>
        </rdf:Bag>
      </dc:subject>
      <xmp:Rating>3</xmp:Rating>
      <dc:source>https://example.com/image/123</dc:source>
      <dc:description>
        <rdf:Alt>
          <rdf:li xml:lang="x-default">Grabber exported photo</rdf:li>
        </rdf:Alt>
      </dc:description>
    </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>"""

        media_path = self.tmp_path / "grabber_test.jpg"
        media_path.write_bytes(make_dummy_jpeg())
        xmp_path = self.tmp_path / "grabber_test.xmp"
        xmp_path.write_text(xmp_xml)

        parser = ExifXmpParser()
        self.assertTrue(parser.can_handle(media_path, [media_path, xmp_path]))

        parsed = parser.parse(media_path, [media_path, xmp_path])
        tag_names = [t.name for t in parsed.tags]
        self.assertIn("grabber_tag1", tag_names)
        self.assertIn("grabber_tag2", tag_names)
        self.assertEqual(parsed.source, "https://example.com/image/123")
        self.assertEqual(parsed.description, "Grabber exported photo")

        # Test embedded PNG JSON tags and metadata
        png_io = io.BytesIO()
        info = PngImagePlugin.PngInfo()
        info.add_text("tags", json.dumps({
            "tags": ["embedded_png_tag", "flower"],
            "rating": "safe",
            "source": "https://example.com/art/png",
            "description": "A beautiful PNG flower",
        }))
        img = Image.new("RGB", (16, 16), color="green")
        img.save(png_io, format="PNG", pnginfo=info)

        png_media_path = self.tmp_path / "embedded.png"
        png_media_path.write_bytes(png_io.getvalue())

        self.assertTrue(parser.can_handle(png_media_path, [png_media_path]))
        parsed_embedded = parser.parse(png_media_path, [png_media_path])
        emb_tag_names = [t.name for t in parsed_embedded.tags]
        self.assertIn("embedded_png_tag", emb_tag_names)
        self.assertIn("flower", emb_tag_names)
        self.assertEqual(parsed_embedded.rating, "safe")
        self.assertEqual(parsed_embedded.source, "https://example.com/art/png")
        self.assertEqual(parsed_embedded.description, "A beautiful PNG flower")

    def test_exiftool_grabber_xmp_sidecar(self):
        """Test parsing ExifTool / Grabber XMP sidecar with dc:creator and pdf:Keywords."""
        grabber_xmp = """<?xpacket begin='' id='W5M0MpCehiHzreSzNTczkc9d'?>
<x:xmpmeta xmlns:x='adobe:ns:meta/' x:xmptk='Image::ExifTool 13.55'>
<rdf:RDF xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#'>

 <rdf:Description rdf:about=''
  xmlns:dc='http://purl.org/dc/elements/1.1/'>
  <dc:creator>
   <rdf:Seq>
    <rdf:li>test_artist</rdf:li>
   </rdf:Seq>
  </dc:creator>
 </rdf:Description>

 <rdf:Description rdf:about=''
  xmlns:pdf='http://ns.adobe.com/pdf/1.3/'>
  <pdf:Keywords>tag_one;multi word tag;looking at viewer;test_artist;test_character;test character (summer);script.exe</pdf:Keywords>
 </rdf:Description>

 <rdf:Description rdf:about=''
  xmlns:xmpMM='http://ns.adobe.com/xap/1.0/mm/'>
  <xmpMM:PreservedFileName>__test_preserved_file_name_12345__</xmpMM:PreservedFileName>
 </rdf:Description>
</rdf:RDF>
</x:xmpmeta>
<?xpacket end='w'?>"""

        media_path = self.tmp_path / "grabber_sample.png"
        media_path.write_bytes(b"\x89PNG\r\n\x1a\n")
        xmp_path = self.tmp_path / "grabber_sample.xmp"
        xmp_path.write_text(grabber_xmp)

        parser = ExifXmpParser()
        self.assertTrue(parser.can_handle(media_path, [media_path, xmp_path]))

        parsed = parser.parse(media_path, [media_path, xmp_path])
        tag_dict = {t.name: t.category for t in parsed.tags}

        # Multi-word tags properly preserved with underscore normalization
        self.assertIn("multi_word_tag", tag_dict)
        self.assertIn("looking_at_viewer", tag_dict)
        self.assertIn("test_character_(summer)", tag_dict)
        self.assertIn("script.exe", tag_dict)
        self.assertIn("tag_one", tag_dict)

        # dc:creator correctly assigned as artist category
        self.assertIn("test_artist", tag_dict)
        self.assertEqual(tag_dict["test_artist"], "artist")
        self.assertEqual(len(parsed.tags), 7)

    def test_sidecar_extension_prioritization(self):
        """Test that exact with-extension sidecars (e.g. file.png.json, file.png.xmp) are prioritized over stem sidecars (e.g. file.json, file.xmp)."""
        media_path = self.tmp_path / "art_file.png"
        media_path.write_bytes(b"\x89PNG\r\n\x1a\n")

        # 1. Gallery-dl: both art_file.png.json and art_file.json present
        exact_json = self.tmp_path / "art_file.png.json"
        exact_json.write_text(json.dumps({"category": "danbooru", "description": "exact_with_ext"}))
        stem_json = self.tmp_path / "art_file.json"
        stem_json.write_text(json.dumps({"category": "danbooru", "description": "stem_without_ext"}))

        gdl_parser = GalleryDlParser()
        # Pass stem_json first in siblings to ensure ordering doesn't determine selection
        parsed_gdl = gdl_parser.parse(media_path, [stem_json, exact_json, media_path])
        self.assertEqual(parsed_gdl.description, "exact_with_ext")

        # Fallback to stem when exact is removed
        parsed_gdl_fallback = gdl_parser.parse(media_path, [stem_json, media_path])
        self.assertEqual(parsed_gdl_fallback.description, "stem_without_ext")

        # 2. ExifXmp: both art_file.png.xmp and art_file.xmp present
        exact_xmp = self.tmp_path / "art_file.png.xmp"
        exact_xmp.write_text(
            '<x:xmpmeta xmlns:x="adobe:ns:meta/" xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns/" xmlns:dc="http://purl.org/dc/elements/1.1/">'
            '<rdf:RDF><rdf:Description dc:description="exact_xmp_desc"/></rdf:RDF></x:xmpmeta>'
        )
        stem_xmp = self.tmp_path / "art_file.xmp"
        stem_xmp.write_text(
            '<x:xmpmeta xmlns:x="adobe:ns:meta/" xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns/" xmlns:dc="http://purl.org/dc/elements/1.1/">'
            '<rdf:RDF><rdf:Description dc:description="stem_xmp_desc"/></rdf:RDF></x:xmpmeta>'
        )

        xmp_parser = ExifXmpParser()
        parsed_xmp = xmp_parser.parse(media_path, [stem_xmp, exact_xmp, media_path])
        self.assertEqual(parsed_xmp.description, "exact_xmp_desc")

        # Fallback to stem when exact is removed
        parsed_xmp_fallback = xmp_parser.parse(media_path, [stem_xmp, media_path])
        self.assertEqual(parsed_xmp_fallback.description, "stem_xmp_desc")

    def test_ai_tagger_enrich_predicted_tags_preserves_confidence_across_aliases(self):
        """Test that enrich_predicted_tags preserves predicted confidence when a tag is an alias."""
        from backend.app.routes.ai_tagger import enrich_predicted_tags

        # Create tag and alias: "feline" -> "cat"
        cat_tag = Tag(name="cat", category="general", post_count=5)
        self.db.add(cat_tag)
        self.db.commit()

        alias = TagAlias(alias_name="feline", target_tag_id=cat_tag.id)
        self.db.add(alias)
        self.db.commit()

        predictions = [
            {"name": "feline", "confidence": 0.88, "category": "general"},
            {"name": "dog", "confidence": 0.95, "category": "general"},
        ]

        enriched = enrich_predicted_tags(predictions, self.db)
        res_map = {t["name"]: t for t in enriched}

        self.assertIn("cat", res_map)
        self.assertEqual(res_map["cat"]["confidence"], 0.88)
        self.assertIn("dog", res_map)
        self.assertEqual(res_map["dog"]["confidence"], 0.95)

    def test_parser_factory_priority_and_config(self):
        """Test parser factory respects configured priority order and parser enable/disable toggles."""
        media_path = self.tmp_path / "multi_sidecar.jpg"
        media_path.write_bytes(make_dummy_jpeg())

        gdl_sidecar = self.tmp_path / "multi_sidecar.jpg.json"
        gdl_sidecar.write_text(json.dumps({"category": "danbooru", "tags": "gdl"}))

        xmp_sidecar = self.tmp_path / "multi_sidecar.xmp"
        xmp_sidecar.write_text("<x:xmpmeta><rdf:RDF><rdf:Description dc:subject='xmp_tag'/></rdf:RDF></x:xmpmeta>")

        siblings = [media_path, gdl_sidecar, xmp_sidecar]

        # By default, GalleryDlParser is prioritized before ExifXmpParser
        parser = get_parser_for_file(media_path, siblings)
        self.assertIsInstance(parser, GalleryDlParser)

        # Reconfigure priority to prefer ExifXmpParser first
        settings.file_settings["metadata_parsers"] = {
            "enabled": ["GalleryDlParser", "ExifXmpParser"],
            "priority": ["ExifXmpParser", "GalleryDlParser"],
        }

        parser_reordered = get_parser_for_file(media_path, siblings)
        self.assertIsInstance(parser_reordered, ExifXmpParser)

        # Disable ExifXmpParser
        settings.file_settings["metadata_parsers"] = {
            "enabled": ["GalleryDlParser"],
            "priority": ["ExifXmpParser", "GalleryDlParser"],
        }
        parser_disabled = get_parser_for_file(media_path, siblings)
        self.assertIsInstance(parser_disabled, GalleryDlParser)

    def test_upload_session_staging_with_sidecar_file(self):
        """Test uploading a file with a paired sidecar file populates staged item metadata."""
        session_res = asyncio.run(create_upload_session(current_user=self.admin_user))
        session_id = session_res["session_id"]

        jpeg_bytes = make_dummy_jpeg()
        media_upload = UploadFile(filename="art_piece.jpg", file=io.BytesIO(jpeg_bytes))

        sidecar_content = json.dumps({
            "category": "danbooru",
            "rating": "s",
            "source": "https://example.com/posts/555",
            "description": "Staged with sidecar",
            "tags_artist": ["sketch_master"],
            "tags_character": ["character_one"],
            "tags_general": ["night_sky", "stars"],
            "pool": [{"name": "Stargazing Series"}],
        }).encode("utf-8")
        sidecar_upload = UploadFile(filename="art_piece.jpg.json", file=io.BytesIO(sidecar_content))

        staged_item = asyncio.run(upload_files_to_session(
            session_id=session_id,
            file=media_upload,
            sidecar=sidecar_upload,
            current_user=self.admin_user,
            db=self.db,
        ))

        self.assertEqual(staged_item["metadata_source"], "gallery-dl")
        self.assertEqual(staged_item["rating"], "safe")
        self.assertEqual(staged_item["source"], "https://example.com/posts/555")
        self.assertEqual(staged_item["description"], "Staged with sidecar")
        self.assertEqual(staged_item["suggested_album_path"], "Stargazing Series")

        tags_by_name = {t["name"]: t for t in staged_item["tags"]}
        self.assertIn("sketch_master", tags_by_name)
        self.assertEqual(tags_by_name["sketch_master"]["category"], "artist")
        self.assertIn("character_one", tags_by_name)
        self.assertEqual(tags_by_name["character_one"]["category"], "character")
        self.assertIn("night_sky", tags_by_name)

    def test_untracked_scanner_with_sibling_sidecar(self):
        """Test staging untracked files automatically detects sibling sidecar on disk."""
        untracked_media = settings.ORIGINAL_DIR / "untracked_art.jpg"
        untracked_media.write_bytes(make_dummy_jpeg())

        sidecar_file = settings.ORIGINAL_DIR / "untracked_art.json"
        sidecar_file.write_text(json.dumps({
            "category": "danbooru",
            "rating": "e",
            "tags_artist": ["untracked_artist"],
            "tags_general": ["forest"],
        }))

        session_res = asyncio.run(create_upload_session(current_user=self.admin_user))
        session_id = session_res["session_id"]

        from backend.app.schemas import UploadSessionAddUntrackedRequest
        req = UploadSessionAddUntrackedRequest(file_path=str(untracked_media))

        staged = asyncio.run(add_untracked_file_to_session(
            session_id=session_id,
            request=req,
            current_user=self.admin_user,
            db=self.db,
        ))

        self.assertEqual(staged["metadata_source"], "gallery-dl")
        self.assertEqual(staged["rating"], "explicit")
        tag_dict = {t["name"]: t["category"] for t in staged["tags"]}
        self.assertEqual(tag_dict.get("untracked_artist"), "artist")
        self.assertEqual(tag_dict.get("forest"), "general")

    def test_archive_extraction_nested_folders_and_sidecars(self):
        """Test extract_archive pairs sidecars before flattening, renames them, and serves via get_archive_file."""
        import uuid
        upload_id = str(uuid.uuid4())

        from backend.app.routes.media import ARCHIVE_CHUNKS_DIR
        chunk_dir = ARCHIVE_CHUNKS_DIR / upload_id
        chunk_dir.mkdir(parents=True, exist_ok=True)

        # Create a nested zip archive:
        # /FolderA/work1.jpg
        # /FolderA/work1.json
        # /FolderB/work2.jpg
        # /FolderB/work2.xmp
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            zf.writestr("FolderA/work1.jpg", make_dummy_jpeg())
            zf.writestr("FolderA/work1.json", json.dumps({"category": "danbooru", "tags": "work1_tag"}))
            zf.writestr("FolderB/work2.jpg", make_dummy_jpeg())
            zf.writestr("FolderB/work2.xmp", "<x:xmpmeta><rdf:RDF><rdf:Description dc:subject='work2_tag'/></rdf:RDF></x:xmpmeta>")

        zip_bytes = zip_buf.getvalue()

        # Write chunk and meta
        (chunk_dir / "chunk_0").write_bytes(zip_bytes)
        (chunk_dir / "meta.json").write_text(json.dumps({
            "filename": "nested_archive.zip",
            "total_chunks": 1,
            "file_size": len(zip_bytes),
        }))

        # Run archive extraction
        res = asyncio.run(extract_archive(upload_id=upload_id, current_user=self.admin_user))
        self.assertEqual(res["count"], 2)

        files = res["files"]
        f0 = files[0]
        self.assertIn("sidecar_file_id", f0)
        self.assertTrue(f0["sidecar_file_id"].endswith("_sidecar"))

        f1 = files[1]
        self.assertIn("sidecar_file_id", f1)
        self.assertTrue(f1["sidecar_file_id"].endswith("_sidecar"))

        # Test fetching media file and sidecar file via get_archive_file
        media_resp = asyncio.run(get_archive_file(upload_id=upload_id, file_id=str(f0["file_id"])))
        self.assertTrue(Path(media_resp.path).exists())

        sidecar_resp = asyncio.run(get_archive_file(upload_id=upload_id, file_id=f0["sidecar_file_id"]))
        self.assertTrue(Path(sidecar_resp.path).exists())
        self.assertIn("work1_tag", Path(sidecar_resp.path).read_text())

        # Test path traversal prevention on file_id
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(get_archive_file(upload_id=upload_id, file_id="../secret"))
        self.assertEqual(ctx.exception.status_code, 400)

        with self.assertRaises(HTTPException) as ctx2:
            asyncio.run(get_archive_file(upload_id=upload_id, file_id="0/../../evil"))
        self.assertEqual(ctx2.exception.status_code, 400)

        # Cleanup archive
        from backend.app.routes.media import cleanup_archive
        asyncio.run(cleanup_archive(upload_id=upload_id, current_user=self.admin_user))
        self.assertFalse(chunk_dir.exists())

    def test_exif_metadata_field_map_detection(self):
        """Test ExifXmpParser detects and parses embedded PNG metadata using configured field map keys without literal tags/rating."""
        # 1. Embedded PNG with {"XPKeywords": ["default_map_tag"], "xmp:Rating": "safe"} in Comment chunk
        png_io = io.BytesIO()
        info = PngImagePlugin.PngInfo()
        info.add_text("Comment", json.dumps({
            "XPKeywords": ["default_map_tag"],
            "xmp:Rating": "safe",
        }))
        img = Image.new("RGB", (16, 16), color="blue")
        img.save(png_io, format="PNG", pnginfo=info)

        media_path = self.tmp_path / "field_mapped.png"
        media_path.write_bytes(png_io.getvalue())

        parser = ExifXmpParser()
        self.assertTrue(parser.can_handle(media_path, [media_path]))

        selected_parser = get_parser_for_file(media_path, [media_path])
        self.assertIsNotNone(selected_parser)
        self.assertIsInstance(selected_parser, ExifXmpParser)

        parsed = parser.parse(media_path, [media_path])
        self.assertEqual(len(parsed.tags), 1)
        self.assertEqual(parsed.tags[0].name, "default_map_tag")
        self.assertEqual(parsed.tags[0].category, "general")
        self.assertEqual(parsed.rating, "safe")

        # 2. Embedded PNG with dc:subject, Rating, ImageDescription, UserComment
        png_io2 = io.BytesIO()
        info2 = PngImagePlugin.PngInfo()
        info2.add_text("metadata", json.dumps({
            "dc:subject": ["mapped_subject_tag", "blue_sky"],
            "Rating": "explicit",
            "ImageDescription": "https://example.com/posts/777",
            "UserComment": "Mapped comment text",
        }))
        img2 = Image.new("RGB", (16, 16), color="red")
        img2.save(png_io2, format="PNG", pnginfo=info2)

        media_path2 = self.tmp_path / "field_mapped_full.png"
        media_path2.write_bytes(png_io2.getvalue())

        self.assertTrue(parser.can_handle(media_path2, [media_path2]))
        parsed2 = parser.parse(media_path2, [media_path2])
        tag_names2 = [t.name for t in parsed2.tags]
        self.assertIn("mapped_subject_tag", tag_names2)
        self.assertIn("blue_sky", tag_names2)
        self.assertEqual(parsed2.rating, "explicit")
        self.assertEqual(parsed2.source, "https://example.com/posts/777")
        self.assertEqual(parsed2.description, "Mapped comment text")

    def test_gallery_dl_does_not_claim_legacy_lolisnatcher_sidecar(self):
        """Test gallery-dl does not hijack legacy LoliSnatcher JSON sidecars with md5 + post_url."""
        media_path = self.tmp_path / "legacy_lolisnatcher.jpg"
        media_path.write_bytes(make_dummy_jpeg())

        sidecar_path = self.tmp_path / "legacy_lolisnatcher.json"
        sidecar_path.write_text(json.dumps({
            "md5": "0123456789abcdef0123456789abcdef",
            "post_url": "https://example.com/posts/888",
            "tags": "legacy_tag_a legacy_tag_b",
            "rating": "q",
        }))

        sibling_files = [media_path, sidecar_path]
        self.assertFalse(GalleryDlParser.can_handle(media_path, sibling_files))
        self.assertTrue(LoliSnatcherParser.can_handle(media_path, sibling_files))

        selected_parser = get_parser_for_file(media_path, sibling_files)
        self.assertIsNotNone(selected_parser)
        self.assertIsInstance(selected_parser, LoliSnatcherParser)

        parsed = selected_parser.parse(media_path, sibling_files)
        tag_names = [t.name for t in parsed.tags]
        self.assertIn("legacy_tag_a", tag_names)
        self.assertIn("legacy_tag_b", tag_names)
        self.assertEqual(parsed.rating, "questionable")
        self.assertEqual(parsed.source, "https://example.com/posts/888")

    def test_sanitize_metadata_for_json(self):
        """Test sanitization of PIL IFDRational, NaN/Inf, bytes, and nested objects."""
        from PIL.TiffImagePlugin import IFDRational
        from backend.app.utils.media_helpers import sanitize_metadata_for_json
        from fastapi.encoders import jsonable_encoder

        raw = {
            "dpi": (IFDRational(300, 1), IFDRational(300, 1)),
            "ratio": IFDRational(16, 9),
            "zero_denom": IFDRational(10, 0),
            "nan_val": float("nan"),
            "inf_val": float("inf"),
            "raw_bytes": b"clean_string\x00",
            "nested": {
                "sub_ratio": IFDRational(4, 3),
                "list": [IFDRational(72, 1), "hello"]
            }
        }

        sanitized = sanitize_metadata_for_json(raw)
        encoded = jsonable_encoder(sanitized)

        self.assertEqual(encoded["dpi"], [300.0, 300.0])
        self.assertAlmostEqual(encoded["ratio"], 16 / 9)
        self.assertEqual(encoded["zero_denom"], 0.0)
        self.assertIsNone(encoded["nan_val"])
        self.assertIsNone(encoded["inf_val"])
        self.assertEqual(encoded["raw_bytes"], "clean_string")
        self.assertAlmostEqual(encoded["nested"]["sub_ratio"], 4 / 3)
        self.assertEqual(encoded["nested"]["list"], [72.0, "hello"])

    def test_extract_image_metadata_with_ifdrational_dpi(self):
        """Test extract_image_metadata sanitizes IFDRational dpi into a JSON-serializable structure."""
        from PIL.TiffImagePlugin import IFDRational
        from backend.app.utils.media_helpers import extract_image_metadata
        from fastapi.encoders import jsonable_encoder
        from unittest.mock import patch

        jpeg_path = Path(self.temp_dir) / "test_dpi.jpg"
        jpeg_path.write_bytes(make_dummy_jpeg())

        original_open = Image.open

        class MockImgContext:
            def __init__(self, real_img):
                self.real_img = real_img
                self.real_img.info["dpi"] = (IFDRational(300, 1), IFDRational(300, 1))

            def __enter__(self):
                return self.real_img

            def __exit__(self, exc_type, exc_val, exc_tb):
                return self.real_img.__exit__(exc_type, exc_val, exc_tb)

        def mock_open(fp, *args, **kwargs):
            real = original_open(fp, *args, **kwargs)
            return MockImgContext(real)

        with patch("backend.app.utils.media_helpers.metadata.Image.open", side_effect=mock_open):
            meta = extract_image_metadata(jpeg_path)
            encoded = jsonable_encoder(meta)
            self.assertEqual(encoded["dpi"], [300.0, 300.0])

    def test_date_colon_normalization(self):
        """Test EXIF date colon format YYYY:MM:DD normalizes to YYYY-MM-DD."""
        from datetime import datetime, timezone
        from backend.app.utils.date_extractor import normalize_date_string, parse_candidate_datetime

        norm = normalize_date_string("2024:05:18 10:14:22")
        self.assertEqual(norm, "2024-05-18 10:14:22")

        dt = parse_candidate_datetime("2024:05:18 10:14:22")
        self.assertIsNotNone(dt)
        self.assertEqual(dt, datetime(2024, 5, 18, 10, 14, 22, tzinfo=timezone.utc))

    def test_zero_and_boundary_dates_rejected(self):
        """Test zero-dates, pre-1970 dates, and future dates are rejected."""
        from datetime import datetime, timedelta, timezone
        from backend.app.utils.date_extractor import is_zero_date_string, parse_candidate_datetime

        self.assertTrue(is_zero_date_string("0000:00:00 00:00:00"))
        self.assertTrue(is_zero_date_string("0000-00-00"))
        self.assertIsNone(parse_candidate_datetime("0000:00:00 00:00:00"))
        self.assertIsNone(parse_candidate_datetime("1970-01-01 00:00:00"))
        self.assertIsNone(parse_candidate_datetime("1904-01-01"))
        self.assertIsNone(parse_candidate_datetime("1969-12-31 23:59:59"))

        # Future date rejected
        future_str = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        self.assertIsNone(parse_candidate_datetime(future_str))

        # Valid timestamp allowed
        valid_dt = parse_candidate_datetime("1970-01-01 00:00:01")
        self.assertIsNotNone(valid_dt)

    def test_exif_timezone_offset_handling(self):
        """Test OffsetTimeOriginal and OffsetTime timezone offset parsing."""
        from datetime import datetime, timezone
        from backend.app.utils.date_extractor import parse_exif_tag_date

        # Offset +02:00 -> 10:14:22 local is 08:14:22 UTC
        dt_plus = parse_exif_tag_date("2024:05:18 10:14:22", "+02:00")
        self.assertIsNotNone(dt_plus)
        self.assertEqual(dt_plus, datetime(2024, 5, 18, 8, 14, 22, tzinfo=timezone.utc))

        # Offset -05:00 -> 10:14:22 local is 15:14:22 UTC
        dt_minus = parse_exif_tag_date("2024:05:18 10:14:22", "-05:00")
        self.assertIsNotNone(dt_minus)
        self.assertEqual(dt_minus, datetime(2024, 5, 18, 15, 14, 22, tzinfo=timezone.utc))

        # No offset assumes UTC
        dt_utc = parse_exif_tag_date("2024:05:18 10:14:22", None)
        self.assertIsNotNone(dt_utc)
        self.assertEqual(dt_utc, datetime(2024, 5, 18, 10, 14, 22, tzinfo=timezone.utc))

    def test_earliest_embedded_date_selection(self):
        """Test selecting the earliest valid timestamp between created and modified candidates."""
        from datetime import datetime, timezone
        from PIL import Image
        from backend.app.utils.date_extractor import extract_image_embedded_dates

        img_path = Path(self.temp_dir) / "test_exif_compare.jpg"
        img = Image.new("RGB", (32, 32), color="blue")
        exif = img.getexif()
        # DateTime (tag 306): 2024:05:19 12:00:00 (modified)
        exif[306] = "2024:05:19 12:00:00"
        # DateTimeOriginal (tag 36867 in Exif IFD): 2024:05:18 10:00:00 (created)
        exif_ifd = exif.get_ifd(34665)
        exif_ifd[36867] = "2024:05:18 10:00:00"
        img.save(img_path, "JPEG", exif=exif)

        result_dt = extract_image_embedded_dates(img_path)
        self.assertIsNotNone(result_dt)
        self.assertEqual(result_dt, datetime(2024, 5, 18, 10, 0, 0, tzinfo=timezone.utc))

    def test_gallery_dl_and_lolisnatcher_date_extraction(self):
        """Test gallery-dl and LoliSnatcher parsers extract dates into ParsedMetadata."""
        from backend.app.services.metadata_parsers import GalleryDlParser, LoliSnatcherParser

        media_file = Path(self.temp_dir) / "art_sample.png"
        media_file.write_bytes(make_dummy_jpeg())

        # 1. Gallery-dl sidecar
        gdl_sidecar = Path(self.temp_dir) / "art_sample.png.json"
        gdl_sidecar.write_text(json.dumps({
            "category": "danbooru",
            "tag_string": "1girl cat_ears",
            "date": "2024-05-18 10:14:22"
        }), encoding="utf-8")

        gdl_parser = GalleryDlParser()
        self.assertTrue(gdl_parser.can_handle(media_file, [gdl_sidecar]))
        gdl_meta = gdl_parser.parse(media_file, [gdl_sidecar])
        self.assertEqual(gdl_meta.date, "2024-05-18T10:14:22+00:00")

        # 2. LoliSnatcher sidecar with real postDate (Gelbooru format)
        ls_sidecar = Path(self.temp_dir) / "art_sample.json"
        ls_sidecar.write_text(json.dumps({
            "isSnatched": True,
            "tagsList": ["solo", "blue_eyes"],
            "postDate": "Sun May 18 10:14:22  2024",
            "postDateFormat": "EEE MMM dd HH:mm:ss  yyyy"
        }), encoding="utf-8")

        ls_parser = LoliSnatcherParser()
        self.assertTrue(ls_parser.can_handle(media_file, [ls_sidecar]))
        ls_meta = ls_parser.parse(media_file, [ls_sidecar])
        self.assertEqual(ls_meta.date, "2024-05-18T10:14:22+00:00")

        # 3. LoliSnatcher sidecar with ISO postDate
        ls_sidecar_iso = Path(self.temp_dir) / "art_iso.json"
        ls_sidecar_iso.write_text(json.dumps({
            "isSnatched": True,
            "tagsList": ["solo"],
            "postDate": "2024-05-18T10:14:22.000Z",
            "postDateFormat": "iso"
        }), encoding="utf-8")
        iso_file = Path(self.temp_dir) / "art_iso.png"
        iso_file.write_bytes(make_dummy_jpeg())
        ls_iso_meta = ls_parser.parse(iso_file, [ls_sidecar_iso])
        self.assertEqual(ls_iso_meta.date, "2024-05-18T10:14:22+00:00")

    def test_explicit_dates_lenient_range(self):
        """Test explicit dates accept vintage (1890, 1965) and future (2090) dates without auto-detection bounds."""
        from backend.app.utils.date_extractor import resolve_custom_date

        # Vintage 1890
        dt, origin = resolve_custom_date(explicit_date="1890-05-01")
        self.assertEqual(origin, "explicit")
        self.assertEqual(dt.year, 1890)
        self.assertEqual(dt.month, 5)
        self.assertEqual(dt.day, 1)

        # Mid-20th century 1965
        dt, origin = resolve_custom_date(explicit_date="1965-03-04")
        self.assertEqual(origin, "explicit")
        self.assertEqual(dt.year, 1965)

        # Future 2090
        dt, origin = resolve_custom_date(explicit_date="2090-01-01")
        self.assertEqual(origin, "explicit")
        self.assertEqual(dt.year, 2090)

    def test_malformed_timezone_offset_does_not_discard_exif_date(self):
        """Test malformed/out-of-bounds offset caps and preserves EXIF date with UTC fallback."""
        from datetime import datetime, timezone
        from backend.app.utils.date_extractor import parse_exif_tag_date, parse_timezone_offset

        # Out of bounds offset (> 14h) returns None without raising
        self.assertIsNone(parse_timezone_offset("+99:00"))
        self.assertIsNone(parse_timezone_offset("-25:00"))

        # Valid offset within 14h returns timezone
        self.assertIsNotNone(parse_timezone_offset("+14:00"))

        # EXIF date with malformed offset retains date with UTC fallback
        dt = parse_exif_tag_date("2024:05:18 10:14:22", "+99:00")
        self.assertIsNotNone(dt)
        self.assertEqual(dt, datetime(2024, 5, 18, 10, 14, 22, tzinfo=timezone.utc))

    def test_unregistered_extension_embedded_date_extraction_does_not_crash(self):
        """Test extract_embedded_date on unregistered file extension returns None without AttributeError."""
        from backend.app.utils.date_extractor import extract_embedded_date

        strange_file = Path(self.temp_dir) / "data_file.xyz_unknown"
        strange_file.write_bytes(b"some binary data not an image or video")
        result = extract_embedded_date(strange_file)
        self.assertIsNone(result)

    def test_resolve_custom_date_precedence(self):
        """Test resolution precedence: explicit > booru > sidecar > exif > client > default."""
        from datetime import datetime, timezone
        from fastapi import HTTPException
        from backend.app.utils.date_extractor import resolve_custom_date

        explicit_dt = "2024-01-01T00:00:00Z"
        booru_dt = "2023-01-01T00:00:00Z"
        sidecar_dt = "2022-01-01T00:00:00Z"
        client_dt = "2021-01-01T00:00:00Z"

        # 1. Explicit always wins
        dt, origin = resolve_custom_date(
            explicit_date=explicit_dt,
            booru_date=booru_dt,
            sidecar_date=sidecar_dt,
            client_date=client_dt,
        )
        self.assertEqual(origin, "explicit")
        self.assertEqual(dt.year, 2024)

        # 2. Malformed explicit raises 422
        with self.assertRaises(HTTPException) as ctx:
            resolve_custom_date(explicit_date="not-a-real-date")
        self.assertEqual(ctx.exception.status_code, 422)

        # 3. Booru wins when explicit is None
        dt, origin = resolve_custom_date(
            explicit_date=None,
            booru_date=booru_dt,
            sidecar_date=sidecar_dt,
            client_date=client_dt,
        )
        self.assertEqual(origin, "booru")
        self.assertEqual(dt.year, 2023)

        # 4. Sidecar wins when booru is None
        dt, origin = resolve_custom_date(
            explicit_date=None,
            booru_date=None,
            sidecar_date=sidecar_dt,
            client_date=client_dt,
        )
        self.assertEqual(origin, "sidecar")
        self.assertEqual(dt.year, 2022)

        # 5. Client wins when embedded is absent
        dt, origin = resolve_custom_date(
            explicit_date=None,
            booru_date=None,
            sidecar_date=None,
            file_path=None,
            client_date=client_dt,
        )
        self.assertEqual(origin, "client")
        self.assertEqual(dt.year, 2021)

        # 6. Default fallback
        dt, origin = resolve_custom_date()
        self.assertEqual(origin, "default")
        self.assertIsNotNone(dt)

    def test_explicit_dates_reject_incomplete_and_zero(self):
        """Test incomplete dates ('2024', '12', 'May', '10:30', '2024-05') and epoch zero (0, '0') are rejected."""
        from fastapi import HTTPException
        from backend.app.utils.date_extractor import parse_explicit_custom_date, resolve_custom_date

        invalid_candidates = ["2024", "12", "May", "10:30", "2024-05", 0, "0", -1, 0.0]
        for val in invalid_candidates:
            with self.subTest(candidate=val):
                self.assertIsNone(parse_explicit_custom_date(val))
                with self.assertRaises(HTTPException) as ctx:
                    resolve_custom_date(explicit_date=val)
                self.assertEqual(ctx.exception.status_code, 422)

    def test_lolisnatcher_bounds_rejects_epoch_and_future(self):
        """Test LoliSnatcherParser rejects epoch zero (1970-01-01T00:00:00), pre-1970, and future dates."""
        from backend.app.services.metadata_parsers.lolisnatcher import LoliSnatcherParser

        parser = LoliSnatcherParser()
        dummy_media = Path(self.temp_dir) / "art_epoch.jpg"
        dummy_media.write_bytes(make_dummy_jpeg())

        # postDate: "1970-01-01T00:00:00" -> None
        sidecar_epoch = Path(self.temp_dir) / "art_epoch.json"
        sidecar_epoch.write_text(json.dumps({
            "isSnatched": True,
            "postDate": "1970-01-01T00:00:00"
        }), encoding="utf-8")
        parsed = parser.parse(dummy_media, [sidecar_epoch])
        self.assertIsNone(parsed.date)

        # postDate: "1969-12-31" -> None
        sidecar_pre1970 = Path(self.temp_dir) / "art_pre1970.json"
        sidecar_pre1970.write_text(json.dumps({
            "isSnatched": True,
            "postDate": "1969-12-31"
        }), encoding="utf-8")
        parsed = parser.parse(dummy_media, [sidecar_pre1970])
        self.assertIsNone(parsed.date)

        # postDate: "2099-01-01T00:00:00" -> None
        sidecar_future = Path(self.temp_dir) / "art_future.json"
        sidecar_future.write_text(json.dumps({
            "isSnatched": True,
            "postDate": "2099-01-01T00:00:00"
        }), encoding="utf-8")
        parsed = parser.parse(dummy_media, [sidecar_future])
        self.assertIsNone(parsed.date)

    def test_exif_xmp_can_handle_no_false_positives_for_dates(self):
        """Test can_handle does not trigger false positives on date strings in ImageMagick chunks or EXIF Software."""
        # 1. ImageMagick PNG with date:create / date:modify
        img = Image.new("RGB", (10, 10), color="red")
        png_info = PngImagePlugin.PngInfo()
        png_info.add_text("date:create", "2024-05-18T10:14:22+00:00")
        png_info.add_text("date:modify", "2024-05-18T10:14:22+00:00")
        im_png = Path(self.temp_dir) / "imagemagick.png"
        img.save(im_png, pnginfo=png_info)

        parser = ExifXmpParser()
        self.assertFalse(parser.can_handle(im_png, [im_png]))

        # 2. JPEG with EXIF Software "Photo Updater 1.0"
        updater_jpg = Path(self.temp_dir) / "updater.jpg"
        exif = Image.Exif()
        exif[0x0131] = "Photo Updater 1.0"
        img.save(updater_jpg, "JPEG", exif=exif)
        self.assertFalse(parser.can_handle(updater_jpg, [updater_jpg]))

        # 3. PNG with date-only JSON payload in non-standard chunk triggers can_handle
        gdl_png = Path(self.temp_dir) / "gdl_date_only.png"
        png_info2 = PngImagePlugin.PngInfo()
        png_info2.add_text("gallery-dl", json.dumps({"date": "2024-05-18 10:14:22"}))
        img.save(gdl_png, pnginfo=png_info2)
        self.assertTrue(parser.can_handle(gdl_png, [gdl_png]))
        meta = parser.parse(gdl_png, [gdl_png])
        self.assertEqual(meta.date, "2024-05-18T10:14:22+00:00")

    def test_xmp_sidecar_modify_date_does_not_override_exif_date(self):
        """Test Lightroom-style sidecar with only ModifyDate/MetadataDate does not override EXIF date."""
        from backend.app.utils.date_extractor import resolve_custom_date

        img = Image.new("RGB", (10, 10), color="blue")
        photo_jpg = Path(self.temp_dir) / "photo.jpg"
        photo_exif = Image.Exif()
        exif_ifd = photo_exif.get_ifd(0x8769)
        exif_ifd[0x9003] = "2015:06:07 12:00:00"
        img.save(photo_jpg, "JPEG", exif=photo_exif)

        # Sidecar with only MetadataDate and ModifyDate
        photo_xmp = Path(self.temp_dir) / "photo.xmp"
        photo_xmp.write_text(
            '<x:xmpmeta xmlns:x="adobe:ns:meta/" xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns/" xmlns:xmp="http://ns.adobe.com/xap/1.0/">'
            '<rdf:RDF>'
            '<rdf:Description rdf:about="" xmp:MetadataDate="2024-02-02T15:30:00" xmp:ModifyDate="2024-02-02T15:30:00"/>'
            '</rdf:RDF>'
            '</x:xmpmeta>'
        )

        parser = ExifXmpParser()
        meta = parser.parse(photo_jpg, [photo_xmp])
        self.assertIsNone(meta.date)

        resolved_dt, origin = resolve_custom_date(file_path=photo_jpg, sidecar_date=meta.date)
        self.assertEqual(origin, "exif")
        self.assertEqual(resolved_dt.year, 2015)
        self.assertEqual(resolved_dt.month, 6)
        self.assertEqual(resolved_dt.day, 7)

        # Sidecar with CreateDate correctly resolves with sidecar origin
        create_xmp = Path(self.temp_dir) / "photo.xmp"
        create_xmp.write_text(
            '<x:xmpmeta xmlns:x="adobe:ns:meta/" xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns/" xmlns:xmp="http://ns.adobe.com/xap/1.0/">'
            '<rdf:RDF>'
            '<rdf:Description rdf:about="" xmp:CreateDate="2020-01-01T10:00:00" xmp:MetadataDate="2024-02-02T15:30:00"/>'
            '</rdf:RDF>'
            '</x:xmpmeta>'
        )
        meta2 = parser.parse(photo_jpg, [create_xmp])
        self.assertEqual(meta2.date, "2020-01-01T10:00:00+00:00")
        resolved_dt2, origin2 = resolve_custom_date(file_path=photo_jpg, sidecar_date=meta2.date)
        self.assertEqual(origin2, "sidecar")
        self.assertEqual(resolved_dt2.year, 2020)

    def test_metadata_parsers_date_keys_work_without_config_entry(self):
        """Test ExifXmpParser date keys work when saved config lacks 'date' category, and custom keys are honored."""
        saved_parsers = {
            "enabled": ["GalleryDlParser", "ExifXmpParser"],
            "priority": ["ExifXmpParser"],
            "exif_metadata_field_map": {
                "tags": ["CustomTagKey"],
                "rating": ["CustomRating"],
                "source": ["CustomSource"],
                "description": ["CustomDesc"],
            }
        }
        settings.file_settings["metadata_parsers"] = saved_parsers
        parser = ExifXmpParser()
        date_keys = parser._get_date_keys()
        self.assertIn("date", date_keys)
        self.assertIn("created_at", date_keys)
        self.assertIn("postdate", date_keys)

        # Custom date key added by user in settings
        saved_parsers["exif_metadata_field_map"]["date"] = ["MyCustomTimestamp"]
        date_keys_custom = parser._get_date_keys()
        self.assertIn("mycustomtimestamp", date_keys_custom)
        self.assertIn("date", date_keys_custom)

    def test_integer_date_parsing_yyyymmdd(self):
        """Test integer dates like 20200101 parse as YYYYMMDD calendar date instead of epoch seconds."""
        from datetime import datetime, timezone
        from backend.app.utils.date_extractor import parse_candidate_datetime, parse_explicit_custom_date

        # 8-digit integer YYYYMMDD
        dt_cand = parse_candidate_datetime(20200101)
        self.assertIsNotNone(dt_cand)
        self.assertEqual(dt_cand, datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc))

        # 14-digit integer YYYYMMDDhhmmss
        dt_cand14 = parse_candidate_datetime(20200101123000)
        self.assertIsNotNone(dt_cand14)
        self.assertEqual(dt_cand14, datetime(2020, 1, 1, 12, 30, 0, tzinfo=timezone.utc))

        # Explicit custom date with 8-digit integer
        dt_exp = parse_explicit_custom_date(20200101)
        self.assertIsNotNone(dt_exp)
        self.assertEqual(dt_exp, datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc))

        # 10-digit Unix epoch integer still works as epoch seconds
        dt_epoch = parse_candidate_datetime(1577836800)
        self.assertIsNotNone(dt_epoch)
        self.assertEqual(dt_epoch, datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc))

    def test_compact_digit_string_dates_require_exact_width(self):
        """Compact digit strings parse only as exactly YYYYMMDD / YYYYMMDDhhmmss; other widths are rejected."""
        from datetime import datetime, timezone
        from backend.app.utils.date_extractor import parse_candidate_datetime

        # Exact-width strings parse
        self.assertEqual(parse_candidate_datetime("20200101"), datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(parse_candidate_datetime("20200101123000"), datetime(2020, 1, 1, 12, 30, 0, tzinfo=timezone.utc))

        # Wrong-width digit strings must not be leniently parsed by strptime
        for bad in ("202011", "2020101", "202001011230", "19845455424", "2020010112300", "199028"):
            with self.subTest(value=bad):
                self.assertIsNone(parse_candidate_datetime(bad))

        # Exact width but not a real date/time
        for bad in ("20201399", "20200230", "20200101246000"):
            with self.subTest(value=bad):
                self.assertIsNone(parse_candidate_datetime(bad))

        # 10/13-digit strings are still epoch seconds/milliseconds
        self.assertEqual(parse_candidate_datetime("1577836800"), datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(parse_candidate_datetime("1577836800000"), datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc))
