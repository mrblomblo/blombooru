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
        self.assertIn("Important Note: Check Source Link (https://example.com/art) and https://example.com/direct.", plain)
        self.assertIn("Artist notes: Very nice scratch that secret Custom Label.", plain)
        self.assertIn("Hidden content", plain)
        self.assertNotIn("[b]", plain)
        self.assertNotIn("[section", plain)

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
        self.assertEqual(parsed.description, "Drawing of Character (https://example.com) in summer.")
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
        self.assertIn("Translated Title", parsed.description)
        self.assertIn("Translated description text.", parsed.description)
        self.assertIn("Original description text.", parsed.description)

    def test_gallery_dl_parser_gelbooru_flat(self):
        """Test GalleryDlParser parsing Gelbooru-style flat tags and source reconstruction."""
        sidecar_data = {
            "id": 67890,
            "category": "gelbooru",
            "subcategory": "post",
            "rating": "e",
            "tags": "tag_one tag_two tag_three",
        }

        media_path = self.tmp_path / "illust.png"
        media_path.write_bytes(b"\x89PNG\r\n\x1a\n")
        sidecar_path = self.tmp_path / "illust.json"
        sidecar_path.write_text(json.dumps(sidecar_data))

        parser = GalleryDlParser()
        self.assertTrue(parser.can_handle(media_path, [media_path, sidecar_path]))

        parsed = parser.parse(media_path, [media_path, sidecar_path])
        self.assertEqual(parsed.rating, "explicit")
        self.assertEqual(parsed.source, "https://gelbooru.com/index.php?page=post&s=view&id=67890")
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
