import re
from typing import Any, Optional

from sqlalchemy import String, cast, func, literal
from sqlalchemy.orm import Query, Session

from ..models import Album, Media, blombooru_media_tags

MAX_RANDOM_SEED_LENGTH = 32
_RANDOM_SEED_PATTERN = re.compile(r"^\d{1,32}$")


def normalize_random_seed(seed: Optional[str]) -> Optional[str]:
    """Accept only Date.now()-style numeric seeds (digits, max 32 chars)."""
    if not seed or not _RANDOM_SEED_PATTERN.match(seed):
        return None
    return seed


def apply_media_sort(
    query: Query,
    sort_by: str,
    sort_order: str = "desc",
    db: Optional[Session] = None,
    seed: Optional[str] = None,
    column_overrides: Optional[dict[str, Any]] = None,
) -> Query:
    """Apply sort ordering to a Media query at the database level."""
    ascending = sort_order == "asc"
    overrides = column_overrides or {}

    if sort_by == "random":
        normalized_seed = normalize_random_seed(seed)
        if normalized_seed:
            hash_input = func.concat(cast(Media.id, String), literal(normalized_seed))
            return query.order_by(func.md5(hash_input))
        return query.order_by(func.random())

    if sort_by == "tag_count":
        if db is None:
            raise ValueError("db session is required for tag_count sorting")
        tag_count_subq = (
            db.query(func.count(blombooru_media_tags.c.tag_id))
            .filter(blombooru_media_tags.c.media_id == Media.id)
            .scalar_subquery()
        )
        if ascending:
            return query.order_by(tag_count_subq.asc(), Media.id.asc())
        return query.order_by(tag_count_subq.desc(), Media.id.desc())

    if sort_by in overrides:
        sort_column = overrides[sort_by]
    elif sort_by == "filename":
        sort_column = Media.filename
    elif sort_by == "file_size":
        sort_column = Media.file_size
    elif sort_by == "file_type":
        sort_column = Media.file_type
    else:
        sort_column = Media.uploaded_at

    if ascending:
        return query.order_by(sort_column.asc(), Media.id.asc())
    return query.order_by(sort_column.desc(), Media.id.desc())


def apply_album_sort(
    query: Query,
    sort_by: str,
    sort_order: str = "desc",
    seed: Optional[str] = None,
) -> Query:
    """Apply sort ordering to an Album query at the database level."""
    ascending = sort_order == "asc"

    if sort_by == "random":
        normalized_seed = normalize_random_seed(seed)
        if normalized_seed:
            hash_input = func.concat(cast(Album.id, String), literal(normalized_seed))
            return query.order_by(func.md5(hash_input))
        return query.order_by(func.random())

    if sort_by == "name" or sort_by == "filename":
        sort_column = Album.name
    elif sort_by == "last_modified":
        sort_column = Album.last_modified
    else:
        # uploaded_at, created_at, and unknown values default to created_at
        sort_column = Album.created_at

    if ascending:
        return query.order_by(sort_column.asc(), Album.id.asc())
    return query.order_by(sort_column.desc(), Album.id.desc())
