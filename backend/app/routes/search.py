from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import desc
from typing import List, Optional

from ..database import get_db
from ..models import Media
from ..schemas import MediaResponse
from ..config import settings
from ..utils.search_parser import parse_search_query, apply_search_criteria
from ..utils.cache import cache_response
from fastapi import APIRouter, Depends, Query, Request

router = APIRouter(prefix="/api/search", tags=["search"])

@router.get("/")
@cache_response(expire=3600, key_prefix="search")
async def search_media(
    request: Request,
    q: str = Query("", description="Search query"),
    rating: Optional[str] = None,
    page: int = 1,
    limit: int = Query(None),
    db: Session = Depends(get_db)
):
    """Search media with tag-based query"""
    if limit is None:
        limit = settings.get_items_per_page()
    query = db.query(Media).options(selectinload(Media.tags))
    parsed = parse_search_query(q)
    
    if rating and rating != "explicit":
        rating_value = "safe" if rating == "safe" else "safe,questionable"
        
        if 'rating' not in parsed['meta']:
            parsed['meta']['rating'] = []
        parsed['meta']['rating'].append({'value': rating_value, 'negated': False})

    # Apply all criteria
    query = apply_search_criteria(query, parsed, db)
    
    # Pagination
    offset = (page - 1) * limit
    total = query.count()
    media_list = query.offset(offset).limit(limit).all()
    
    items = [MediaResponse.model_validate(m) for m in media_list]
    
    return {
        "items": items,
        "total": total,
        "page": page,
        "pages": max(1, (total + limit - 1) // limit),
        "query": q
    }
