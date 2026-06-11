from typing import Optional

from sqlalchemy import String, cast, func, literal
from sqlalchemy.orm import Query, Session

from ..models import Media, blombooru_media_tags


def apply_media_sort(
    query: Query,
    sort_by: str,
    sort_order: str = "desc",
    db: Optional[Session] = None,
    seed: Optional[str] = None,
) -> Query:
    """Apply sort ordering to a Media query at the database level."""
    ascending = sort_order == "asc"

    if sort_by == "random":
        if seed:
            hash_input = func.concat(cast(Media.id, String), literal(seed))
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

    sort_column = Media.uploaded_at
    if sort_by == "filename":
        sort_column = Media.filename
    elif sort_by == "file_size":
        sort_column = Media.file_size
    elif sort_by == "file_type":
        sort_column = Media.file_type

    if ascending:
        return query.order_by(sort_column.asc(), Media.id.asc())
    return query.order_by(sort_column.desc(), Media.id.desc())
