import html
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..booru.types import BooruTag
from ...utils.logger import logger
from .base import MetadataParser
from .gallery_dl import GALLERY_DL_RATING_MAP
from .types import ParsedMetadata

class LoliSnatcherParser(MetadataParser):
    """Parser for LoliSnatcher sidecar JSON files (<filename>.json or <stem>.json)."""

    name: str = "LoliSnatcher"

    @classmethod
    def _find_sidecar(cls, media_path: Path, sibling_files: List[Path]) -> Optional[Path]:
        media_name = media_path.name.lower()
        media_stem = media_path.stem.lower()

        # Exact media_name + ".json" (e.g. image.png.json)
        for s in sibling_files:
            s_name = s.name.lower()
            if s_name == f"{media_name}.json" and cls._is_lolisnatcher_json(s):
                return s

        # 2. Stem + ".json" (e.g. image.json)
        for s in sibling_files:
            s_name = s.name.lower()
            if s_name == f"{media_stem}.json" and s_name != f"{media_name}.json":
                if cls._is_lolisnatcher_json(s):
                    return s

        return None

    @classmethod
    def _is_lolisnatcher_json(cls, json_path: Path) -> bool:
        """Check if JSON file matches LoliSnatcher structure."""
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return False
            # LoliSnatcher signature fields
            if "isSnatched" in data or "postURL" in data or "isFavourite" in data:
                return True
            if "sampleURL" in data or "thumbnailURL" in data or "fileURL" in data or "md5String" in data:
                return True
            # Legacy/alternative LoliSnatcher formats
            if "booru" in data or "tagsList" in data:
                return True
            if "md5" in data and ("post_url" in data or "file_url" in data or "booru_url" in data):
                return True
            return False
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
            logger.warning(f"Failed to read LoliSnatcher sidecar {sidecar}: {e}")
            return ParsedMetadata(confidence="sidecar")

        if not isinstance(data, dict):
            return ParsedMetadata(confidence="sidecar")

        tags = self._parse_tags(data)
        rating = self._parse_rating(data)
        source = self._parse_source(data)
        description = self._parse_description(data)
        pool_names = self._parse_pools(data)

        return ParsedMetadata(
            tags=tags,
            rating=rating,
            source=source,
            description=description,
            pool_names=pool_names,
            confidence="sidecar",
        )

    def _parse_tags(self, data: Dict[str, Any]) -> List[BooruTag]:
        tags: List[BooruTag] = []
        seen: set[str] = set()

        raw_tags = data.get("tags") or data.get("tagsList") or data.get("keywords")
        if not raw_tags:
            return tags

        if isinstance(raw_tags, list):
            for item in raw_tags:
                if isinstance(item, dict):
                    t_name = item.get("fullString") or item.get("name") or item.get("tag") or item.get("string")
                    t_cat_raw = item.get("tagType") or item.get("category") or item.get("type") or "general"
                    t_cat_clean = str(t_cat_raw).strip().lower()
                    t_cat = t_cat_clean if t_cat_clean not in ("none", "null", "") else "general"
                    if t_cat not in ("artist", "character", "copyright", "general", "meta"):
                        t_cat = "general"

                    if t_name:
                        name_clean = html.unescape(str(t_name).strip())
                        if name_clean and name_clean.lower() not in seen:
                            seen.add(name_clean.lower())
                            tags.append(BooruTag(name=name_clean, category=t_cat))
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
        if raw_rating is not None and str(raw_rating).strip():
            clean_rating = str(raw_rating).strip().lower()
            return GALLERY_DL_RATING_MAP.get(clean_rating, "safe")
        post_url = str(data.get("postURL") or data.get("post_url") or "").lower()
        if "safebooru" in post_url:
            return "safe"
        return None

    def _parse_source(self, data: Dict[str, Any]) -> Optional[str]:
        source = (
            data.get("postURL")
            or data.get("post_url")
            or data.get("source")
            or data.get("sources")
            or data.get("booru_url")
            or data.get("fileURL")
            or data.get("file_url")
            or data.get("sampleURL")
        )
        if isinstance(source, list) and source:
            source = source[0]
        if source and isinstance(source, str) and source.strip():
            return html.unescape(source.strip())
        return None

    def _parse_description(self, data: Dict[str, Any]) -> Optional[str]:
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
                parts.append(str(orig_desc).strip())
            if parts:
                return html.unescape("\n\n".join(parts))
        elif isinstance(commentary, str) and commentary.strip():
            return html.unescape(commentary.strip())

        desc = data.get("description") or data.get("notes") or data.get("commentary") or data.get("caption")
        if desc and isinstance(desc, str) and desc.strip():
            return html.unescape(desc.strip())
        return None

    def _parse_pools(self, data: Dict[str, Any]) -> List[str]:
        pools: List[str] = []
        raw_pools = data.get("pools") or data.get("pool") or data.get("folder")
        if not raw_pools:
            return pools

        if isinstance(raw_pools, list):
            for p in raw_pools:
                if isinstance(p, str) and p.strip():
                    pools.append(p.strip())
        elif isinstance(raw_pools, str) and raw_pools.strip():
            pools.append(raw_pools.strip())

        return pools
