import html
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image

from ..booru.types import BooruTag
from ...config import settings
from ...utils.ai_metadata.exif import decode_exif_user_comment
from ...utils.format_registry import format_registry
from ...utils.logger import logger
from .base import MetadataParser
from .gallery_dl import GALLERY_DL_RATING_MAP
from .types import ParsedMetadata

class ExifXmpParser(MetadataParser):
    """Parser for imgbrd-grabber style XMP sidecars and embedded EXIF/XMP/PNG metadata."""

    name: str = "EXIF/XMP"

    @classmethod
    def _find_xmp_sidecar(cls, media_path: Path, sibling_files: List[Path]) -> Optional[Path]:
        media_name = media_path.name.lower()
        media_stem = media_path.stem.lower()

        # Exact media_name + ".xmp" (e.g. image.png.xmp)
        for s in sibling_files:
            s_name = s.name.lower()
            if s_name == f"{media_name}.xmp":
                return s

        # Stem + ".xmp" (e.g. image.xmp)
        for s in sibling_files:
            s_name = s.name.lower()
            if s_name == f"{media_stem}.xmp" and s_name != f"{media_name}.xmp":
                return s

        return None

    @classmethod
    def can_handle(cls, media_path: Path, sibling_files: List[Path]) -> bool:
        # 1. Check for sibling .xmp sidecar
        if cls._find_xmp_sidecar(media_path, sibling_files) is not None:
            return True

        # 2. Check if media file has embedded metadata that parses as structured Grabber metadata
        if format_registry.is_image(media_path):
            try:
                return cls._has_embedded_structured_metadata(media_path)
            except Exception:
                return False

        return False

    @classmethod
    def _get_candidate_keys(cls) -> set[str]:
        field_map = settings.METADATA_PARSERS.get("exif_metadata_field_map", {})
        candidate_keys = {
            "tags", "keywords", "xpkeywords", "rating", "source",
            "description", "comment", "usercomment", "creator", "artist", "author",
            "post_url", "url", "identifier"
        }
        for key_list in field_map.values():
            if isinstance(key_list, list):
                for k in key_list:
                    if isinstance(k, str):
                        candidate_keys.add(k.lower())
        return candidate_keys

    @classmethod
    def _has_embedded_structured_metadata(cls, media_path: Path) -> bool:
        """Cheap probe for embedded structured EXIF/PNG JSON or Grabber tags."""
        candidate_keys = cls._get_candidate_keys()
        try:
            with Image.open(media_path) as img:
                # Check PNG text chunks
                if hasattr(img, "info") and img.info:
                    for key, val in img.info.items():
                        k_low = str(key).lower()
                        if k_low in ("xmp", "xml:com.adobe.xmp") and isinstance(val, (bytes, str)):
                            xmp_str = val.decode("utf-8", errors="replace") if isinstance(val, bytes) else str(val)
                            if "<rdf:RDF" in xmp_str or "<x:xmpmeta" in xmp_str:
                                return True
                        if k_low in candidate_keys:
                            return True
                        if isinstance(val, str):
                            val_stripped = val.strip()
                            if val_stripped.startswith("{"):
                                try:
                                    parsed = json.loads(val_stripped)
                                    if isinstance(parsed, dict) and any(str(pk).lower() in candidate_keys for pk in parsed.keys()):
                                        return True
                                except Exception:
                                    pass
                            elif any(ck in k_low for ck in candidate_keys):
                                return True

                # Check EXIF
                exif = img.getexif()
                if exif:
                    for tag_id, value in exif.items():
                        decoded_str = None
                        if isinstance(value, bytes):
                            decoded_str = decode_exif_user_comment(value)
                        elif isinstance(value, str):
                            decoded_str = value

                        if decoded_str:
                            d_str = decoded_str.strip()
                            if d_str.startswith("{"):
                                try:
                                    parsed = json.loads(d_str)
                                    if isinstance(parsed, dict) and any(str(pk).lower() in candidate_keys for pk in parsed.keys()):
                                        return True
                                except Exception:
                                    pass
                            elif any(ck in d_str.lower() for ck in candidate_keys):
                                return True
        except Exception:
            return False
        return False

    def parse(self, media_path: Path, sibling_files: List[Path]) -> ParsedMetadata:
        # 1. Try XMP sidecar first
        xmp_sidecar = self._find_xmp_sidecar(media_path, sibling_files)
        if xmp_sidecar:
            try:
                with open(xmp_sidecar, "r", encoding="utf-8", errors="replace") as f:
                    xmp_content = f.read()
                parsed_xmp = self._parse_xmp_content(xmp_content)
                if parsed_xmp.tags or parsed_xmp.rating or parsed_xmp.source or parsed_xmp.description:
                    return parsed_xmp
            except Exception as e:
                logger.warning(f"Failed to parse XMP sidecar {xmp_sidecar}: {e}")

        # 2. Try embedded EXIF / PNG chunks
        if format_registry.is_image(media_path):
            try:
                parsed_embedded = self._parse_embedded_metadata(media_path)
                if parsed_embedded.tags or parsed_embedded.rating or parsed_embedded.source or parsed_embedded.description:
                    return parsed_embedded
            except Exception as e:
                logger.debug(f"Error parsing embedded EXIF/XMP in {media_path}: {e}")

        return ParsedMetadata(confidence="exif")

    def _parse_xmp_content(self, xmp_content: str) -> ParsedMetadata:
        """Extract tags, rating, source, description from XMP XML string."""
        tags: List[BooruTag] = []
        rating: Optional[str] = None
        source: Optional[str] = None
        description: Optional[str] = None
        seen_tags: Dict[str, BooruTag] = {}

        # Clean XMP packet wrapper
        cleaned = re.sub(r"<\?xpacket[^>]*\?>", "", xmp_content).strip()
        if not cleaned:
            return ParsedMetadata(confidence="xmp")

        try:
            root = ET.fromstring(cleaned)
        except ET.ParseError:
            try:
                # Retry with common XMP/RDF namespaces declared to handle snippets missing root namespace bindings
                wrapper = (
                    '<xmp_root xmlns:x="adobe:ns:meta/" xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
                    'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:xmp="http://ns.adobe.com/xap/1.0/" '
                    'xmlns:pdf="http://ns.adobe.com/pdf/1.3/" xmlns:photoshop="http://ns.adobe.com/photoshop/1.0/" '
                    f'xmlns:xmpMM="http://ns.adobe.com/xap/1.0/mm/">{cleaned}</xmp_root>'
                )
                root = ET.fromstring(wrapper)
            except Exception:
                # Try to extract <x:xmpmeta> or <rdf:RDF> substring
                start = cleaned.find("<x:xmpmeta")
                if start == -1:
                    start = cleaned.find("<rdf:RDF")
                end = cleaned.rfind("</x:xmpmeta>")
                if end != -1:
                    end += len("</x:xmpmeta>")
                elif cleaned.rfind("</rdf:RDF>") != -1:
                    end = cleaned.rfind("</rdf:RDF>") + len("</rdf:RDF>")

                if start != -1 and end != -1 and start < end:
                    try:
                        root = ET.fromstring(cleaned[start:end])
                    except Exception:
                        return ParsedMetadata(confidence="xmp")
                else:
                    return ParsedMetadata(confidence="xmp")

        def local_name(tag_name: str) -> str:
            return tag_name.split("}", 1)[1] if "}" in tag_name else tag_name

        def extract_li_or_text(elem: ET.Element) -> List[str]:
            items = []
            for child in elem.iter():
                if local_name(child.tag) == "li" and child.text and child.text.strip():
                    items.append(child.text.strip())
            if not items and elem.text and elem.text.strip():
                items.append(elem.text.strip())
            return items

        def parse_tag_string(val: str, category: str = "general") -> None:
            if not val or not isinstance(val, str):
                return
            if ";" in val:
                parts = val.split(";")
            elif "\n" in val:
                parts = val.split("\n")
            elif "," in val:
                parts = val.split(",")
            else:
                parts = val.split()

            for p in parts:
                cleaned = html.unescape(p.strip())
                if cleaned:
                    norm = re.sub(r"\s+", "_", cleaned)
                    c_low = norm.lower()
                    if c_low not in seen_tags:
                        t = BooruTag(name=norm, category=category)
                        seen_tags[c_low] = t
                        tags.append(t)
                    elif category != "general":
                        seen_tags[c_low].category = category

        for elem in root.iter():
            # Check attributes on all elements (e.g. <rdf:Description dc:description="..." dc:subject="...">)
            for attr_name, attr_val in elem.attrib.items():
                if not attr_val or not isinstance(attr_val, str):
                    continue
                a_name = local_name(attr_name).lower()
                if a_name in ("subject", "tags", "keywords", "lastkeyw", "hierarchicalsubject", "cataloguesets"):
                    parse_tag_string(attr_val, category="general")
                elif a_name in ("creator", "author", "artist", "byline", "photographer"):
                    parse_tag_string(attr_val, category="artist")
                elif a_name in ("character", "characters", "personinimage", "persons"):
                    parse_tag_string(attr_val, category="character")
                elif a_name in ("copyright", "series"):
                    parse_tag_string(attr_val, category="copyright")
                elif a_name in ("rating", "urgency") and not rating:
                    rating = GALLERY_DL_RATING_MAP.get(attr_val.strip().lower(), "safe")
                elif a_name in ("source", "url", "identifier", "webstatement") and not source:
                    source = html.unescape(attr_val.strip())
                elif a_name in ("description", "comment", "usercomment", "caption", "imagedescription") and not description:
                    description = html.unescape(attr_val.strip())

            if elem.tag.startswith("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}") and local_name(elem.tag).lower() in ("description", "rdf", "bag", "seq", "alt"):
                continue

            name = local_name(elem.tag).lower()

            # Subject / Keywords / Tags
            if name in ("subject", "tags", "keywords", "lastkeyw", "hierarchicalsubject", "cataloguesets"):
                values = extract_li_or_text(elem)
                for val in values:
                    parse_tag_string(val, category="general")

            # Creator / Author / Artist
            elif name in ("creator", "author", "artist", "byline", "photographer"):
                values = extract_li_or_text(elem)
                for val in values:
                    parse_tag_string(val, category="artist")

            # Character
            elif name in ("character", "characters", "personinimage", "persons"):
                values = extract_li_or_text(elem)
                for val in values:
                    parse_tag_string(val, category="character")

            # Copyright / Series
            elif name in ("copyright", "series"):
                values = extract_li_or_text(elem)
                for val in values:
                    parse_tag_string(val, category="copyright")

            # Rating
            elif name in ("rating", "urgency") and not rating:
                values = extract_li_or_text(elem)
                if values:
                    rating = GALLERY_DL_RATING_MAP.get(values[0].strip().lower(), "safe")

            # Source / URL
            elif name in ("source", "url", "identifier", "webstatement") and not source:
                values = extract_li_or_text(elem)
                if values:
                    source = html.unescape(values[0].strip())

            # Description
            elif name in ("description", "comment", "usercomment", "caption", "imagedescription") and not description:
                values = extract_li_or_text(elem)
                if values:
                    description = html.unescape("\n".join(values).strip())

        return ParsedMetadata(
            tags=tags,
            rating=rating,
            source=source,
            description=description,
            confidence="xmp",
        )

    def _parse_embedded_metadata(self, media_path: Path) -> ParsedMetadata:
        """Parse structured metadata or tags from embedded image chunks / EXIF tags."""
        tags: List[BooruTag] = []
        rating: Optional[str] = None
        source: Optional[str] = None
        description: Optional[str] = None
        seen_tags: set[str] = set()

        field_map = settings.METADATA_PARSERS.get("exif_metadata_field_map", {})

        with Image.open(media_path) as img:
            # 1. Check PNG text chunks
            if hasattr(img, "info") and img.info:
                # Direct check across img.info dict in case chunks are named e.g. "XPKeywords", "Description", "Rating"
                res_info = self._extract_from_dict(img.info, tags, seen_tags, field_map)
                if not rating and res_info.get("rating"):
                    rating = res_info["rating"]
                if not source and res_info.get("source"):
                    source = res_info["source"]
                if not description and res_info.get("description"):
                    description = res_info["description"]

                for key, val in img.info.items():
                    if key.lower() in ("xmp", "xml:com.adobe.xmp") and isinstance(val, (bytes, str)):
                        xmp_str = val.decode("utf-8", errors="replace") if isinstance(val, bytes) else val
                        parsed_xmp = self._parse_xmp_content(xmp_str)
                        if parsed_xmp.tags:
                            for t in parsed_xmp.tags:
                                if t.name.lower() not in seen_tags:
                                    seen_tags.add(t.name.lower())
                                    tags.append(t)
                        if not rating and parsed_xmp.rating:
                            rating = parsed_xmp.rating
                        if not source and parsed_xmp.source:
                            source = parsed_xmp.source
                        if not description and parsed_xmp.description:
                            description = parsed_xmp.description

                    # Check for JSON payloads in text chunks
                    if isinstance(val, str) and val.strip().startswith("{"):
                        try:
                            parsed_json = json.loads(val)
                            if isinstance(parsed_json, dict):
                                res = self._extract_from_dict(parsed_json, tags, seen_tags, field_map)
                                if not rating and res.get("rating"):
                                    rating = res["rating"]
                                if not source and res.get("source"):
                                    source = res["source"]
                                if not description and res.get("description"):
                                    description = res["description"]
                        except Exception:
                            pass

            # 2. Check EXIF tags
            exif = img.getexif()
            if exif:
                for tag_id, value in exif.items():
                    decoded_str = None
                    if isinstance(value, bytes):
                        decoded_str = decode_exif_user_comment(value)
                    elif isinstance(value, str):
                        decoded_str = value

                    if decoded_str and decoded_str.strip().startswith("{"):
                        try:
                            parsed_json = json.loads(decoded_str)
                            if isinstance(parsed_json, dict):
                                res = self._extract_from_dict(parsed_json, tags, seen_tags, field_map)
                                if not rating and res.get("rating"):
                                    rating = res["rating"]
                                if not source and res.get("source"):
                                    source = res["source"]
                                if not description and res.get("description"):
                                    description = res["description"]
                        except Exception:
                            pass

        return ParsedMetadata(
            tags=tags,
            rating=rating,
            source=source,
            description=description,
            confidence="exif",
        )

    def _extract_from_dict(
        self,
        data: Dict[str, Any],
        tags: List[BooruTag],
        seen_tags: set[str],
        field_map: Dict[str, List[str]],
    ) -> Dict[str, Optional[str]]:
        def get_field(primary_keys: List[str], map_category: str) -> Any:
            # 1. Exact match on primary keys
            for k in primary_keys:
                if k in data and data[k] is not None:
                    return data[k]
            # 2. Configured field map exact match
            for k in field_map.get(map_category, []):
                if k in data and data[k] is not None:
                    return data[k]
            # 3. Case-insensitive fallback
            data_lower = {str(k).lower(): v for k, v in data.items() if v is not None}
            for k in primary_keys:
                if k.lower() in data_lower:
                    return data_lower[k.lower()]
            for k in field_map.get(map_category, []):
                if k.lower() in data_lower:
                    return data_lower[k.lower()]
            return None

        # Extract tags
        raw_tags = get_field(["tags", "keywords", "XPKeywords", "dc:subject"], "tags")
        if raw_tags:
            if isinstance(raw_tags, list):
                for item in raw_tags:
                    if isinstance(item, dict):
                        t_name = html.unescape(str(item.get("name", "")).strip())
                        t_cat = str(item.get("category", "general")).strip() or "general"
                        if t_name:
                            norm = re.sub(r"\s+", "_", t_name)
                            if norm.lower() not in seen_tags:
                                seen_tags.add(norm.lower())
                                tags.append(BooruTag(name=norm, category=t_cat))
                    else:
                        cleaned = html.unescape(str(item).strip())
                        if cleaned:
                            norm = re.sub(r"\s+", "_", cleaned)
                            if norm.lower() not in seen_tags:
                                seen_tags.add(norm.lower())
                                tags.append(BooruTag(name=norm, category="general"))
            elif isinstance(raw_tags, str):
                if ";" in raw_tags:
                    parts = raw_tags.split(";")
                elif "\n" in raw_tags:
                    parts = raw_tags.split("\n")
                elif "," in raw_tags:
                    parts = raw_tags.split(",")
                else:
                    parts = raw_tags.split()
                for t in parts:
                    cleaned = html.unescape(t.strip())
                    if cleaned:
                        norm = re.sub(r"\s+", "_", cleaned)
                        if norm.lower() not in seen_tags:
                            seen_tags.add(norm.lower())
                            tags.append(BooruTag(name=norm, category="general"))

        # Extract creator / artist from dict
        raw_creator = get_field(["creator", "artist", "author", "byline", "photographer"], "artist")
        if raw_creator:
            if isinstance(raw_creator, list):
                for item in raw_creator:
                    cleaned = html.unescape(str(item).strip())
                    if cleaned:
                        norm = re.sub(r"\s+", "_", cleaned)
                        if norm.lower() not in seen_tags:
                            seen_tags.add(norm.lower())
                            tags.append(BooruTag(name=norm, category="artist"))
            elif isinstance(raw_creator, str):
                cleaned = html.unescape(raw_creator.strip())
                if cleaned:
                    norm = re.sub(r"\s+", "_", cleaned)
                    if norm.lower() not in seen_tags:
                        seen_tags.add(norm.lower())
                        tags.append(BooruTag(name=norm, category="artist"))

        # Extract rating
        rating = None
        raw_rating = get_field(["rating", "Rating", "xmp:Rating", "urgency"], "rating")
        if raw_rating:
            rating = GALLERY_DL_RATING_MAP.get(str(raw_rating).strip().lower(), "safe")

        # Extract source
        source = None
        raw_source = get_field(["source", "post_url", "dc:description", "ImageDescription", "url", "identifier"], "source")
        if raw_source and isinstance(raw_source, str) and raw_source.strip():
            source = html.unescape(raw_source.strip())

        # Extract description
        description = None
        raw_desc = get_field(["description", "Description", "comment", "UserComment", "caption"], "description")
        if raw_desc and isinstance(raw_desc, str) and raw_desc.strip():
            description = html.unescape(raw_desc.strip())

        return {
            "rating": rating,
            "source": source,
            "description": description,
        }
