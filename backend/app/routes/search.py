from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, or_
from typing import List, Optional
import re

from ..database import get_db
from ..models import Media, Tag, blombooru_media_tags
from ..schemas import RatingEnum, MediaResponse

router = APIRouter(prefix="/api/search", tags=["search"])

def parse_search_query(query_string: str) -> dict:
    """Parse Danbooru-style search query"""
    include_tags = []
    exclude_tags = []
    wildcards = []
    
    # Split by spaces, handle quoted strings
    tokens = re.findall(r'[^\s"]+|"[^"]*"', query_string)
    
    for token in tokens:
        token = token.strip('"')
        
        if token.startswith('-'):
            # Exclude tag
            tag_name = token[1:]
            if '*' in tag_name or '?' in tag_name:
                wildcards.append(('exclude', tag_name))
            else:
                exclude_tags.append(tag_name)
        else:
            # Include tag
            if '*' in token or '?' in token:
                wildcards.append(('include', token))
            else:
                include_tags.append(token)
    
    return {
        'include': include_tags,
        'exclude': exclude_tags,
        'wildcards': wildcards
    }

def wildcard_to_sql(pattern: str) -> str:
    """Convert wildcard pattern to SQL LIKE pattern"""
    # Replace * with % and ? with _
    pattern = pattern.replace('*', '%').replace('?', '_')
    return pattern

@router.get("/")
async def search_media(
    q: str = Query("", description="Search query"),
    rating: Optional[str] = None,
    page: int = 1,
    limit: int = 30,
    db: Session = Depends(get_db)
):
    """Search media with tag-based query"""
    # Don't filter by is_shared - show all media in your private gallery
    query = db.query(Media)
    
    # Apply rating filter
    if rating and rating != "explicit":
        allowed_ratings = {
            "safe": [RatingEnum.safe],
            "questionable": [RatingEnum.safe, RatingEnum.questionable]
        }
        query = query.filter(Media.rating.in_(allowed_ratings.get(rating, [])))
    
    # Parse search query
    if q:
        parsed = parse_search_query(q)
        
        # Include tags
        for tag_name in parsed['include']:
            tag = db.query(Tag).filter(Tag.name == tag_name.lower()).first()
            if tag:
                query = query.filter(Media.tags.contains(tag))
        
        # Exclude tags
        for tag_name in parsed['exclude']:
            tag = db.query(Tag).filter(Tag.name == tag_name.lower()).first()
            if tag:
                query = query.filter(~Media.tags.contains(tag))
        
        # Wildcards
        for wildcard_type, pattern in parsed['wildcards']:
            sql_pattern = wildcard_to_sql(pattern)
            matching_tags = db.query(Tag).filter(Tag.name.like(sql_pattern)).all()
            
            if wildcard_type == 'include':
                # Media must have at least one matching tag
                if matching_tags:
                    tag_filters = [Media.tags.contains(tag) for tag in matching_tags]
                    query = query.filter(or_(*tag_filters))
            else:
                # Media must not have any matching tags
                for tag in matching_tags:
                    query = query.filter(~Media.tags.contains(tag))
    
    # Order by upload date
    query = query.order_by(desc(Media.uploaded_at))
    
    # Pagination
    offset = (page - 1) * limit
    total = query.count()
    media_list = query.offset(offset).limit(limit).all()
    
    # Convert to response models
    items = [MediaResponse.model_validate(m) for m in media_list]
    
    return {
        "items": items,
        "total": total,
        "page": page,
        "pages": max(1, (total + limit - 1) // limit),
        "query": q
    }
