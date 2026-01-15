from fastapi import APIRouter, Depends, Query, Request, HTTPException
from sqlalchemy.orm import Session, joinedload, selectinload, load_only
from sqlalchemy import desc, asc, case, exists, and_, or_, func, literal_column
from typing import List, Optional, Union, Set
from collections import deque
from pathlib import Path
import re

from ..database import get_db
from ..models import Media, Tag, TagAlias, User, Album, TagCategoryEnum, blombooru_album_media, blombooru_media_tags, blombooru_album_hierarchy
from ..config import settings
from .search import parse_search_query, wildcard_to_sql

router = APIRouter(tags=["danbooru"])

# --- MODULE-LEVEL CONSTANTS ---

RATING_MAP = {"safe": "s", "questionable": "q", "explicit": "e"}
CATEGORY_MAP = {"general": 0, "artist": 1, "copyright": 3, "series": 3, "character": 4, "meta": 5}
TAG_WORD_SPLIT_PATTERN = re.compile(r'[_\-]')

# --- HELPERS ---

def format_artist_response(tag: Tag) -> dict:
    """Formats a Tag (Artist) into a Danbooru Artist JSON object"""
    created_at = tag.created_at.isoformat(timespec='milliseconds') if tag.created_at else None
    # Extract aliases
    other_names = [a.alias_name for a in tag.aliases]

    return {
        "id": tag.id,
        "created_at": created_at,
        "name": tag.name,
        # Fallback to created_at since Tag doesn't have updated_at
        "updated_at": created_at,
        "is_deleted": False,
        "group_name": "",
        "is_banned": False,
        "other_names": other_names
    }

def get_flattened_media_ids(db: Session, root_album_id: int) -> List[int]:
    """
    Recursively fetches media IDs for an album and all its descendants (children, grandchildren, etc.).
    Returns a distinct list of media IDs.
    """
    # 1. Collect all Album IDs in the hierarchy using deque for O(1) popleft
    all_album_ids: Set[int] = {root_album_id}
    queue = deque([root_album_id])
    
    while queue:
        current_id = queue.popleft()
        children = db.query(blombooru_album_hierarchy.c.child_album_id).filter(
            blombooru_album_hierarchy.c.parent_album_id == current_id
        ).all()
        
        for (cid,) in children:
            if cid not in all_album_ids:
                all_album_ids.add(cid)
                queue.append(cid)

    # Fetch all media IDs belonging to this set of albums
    results = db.query(blombooru_album_media.c.media_id).filter(
        blombooru_album_media.c.album_id.in_(all_album_ids)
    ).distinct().all()
    
    return sorted(r[0] for r in results)

def format_media_response(media: Media, base_url: str) -> dict:
    """
    Formats a Media object into a Danbooru v2 compatible JSON dictionary.
    """
    # Handle enum value or string representation
    r_val = media.rating.value if hasattr(media.rating, 'value') else str(media.rating)
    rating = RATING_MAP.get(r_val, "q")

    # Generate URLs
    media_id = media.id
    file_url = f"{base_url}/api/media/{media_id}/file"
    has_thumb = bool(media.thumbnail_path)
    preview_url = f"{base_url}/api/media/{media_id}/thumbnail" if has_thumb else file_url
    
    file_ext = Path(media.filename).suffix.lstrip('.') if media.filename else "jpg"
    uploaded_at = media.uploaded_at.isoformat(timespec='milliseconds') if media.uploaded_at else None

    # Categorize Tags (Counts AND Strings)
    tags_by_cat = {0: [], 1: [], 3: [], 4: [], 5: []}
    all_tag_names = []

    for tag in media.tags:
        # Get category name safely
        c_val = tag.category.value if hasattr(tag.category, 'value') else str(tag.category)
        c_id = CATEGORY_MAP.get(c_val.lower(), 0)
        tag_name = tag.name
        tags_by_cat[c_id].append(tag_name)
        all_tag_names.append(tag_name)

    all_tag_names.sort()
    for cat_list in tags_by_cat.values():
        cat_list.sort()

    # Construct Media Asset Variants
    width, height = media.width, media.height
    variants = []

    # A. Thumbnail
    if has_thumb:
        variants.append({"type": "180x180", "url": preview_url, "width": 180, "height": 180, "file_ext": "jpg"})

    # B. Sample
    variants.append({"type": "sample", "url": file_url, "width": width, "height": height, "file_ext": file_ext})

    # C. Original
    variants.append({"type": "original", "url": file_url, "width": width, "height": height, "file_ext": file_ext})

    media_asset = {
        "id": media_id,
        "created_at": uploaded_at,
        "updated_at": uploaded_at,
        "md5": media.hash,
        "file_ext": file_ext,
        "file_size": media.file_size,
        "image_width": width,
        "image_height": height,
        "duration": media.duration,
        "status": "active",
        "file_key": media.hash,
        "is_public": True,
        "pixel_hash": media.hash,
        "variants": variants
    }

    has_children = bool(media.children)
    tag_count = len(all_tag_names)

    return {
        "id": media_id,
        "created_at": uploaded_at,
        "uploader_id": 1,
        "score": 0,
        "source": media.source or "",
        "md5": media.hash,
        "last_comment_bumped_at": None,
        "rating": rating,
        "image_width": width,
        "image_height": height,
        "tag_string": " ".join(all_tag_names),
        "fav_count": 0,
        "file_ext": file_ext,
        "last_noted_at": None,
        "parent_id": media.parent_id,
        "has_children": has_children,
        "approver_id": None,
        "tag_count_general": len(tags_by_cat[0]),
        "tag_count_artist": len(tags_by_cat[1]),
        "tag_count_copyright": len(tags_by_cat[3]),
        "tag_count_character": len(tags_by_cat[4]),
        "tag_count_meta": len(tags_by_cat[5]),
        "tag_count": tag_count,
        "tag_string_general": " ".join(tags_by_cat[0]),
        "tag_string_artist": " ".join(tags_by_cat[1]),
        "tag_string_copyright": " ".join(tags_by_cat[3]),
        "tag_string_character": " ".join(tags_by_cat[4]),
        "tag_string_meta": " ".join(tags_by_cat[5]),
        "file_size": media.file_size,
        "up_score": 0,
        "down_score": 0,
        "is_pending": False,
        "is_flagged": False,
        "is_deleted": False,
        "tag_count_upload_tag": 0,
        "updated_at": uploaded_at,
        "is_banned": False,
        "pixiv_id": None,
        "last_commented_at": None,
        "has_active_children": has_children,
        "has_visible_children": has_children,
        "bit_flags": 0,
        "has_large": True,
        "file_url": file_url,
        "large_file_url": file_url,
        "preview_file_url": preview_url,
        "media_asset": media_asset
    }

def get_base_url(request: Request) -> str:
    base_url = settings.EXTERNAL_SHARE_URL
    if not base_url:
        base_url = str(request.base_url).rstrip('/')
    else:
        base_url = base_url.rstrip('/')
    return base_url

# --- ENDPOINTS ---

@router.get("/explore/posts/popular.json")
@router.get("/explore/posts/viewed.json")
@router.get("/posts.json")
async def get_posts_json(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1),
    tags: str = Query("", description="Space-separated tags"),
    db: Session = Depends(get_db)
):
    """Danbooru v2 compatible posts API"""
    # Clamp limit to a reasonable maximum
    limit = min(limit, 1000)

    query = db.query(Media).options(
        selectinload(Media.tags),
        selectinload(Media.children)
    )

    if tags:
        parsed = parse_search_query(tags)
        include_tags = parsed['include']
        exclude_tags = parsed['exclude']
        wildcards = parsed['wildcards']
        
        # Batch lookup for include tags
        standard_include = []
        for tag_name in include_tags:
            tag_lower = tag_name.lower()
            if tag_lower.startswith("id:"):
                try:
                    id_string = tag_name.split(":", 1)[1]
                    target_ids = [int(x) for x in id_string.split(',') if x.isdigit()]
                    if target_ids:
                        query = query.filter(Media.id.in_(target_ids))
                except ValueError:
                    pass
            elif tag_lower.startswith("order:") or tag_lower.startswith("sort:"):
                continue
            else:
                standard_include.append(tag_lower)
        
        # Batch lookup for standard include tags
        if standard_include:
            found_tags = db.query(Tag).filter(Tag.name.in_(standard_include)).all()
            found_names = {t.name for t in found_tags}
            
            for tag_name in standard_include:
                if tag_name not in found_names:
                    return []
            
            for tag in found_tags:
                query = query.filter(Media.tags.contains(tag))
        
        # Batch lookup for exclude tags
        if exclude_tags:
            exclude_lower = [t.lower() for t in exclude_tags]
            exclude_found = db.query(Tag).filter(Tag.name.in_(exclude_lower)).all()
            for tag in exclude_found:
                query = query.filter(~Media.tags.contains(tag))
        
        for wildcard_type, pattern in wildcards:
            sql_pattern = wildcard_to_sql(pattern)
            subquery = exists().where(
                and_(
                    blombooru_media_tags.c.media_id == Media.id,
                    blombooru_media_tags.c.tag_id == Tag.id,
                    Tag.name.like(sql_pattern)
                )
            )
            if wildcard_type == 'include':
                query = query.filter(subquery)
            else:
                query = query.filter(~subquery)

    query = query.order_by(desc(Media.uploaded_at))
    
    offset = (page - 1) * limit
    media_list = query.offset(offset).limit(limit).all()
    
    base_url = get_base_url(request)
    return [format_media_response(m, base_url) for m in media_list]

# Single Post Details
@router.get("/posts/{post_id}.json")
@router.get("/posts/{post_id}")
async def get_post_json(
    post_id: Union[int, str],
    request: Request,
    db: Session = Depends(get_db)
):
    if isinstance(post_id, str) and ".json" in post_id:
        post_id = int(post_id.replace(".json", ""))
        
    media = db.query(Media).options(
        selectinload(Media.tags),
        selectinload(Media.children)
    ).filter(Media.id == post_id).first()
    
    if not media:
        raise HTTPException(status_code=404, detail="Post not found")
        
    return format_media_response(media, get_base_url(request))

@router.get("/users.json")
async def get_users_json(db: Session = Depends(get_db)):
    user = db.query(User).options(
        load_only(User.id, User.username, User.created_at)
    ).order_by(asc(User.id)).first()
    
    if not user:
        return []
    
    upload_count = db.query(func.count(Media.id)).scalar()
    
    return [{
        "id": user.id,
        "name": user.username,
        "level": 20,
        "base_upload_limit": 1000,
        "post_upload_count": upload_count,
        "post_update_count": 0,
        "note_update_count": 0,
        "is_banned": False,
        "can_upload_free": True,
        "level_string": "Admin",
        "created_at": user.created_at.isoformat(timespec='milliseconds') if user.created_at else "2023-01-01T00:00:00.000-00:00"
    }]

@router.get("/tags.json")
async def get_tags_json(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1),
    search_name_comma: Optional[str] = Query(None, alias="search[name_comma]"),
    search_name_matches: Optional[str] = Query(None, alias="search[name_matches]"),
    search_order: Optional[str] = Query(None, alias="search[order]"),
    search_hide_empty: Optional[str] = Query(None, alias="search[hide_empty]"),
    db: Session = Depends(get_db)
):
    """Danbooru v2 compatible tags API"""
    
    # Clamp limit (apps often request 1000 tags at once)
    limit = min(limit, 1000)
    
    query = db.query(Tag).options(
        load_only(Tag.id, Tag.name, Tag.post_count, Tag.category, Tag.created_at)
    )

    # 1. Search by comma-separated list (Used by app to fetch details for current view)
    if search_name_comma:
        names = [n.strip().lower() for n in search_name_comma.split(',') if n.strip()]
        if names:
            query = query.filter(Tag.name.in_(names))
            
    # 2. Search by wildcard/pattern (Used by tag search bars)
    elif search_name_matches:
        query = query.filter(Tag.name.ilike(f"%{search_name_matches}%"))

    # 3. Filter empty tags
    if search_hide_empty in ("yes", "true"):
        query = query.filter(Tag.post_count > 0)

    # 4. Sorting
    if search_order == "count":
        query = query.order_by(desc(Tag.post_count))
    elif search_order == "date":
        query = query.order_by(desc(Tag.created_at))
    elif search_order == "name":
        query = query.order_by(asc(Tag.name))
    else:
        # Default sort
        query = query.order_by(desc(Tag.post_count))

    # Pagination
    offset = (page - 1) * limit
    tags = query.offset(offset).limit(limit).all()

    # Response Formatting
    results = []
    for tag in tags:
        c_val = tag.category.value if hasattr(tag.category, 'value') else str(tag.category)
        category_id = CATEGORY_MAP.get(c_val.lower(), 0)
        created_at = tag.created_at.isoformat(timespec='milliseconds') if tag.created_at else None

        results.append({
            "id": tag.id,
            "name": tag.name,
            "post_count": tag.post_count,
            "category": category_id,
            "created_at": created_at,
            "updated_at": created_at,
            "is_deprecated": False,
            "words": TAG_WORD_SPLIT_PATTERN.split(tag.name)
        })

    return results

@router.get("/artists.json")
async def get_artists_json(
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1),
    search_any_name_matches: Optional[str] = Query(None, alias="search[any_name_matches]"),
    search_name: Optional[str] = Query(None, alias="search[name]"),
    search_order: Optional[str] = Query(None, alias="search[order]"),
    search_is_deleted: Optional[str] = Query(None, alias="search[is_deleted]"),
    search_has_tag: Optional[str] = Query(None, alias="search[has_tag]"),
    db: Session = Depends(get_db)
):
    """Danbooru v2 compatible Artists API (Mapped from Tags)"""
    
    # Clamp limit
    limit = min(limit, 1000)
    
    # Pre-load aliases
    query = db.query(Tag).options(selectinload(Tag.aliases)).filter(
        Tag.category == TagCategoryEnum.artist
    )

    # Search Logic
    if search_any_name_matches:
        pattern = f"%{search_any_name_matches}%"
        query = query.outerjoin(Tag.aliases).filter(
            or_(
                Tag.name.ilike(pattern),
                TagAlias.alias_name.ilike(pattern)
            )
        )
    elif search_name:
        # Exact/Partial match on name only
        query = query.filter(Tag.name.ilike(f"%{search_name}%"))

    # Sorting Logic
    if search_order == "name":
        query = query.order_by(asc(Tag.name))
    elif search_order in ("created_at", "updated_at"):
        query = query.order_by(desc(Tag.created_at))
    else:
        # Default sort
        query = query.order_by(desc(Tag.created_at))

    offset = (page - 1) * limit
    # distinct() is required because joining aliases might return the same artist row multiple times
    artists = query.distinct().offset(offset).limit(limit).all()

    return [format_artist_response(tag) for tag in artists]

@router.get("/artists/{artist_id}.json")
@router.get("/artists/{artist_id}")
async def get_artist_json(
    artist_id: Union[int, str],
    db: Session = Depends(get_db)
):
    """Danbooru v2 compatible Single Artist API"""
    
    # Clean ID if it contains .json
    if isinstance(artist_id, str) and ".json" in artist_id:
        artist_id = int(artist_id.replace(".json", ""))
    
    # Find tag by ID, ensure it is an artist category, and load aliases
    tag = db.query(Tag).options(selectinload(Tag.aliases)).filter(
        Tag.id == artist_id,
        Tag.category == TagCategoryEnum.artist
    ).first()

    if not tag:
        raise HTTPException(status_code=404, detail="Artist not found")

    return format_artist_response(tag)

@router.get("/pools.json")
async def get_pools_json(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1),
    search_id: Optional[int] = Query(None, alias="search[id]"),
    search_category: Optional[str] = Query(None, alias="search[category]"),
    search_order: Optional[str] = Query(None, alias="search[order]"),
    post_ids_include_all: Optional[int] = Query(None, alias="search[post_ids_include_all]"),
    db: Session = Depends(get_db)
):
    """Danbooru v2 compatible pools index with sorting and pagination"""
    
    # Clamp limit
    limit = min(limit, 1000)
    
    query = db.query(Album).options(
        load_only(Album.id, Album.name, Album.created_at, Album.updated_at)
    )

    if search_id:
        query = query.filter(Album.id == search_id)
    elif post_ids_include_all:
        query = query.join(
            blombooru_album_media,
            Album.id == blombooru_album_media.c.album_id
        ).filter(
            blombooru_album_media.c.media_id == post_ids_include_all
        )

    # Sorting logic
    if search_order == "name":
        query = query.order_by(asc(Album.name))
    elif search_order == "created_at":
        query = query.order_by(desc(Album.created_at))
    elif search_order == "post_count":
        # Subquery to count media in each album
        post_count_subquery = db.query(
            blombooru_album_media.c.album_id,
            func.count(blombooru_album_media.c.media_id).label('media_count')
        ).group_by(blombooru_album_media.c.album_id).subquery()
        
        query = query.outerjoin(
            post_count_subquery,
            Album.id == post_count_subquery.c.album_id
        ).order_by(desc(func.coalesce(post_count_subquery.c.media_count, 0)))
    else:
        query = query.order_by(desc(Album.updated_at))

    offset = (page - 1) * limit
    albums = query.offset(offset).limit(limit).all()
    
    if not albums:
        return []

    results = []
    for album in albums:
        media_ids = get_flattened_media_ids(db, album.id)
        created_at = album.created_at.isoformat(timespec='milliseconds') if album.created_at else None
        updated_at = album.updated_at.isoformat(timespec='milliseconds') if album.updated_at else None

        results.append({
            "id": album.id,
            "name": album.name,
            "created_at": created_at,
            "updated_at": updated_at,
            "description": "",
            "is_active": True,
            "is_deleted": False,
            "post_ids": media_ids,
            "category": "collection",
            "post_count": len(media_ids)
        })
    return results

@router.get("/pools/{pool_id}.json")
@router.get("/pools/{pool_id}")
async def get_single_pool_json(
    pool_id: Union[int, str],
    db: Session = Depends(get_db)
):
    if isinstance(pool_id, str) and ".json" in pool_id:
        pool_id = int(pool_id.replace(".json", ""))
    
    album = db.query(Album).options(
        load_only(Album.id, Album.name, Album.created_at, Album.updated_at)
    ).filter(Album.id == pool_id).first()
    
    if not album:
        raise HTTPException(status_code=404, detail="Pool not found")

    media_ids = get_flattened_media_ids(db, album.id)
    created_at = album.created_at.isoformat(timespec='milliseconds') if album.created_at else None
    updated_at = album.updated_at.isoformat(timespec='milliseconds') if album.updated_at else None

    return {
        "id": album.id,
        "name": album.name,
        "created_at": created_at,
        "updated_at": updated_at,
        "description": "",
        "is_active": True,
        "is_deleted": False,
        "post_ids": media_ids,
        "category": "collection",
        "post_count": len(media_ids)
    }

@router.get("/autocomplete.json")
async def get_autocomplete_json(
    query: Optional[str] = Query(None, alias="search[query]"),
    type: Optional[str] = Query(None, alias="search[type]"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    if not query:
        return []

    tags = db.query(Tag).options(
        load_only(Tag.id, Tag.name, Tag.post_count, Tag.category)
    ).filter(
        Tag.name.ilike(f"%{query}%")
    ).order_by(
        case((Tag.name.ilike(f"{query}%"), 1), else_=2),
        desc(Tag.post_count)
    ).limit(limit).all()

    response_type = type or "tag_query"
    results = []
    for tag in tags:
        c_val = tag.category.value if hasattr(tag.category, 'value') else str(tag.category)
        category_id = CATEGORY_MAP.get(c_val.lower(), 0)
        results.append({
            "type": response_type,
            "label": f"{tag.name} ({tag.post_count})",
            "value": tag.name,
            "category": category_id,
            "post_count": tag.post_count
        })
    return results

@router.get("/related_tag.json")
async def get_related_tag_json(query: Optional[str] = Query(None, alias="search[query]")):
    return {"query": query or "", "tags": []}

@router.get("/counts/posts.json")
async def get_counts_posts_json(db: Session = Depends(get_db)):
    count = db.query(func.count(Media.id)).scalar()
    return {"counts": {"posts": count}}

@router.get("/post_versions.json")
async def get_post_versions_json(post_id: Optional[int] = Query(None, alias="search[post_id]")):
    return []

@router.get("/post_votes.json")
async def get_post_votes_json():
    return []

@router.get("/posts/{post_id}/favorites.json")
async def get_post_favorites_json(post_id: int):
    return []

@router.get("/forum_topics.json")
async def get_forum_topics_json():
    return []

@router.get("/artist_commentaries.json")
async def get_artist_commentaries_json():
    return []

@router.get("/comments.json")
async def get_comments_json():
    return []

@router.get("/explore/posts/searches.json")
async def get_explore_posts_searches_json():
    return []
