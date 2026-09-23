import html
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..booru.types import BooruTag
from ...utils.logger import logger
from ...utils.tag_utils import dtext_to_plain
from .base import MetadataParser
from .types import ParsedMetadata

GALLERY_DL_RATING_MAP: Dict[str, str] = {
    "g": "safe",
    "s": "safe",
    "general": "safe",
    "safe": "safe",
    "sensitive": "safe",
    "q": "questionable",
    "questionable": "questionable",
    "e": "explicit",
    "explicit": "explicit",
    "0": "safe",
    "1": "safe",
    "2": "safe",
    "3": "questionable",
    "4": "explicit",
    "5": "explicit",
}

DANBOORU_CATEGORY_FIELDS: Dict[str, str] = {
    "tags_general": "general",
    "tags_artist": "artist",
    "tags_character": "character",
    "tags_copyright": "copyright",
    "tags_meta": "meta",
}

class GalleryDlParser(MetadataParser):
    """Parser for gallery-dl sidecar JSON files (<filename>.<ext>.json or <filename>.json)."""

    name: str = "gallery-dl"

    @classmethod
    def _find_sidecar(cls, media_path: Path, sibling_files: List[Path]) -> Optional[Path]:
        """Find matching gallery-dl sidecar file from sibling files."""
        media_name = media_path.name.lower()
        media_stem = media_path.stem.lower()

        # Exact media_name + ".json" (e.g. image.png.json)
        for s in sibling_files:
            s_name = s.name.lower()
            if s_name == f"{media_name}.json" and cls._is_gallery_dl_json(s):
                return s

        # Stem + ".json" (e.g. image.json)
        for s in sibling_files:
            s_name = s.name.lower()
            if s_name == f"{media_stem}.json" and s_name != f"{media_name}.json":
                if cls._is_gallery_dl_json(s):
                    return s

        return None

    @classmethod
    def _is_gallery_dl_json(cls, json_path: Path) -> bool:
        """Heuristic check for gallery-dl JSON sidecar content."""
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return False
            # Exclude LoliSnatcher signature keys
            lolisnatcher_keys = {
                "booru", "tagsList", "isSnatched", "postURL", "isFavourite",
                "sampleURL", "thumbnailURL", "fileURL", "md5String"
            }
            if any(k in data for k in lolisnatcher_keys):
                return False
            # Exclude LoliSnatcher legacy format unless gallery-dl specific identifiers are present
            if "md5" in data and any(k in data for k in ("post_url", "file_url", "booru_url")):
                if not any(k in data for k in ("category", "extractor", "subcategory", "tags_general", "tag_string", "gallery")):
                    return False

            # Gallery-dl typical keys
            typical_keys = {"category", "subcategory", "tags_general", "tag_string", "post_url", "gallery", "extractor"}
            return bool(typical_keys.intersection(data.keys()))
        except Exception:
            return False

    @classmethod
    def can_handle(cls, media_path: Path, sibling_files: List[Path]) -> bool:
        sidecar = cls._find_sidecar(media_path, sibling_files)
        return sidecar is not None

    def parse(self, media_path: Path, sibling_files: List[Path]) -> ParsedMetadata:
        sidecar = self._find_sidecar(media_path, sibling_files)
        if not sidecar:
            return ParsedMetadata(confidence="sidecar")

        try:
            with open(sidecar, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read gallery-dl sidecar {sidecar}: {e}")
            return ParsedMetadata(confidence="sidecar")

        if not isinstance(data, dict):
            return ParsedMetadata(confidence="sidecar")

        tags = self._parse_tags(data)
        rating = self._parse_rating(data)
        source = self._parse_source(data)
        description = self._parse_description(data)
        pool_names = self._parse_pools(data)
        parent_id = str(data.get("parent_id")) if data.get("parent_id") is not None else None

        return ParsedMetadata(
            tags=tags,
            rating=rating,
            source=source,
            description=description,
            pool_names=pool_names,
            parent_source_id=parent_id,
            confidence="sidecar",
        )

    def _parse_tags(self, data: Dict[str, Any]) -> List[BooruTag]:
        tags: List[BooruTag] = []
        seen: set[str] = set()

        # 1. Categorized Danbooru-style fields
        has_categorized = False
        for field_name, category in DANBOORU_CATEGORY_FIELDS.items():
            val = data.get(field_name)
            if val:
                has_categorized = True
                tag_items = val if isinstance(val, list) else str(val).split()
                for tag_name in tag_items:
                    cleaned = html.unescape(str(tag_name).strip())
                    if cleaned and cleaned.lower() not in seen:
                        seen.add(cleaned.lower())
                        tags.append(BooruTag(name=cleaned, category=category))

        if has_categorized:
            return tags

        # 2. General tags list or space-separated string
        raw_tags = data.get("tags") or data.get("tag_string") or data.get("keywords")
        if raw_tags:
            if isinstance(raw_tags, list):
                for item in raw_tags:
                    if isinstance(item, dict):
                        t_name = html.unescape(str(item.get("name", "")).strip())
                        t_cat = str(item.get("category", "general")).strip() or "general"
                        if t_name and t_name.lower() not in seen:
                            seen.add(t_name.lower())
                            tags.append(BooruTag(name=t_name, category=t_cat))
                    else:
                        cleaned = html.unescape(str(item).strip())
                        if cleaned and cleaned.lower() not in seen:
                            seen.add(cleaned.lower())
                            tags.append(BooruTag(name=cleaned, category="general"))
            elif isinstance(raw_tags, str):
                for tag_name in raw_tags.split():
                    cleaned = html.unescape(tag_name.strip())
                    if cleaned and cleaned.lower() not in seen:
                        seen.add(cleaned.lower())
                        tags.append(BooruTag(name=cleaned, category="general"))

        return tags

    def _parse_rating(self, data: Dict[str, Any]) -> Optional[str]:
        raw_rating = data.get("rating")
        if raw_rating is None:
            return None

        clean_rating = str(raw_rating).strip().lower()
        return GALLERY_DL_RATING_MAP.get(clean_rating, "safe")

    def _parse_source(self, data: Dict[str, Any]) -> Optional[str]:
        # Direct source or post_url
        source = data.get("source") or data.get("post_url") or data.get("url")
        if source and isinstance(source, str) and source.strip():
            return html.unescape(source.strip())

        # Extractor fallback reconstruction
        category = data.get("category")
        subcat = data.get("subcategory")
        post_id = data.get("id")
        if category and post_id:
            if category == "danbooru" or subcat == "danbooru":
                return f"https://danbooru.donmai.us/posts/{post_id}"
            elif category == "gelbooru" or subcat == "gelbooru":
                return f"https://gelbooru.com/index.php?page=post&s=view&id={post_id}"

        return None

    def _parse_description(self, data: Dict[str, Any]) -> Optional[str]:
        # 1. Check artist_commentary dict (Danbooru API structure)
        commentary = data.get("artist_commentary")
        if isinstance(commentary, dict):
            parts = []
            title = commentary.get("translated_title") or commentary.get("original_title")
            trans_desc = commentary.get("translated_description")
            orig_desc = commentary.get("original_description")

            if title and str(title).strip():
                parts.append(str(title).strip())
            if trans_desc and str(trans_desc).strip():
                parts.append(str(trans_desc).strip())
            if orig_desc and str(orig_desc).strip() and orig_desc != trans_desc:
                if trans_desc:
                    parts.append(f"Original:\n{str(orig_desc).strip()}")
                else:
                    parts.append(str(orig_desc).strip())

            if parts:
                return dtext_to_plain("\n\n".join(parts))

        elif isinstance(commentary, str) and commentary.strip():
            return dtext_to_plain(commentary.strip())

        # 2. Check general description / notes / commentary fields
        desc = data.get("description") or data.get("notes") or data.get("commentary") or data.get("caption")
        if not desc or not isinstance(desc, str) or not desc.strip():
            return None

        # Convert DText or decode entities
        return dtext_to_plain(desc.strip())

    def _parse_pools(self, data: Dict[str, Any]) -> List[str]:
        pools: List[str] = []
        raw_pools = data.get("pool") or data.get("pools") or data.get("gallery")
        if not raw_pools:
            return pools

        if isinstance(raw_pools, list):
            for p in raw_pools:
                if isinstance(p, dict):
                    name = p.get("name") or p.get("title")
                    if name and str(name).strip():
                        pools.append(str(name).strip())
                elif isinstance(p, str) and p.strip():
                    pools.append(p.strip())
        elif isinstance(raw_pools, dict):
            name = raw_pools.get("name") or raw_pools.get("title")
            if name and str(name).strip():
                pools.append(str(name).strip())
        elif isinstance(raw_pools, str) and raw_pools.strip():
            pools.append(raw_pools.strip())

        return pools
