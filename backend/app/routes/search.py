import html
import random
import re
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import case, desc, func, or_
from sqlalchemy.orm import Session, selectinload

from ..config import settings
from ..database import get_db
from ..enums import is_rating_filter_active, parse_rating_filter
from ..models import Album, Media
from ..schemas import MediaResponse
from ..utils.cache import cache_response
from ..utils.logger import logger
from ..utils.markdown import render_markdown
from ..utils.media_sort import apply_media_sort
from ..translations import translation_helper
from ..utils.search_parser import (apply_custom_filters_or,
                                   apply_search_criteria, canonicalize_query,
                                   parse_search_query)

router = APIRouter(prefix="/api/search", tags=["search"])

_SYNTAX_GUIDE_DIR = settings.BASE_DIR / "docs" / "Search Syntax Guide"
_cached_guide_html: Dict[str, str] = {}
_cached_guide_mtime: Dict[str, float] = {}

def _resolve_syntax_guide_lang(lang: str) -> str:
    clean = (lang or "").strip().lower().replace("_", "-")
    if translation_helper.is_language_supported(clean):
        if (_SYNTAX_GUIDE_DIR / f"syntax_guide-{clean}.md").is_file():
            return clean
    return "en"

def _render_syntax_guide(lang: str) -> Optional[str]:
    selected_lang = _resolve_syntax_guide_lang(lang)
    guide_path = _SYNTAX_GUIDE_DIR / f"syntax_guide-{selected_lang}.md"

    if not guide_path.is_file():
        return None

    try:
        current_mtime = guide_path.stat().st_mtime
        if selected_lang in _cached_guide_html and _cached_guide_mtime.get(selected_lang) == current_mtime:
            return _cached_guide_html[selected_lang]

        content = guide_path.read_text(encoding="utf-8").strip()
    except Exception as e:
        logger.error(f"Failed to read syntax guide ({guide_path}): {e}")
        return None

    if not content:
        return None

    sections = [s.strip() for s in re.split(r'(?m)^(?=##\s+)', content) if s.strip()] or [content]

    try:
        rendered_sections = []
        for s in sections:
            rendered = render_markdown(s, heading_color="info")
            rendered_sections.append(f'<div class="bg p-2.5 border border-info">{rendered}</div>')
        html_out = "\n".join(rendered_sections)
    except Exception as e:
        logger.error(f"Error rendering syntax guide ({guide_path}): {e}")
        html_out = "\n".join(
            f'<div class="bg p-2.5 border border-info"><pre>{html.escape(s)}</pre></div>'
            for s in sections
        )

    _cached_guide_html[selected_lang] = html_out
    _cached_guide_mtime[selected_lang] = current_mtime
    return html_out

class SyntaxGuideResponse(BaseModel):
    html: Optional[str] = None
    lang: str

@router.get("/")
@router.get("")
@cache_response(expire=3600, key_prefix="search")
async def search_media(
    request: Request,
    q: str = Query("", description="Search query"),
    rating: Optional[str] = None,
    custom_filter: Optional[List[str]] = Query(default=None),
    page: int = 1,
    limit: int = Query(None),
    sort: Optional[str] = None,
    order: Optional[str] = None,
    seed: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Search media with tag-based query"""
    if limit is None or not isinstance(limit, int):
        limit = settings.get_items_per_page()
    if not isinstance(q, str):
        q = ""
    query = db.query(Media).options(selectinload(Media.tags), selectinload(Media.media_tag_links))
    parsed = parse_search_query(q)
    
    rating_str = rating if isinstance(rating, str) else None
    valid_ratings = parse_rating_filter(rating_str) if rating_str else None
    sidebar_rating_active = is_rating_filter_active(valid_ratings) if valid_ratings else False
    if sidebar_rating_active and 'rating' not in parsed['meta']:
        parsed['meta']['rating'] = [{'value': rating_str.lower(), 'negated': False}]

    # Apply all criteria
    query = apply_search_criteria(query, parsed, db)
    custom_filter_list = custom_filter if isinstance(custom_filter, (list, tuple, set)) else None
    custom_filter_active = bool(custom_filter_list and any(cf.strip() for cf in custom_filter_list if isinstance(cf, str)))
    if custom_filter_active:
        query = apply_custom_filters_or(query, custom_filter_list, db)

    # Apply UI sort/order unless the search query specifies its own ordering
    if 'order' not in parsed['meta'] and 'sort' not in parsed['meta']:
        sort_by = sort if sort else settings.get_default_sort()
        sort_order = order if order else settings.get_default_order()
        query = query.order_by(None)
        query = apply_media_sort(query, sort_by, sort_order, db, seed)
    
    # Pagination
    offset = (page - 1) * limit
    total = query.count()
    media_list = query.offset(offset).limit(limit).all()
    
    items = [MediaResponse.model_validate(m) for m in media_list]

    sidebar_filter_applied = (sidebar_rating_active and 'rating' not in parse_search_query(q)['meta']) or custom_filter_active
    if total == 0 and sidebar_filter_applied:
        base_parsed = parse_search_query(q)
        unfiltered_query = db.query(func.count(Media.id))
        unfiltered_query = apply_search_criteria(unfiltered_query, base_parsed, db)
        unfiltered_total = unfiltered_query.scalar()
    else:
        unfiltered_total = total
    
    return {
        "items": items,
        "total": total,
        "unfiltered_total": unfiltered_total,
        "page": page,
        "pages": max(1, (total + limit - 1) // limit),
        "query": canonicalize_query(q)
    }

@router.get("/random")
async def get_random_media(
    q: str = Query("", description="Search query"),
    rating: Optional[str] = None,
    custom_filter: Optional[List[str]] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Get a random media ID matching the search criteria"""
    if not isinstance(q, str):
        q = ""
    query = db.query(Media.id)
    parsed = parse_search_query(q)
    
    if rating and 'rating' not in parsed['meta']:
        parsed['meta']['rating'] = [{'value': rating.lower(), 'negated': False}]

    query = apply_search_criteria(query, parsed, db)
    if custom_filter:
        query = apply_custom_filters_or(query, custom_filter, db)

    total = query.count()
    
    if total == 0:
        return {"id": None}
    
    offset = random.randint(0, total - 1)
    media_id = query.offset(offset).limit(1).scalar()
    
    return {"id": media_id}

@router.get("/syntax-guide", response_model=SyntaxGuideResponse)
async def get_syntax_guide(lang: str = Query("en", description="Language code for syntax guide")):
    """Get the search syntax guide rendered as HTML via Wenmode."""
    resolved_lang = _resolve_syntax_guide_lang(lang)
    rendered_html = _render_syntax_guide(resolved_lang)
    return SyntaxGuideResponse(html=rendered_html, lang=resolved_lang)

@router.get("/qualifier-autocomplete")
@cache_response(expire=3600, key_prefix="qualifier_autocomplete")
async def qualifier_autocomplete(
    request: Request,
    qualifier: str = Query(..., description="Qualifier name"),
    q: str = Query("", description="Search term for qualifier value"),
    exclude: Optional[str] = Query(None, description="Comma-separated values or IDs to exclude"),
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """Dynamic autocomplete suggestions for search qualifiers."""
    canonical = (qualifier or "").strip().lower()
    alias_map = {
        'pool': 'album',
        'pool_tree': 'album_tree'
    }
    canonical = alias_map.get(canonical, canonical)
    q_clean = (q or "").strip()

    if canonical in ('album', 'album_tree'):
        query = db.query(Album)

        if exclude:
            exclude_tokens = [x.strip() for x in exclude.split(',') if x.strip()]
            exclude_ids = []
            exclude_names = []
            for tok in exclude_tokens:
                if tok.isdigit():
                    exclude_ids.append(int(tok))
                else:
                    exclude_names.append(tok.replace('_', ' ').lower())
            if exclude_ids:
                query = query.filter(Album.id.notin_(exclude_ids))
            if exclude_names:
                for en in exclude_names:
                    query = query.filter(func.lower(Album.name) != en)

        if q_clean:
            clean_text = q_clean.replace('_', ' ')
            q_pattern = f"%{clean_text}%"
            if q_clean.isdigit():
                query = query.filter(or_(Album.id == int(q_clean), Album.name.ilike(q_pattern)))
                priority = case(
                    (Album.id == int(q_clean), 1),
                    (func.lower(Album.name) == clean_text.lower(), 2),
                    (Album.name.ilike(f"{clean_text}%"), 3),
                    else_=4
                )
            else:
                query = query.filter(Album.name.ilike(q_pattern))
                priority = case(
                    (func.lower(Album.name) == clean_text.lower(), 1),
                    (Album.name.ilike(f"{clean_text}%"), 2),
                    else_=3
                )
            albums = query.order_by(
                priority,
                desc(Album.cached_media_count),
                func.length(Album.name),
                Album.name
            ).limit(limit).all()
        else:
            albums = query.order_by(
                desc(Album.cached_media_count),
                Album.id
            ).limit(min(limit, 5)).all()

        results = []
        seen = set()
        for a in albums:
            name_val = a.name.replace(' ', '_')
            if name_val.lower() in seen:
                continue
            seen.add(name_val.lower())
            count = a.cached_media_count or 0
            detail_str = f"ID {a.id} ({count})"
            results.append({
                "value": name_val,
                "label": a.name,
                "detail": detail_str,
                "id": a.id,
                "count": count
            })
        return results

    if canonical in ('id', 'child', 'parent') and not q_clean:
        sample = db.query(Media.id).order_by(desc(Media.id)).first()
        if sample:
            return [{
                "value": str(sample[0]),
                "label": f"Post #{sample[0]}",
                "detail": "Latest ID"
            }]

    return []
