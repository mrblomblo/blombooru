from typing import (
    Any,
    Dict,
    List,
    Optional,
)
from sqlalchemy import (
    Float,
    case,
    cast,
    func,
    literal,
)
from sqlalchemy.orm import Query, Session
from ...models import (
    Media,
    Tag,
    TagCategoryEnum,
    blombooru_media_tags,
)

def apply_sort_ordering(
    query: Query,
    order_val: str,
    db: Session,
    parsed_meta: Dict[str, Any],
    similarity_ranked_ids: Optional[List[int]] = None,
) -> Query:
    """
    Applies comprehensive sorting with full _asc and _desc support for all fields.
    """
    order_val = order_val.strip().lower()

    ascending = False
    base_sort = order_val
    if order_val.endswith('_asc'):
        ascending = True
        base_sort = order_val[:-4]
    elif order_val.endswith('_desc'):
        ascending = False
        base_sort = order_val[:-5]
    elif order_val.startswith('random'):
        base_sort = 'random'
    else:
        # Default direction per base_sort
        if base_sort in ('filename', 'name', 'md5', 'hash', 'rating', 'similarity', 'similar'):
            ascending = True
        else:
            ascending = False

    if base_sort in ('id',):
        return query.order_by(Media.id.asc() if ascending else Media.id.desc())

    if base_sort in ('date', 'uploaded_at', 'created_at', 'time'):
        col = Media.uploaded_at
        return query.order_by(col.asc() if ascending else col.desc(), Media.id.asc() if ascending else Media.id.desc())

    if base_sort in ('custom_date',):
        col = Media.custom_date
        return query.order_by(col.asc() if ascending else col.desc(), Media.id.asc() if ascending else Media.id.desc())

    if base_sort in ('filesize', 'file_size', 'size'):
        col = Media.file_size
        return query.order_by(col.asc() if ascending else col.desc(), Media.id.asc() if ascending else Media.id.desc())

    if base_sort in ('width',):
        col = Media.width
        return query.order_by(col.asc() if ascending else col.desc(), Media.id.asc() if ascending else Media.id.desc())

    if base_sort in ('height',):
        col = Media.height
        return query.order_by(col.asc() if ascending else col.desc(), Media.id.asc() if ascending else Media.id.desc())

    if base_sort in ('mpixels', 'resolution', 'pixels', 'area'):
        expr = Media.width * Media.height
        return query.order_by(expr.asc() if ascending else expr.desc(), Media.id.asc() if ascending else Media.id.desc())

    if base_sort in ('duration',):
        col = Media.duration
        return query.order_by(col.asc() if ascending else col.desc(), Media.id.asc() if ascending else Media.id.desc())

    if base_sort in ('landscape', 'aspect_ratio'):
        expr = cast(Media.width, Float) / func.nullif(Media.height, 0)
        return query.order_by(expr.asc() if ascending else expr.desc(), Media.id.asc() if ascending else Media.id.desc())

    if base_sort in ('portrait',):
        expr = cast(Media.height, Float) / func.nullif(Media.width, 0)
        return query.order_by(expr.asc() if ascending else expr.desc(), Media.id.asc() if ascending else Media.id.desc())

    if base_sort in ('tagcount', 'tag_count', 'tags'):
        subq = (
            db.query(func.count(blombooru_media_tags.c.tag_id))
            .filter(blombooru_media_tags.c.media_id == Media.id)
            .scalar_subquery()
        )
        return query.order_by(subq.asc() if ascending else subq.desc(), Media.id.asc() if ascending else Media.id.desc())

    category_sort_map = {
        'gentags': TagCategoryEnum.general,
        'arttags': TagCategoryEnum.artist,
        'chartags': TagCategoryEnum.character,
        'copytags': TagCategoryEnum.copyright,
        'metatags': TagCategoryEnum.meta,
    }
    if base_sort in category_sort_map:
        cat = category_sort_map[base_sort]
        subq = (
            db.query(func.count(blombooru_media_tags.c.tag_id))
            .join(Tag, blombooru_media_tags.c.tag_id == Tag.id)
            .filter(blombooru_media_tags.c.media_id == Media.id)
            .filter(Tag.category == cat)
            .scalar_subquery()
        )
        return query.order_by(subq.asc() if ascending else subq.desc(), Media.id.asc() if ascending else Media.id.desc())

    if base_sort in ('rating',):
        col = Media.rating
        return query.order_by(col.asc() if ascending else col.desc(), Media.id.asc() if ascending else Media.id.desc())

    if base_sort in ('filename', 'name'):
        col = Media.filename
        return query.order_by(col.asc() if ascending else col.desc(), Media.id.asc() if ascending else Media.id.desc())

    if base_sort in ('filetype', 'file_type'):
        col = Media.file_type
        return query.order_by(col.asc() if ascending else col.desc(), Media.id.asc() if ascending else Media.id.desc())

    if base_sort in ('md5', 'hash'):
        col = Media.hash
        return query.order_by(col.asc() if ascending else col.desc(), Media.id.asc() if ascending else Media.id.desc())

    if base_sort in ('random', 'rank', 'shuffle'):
        seed = "0"
        if ':' in order_val:
            seed = order_val.split(':', 1)[1].strip()
        from sqlalchemy import String
        hash_input = func.concat(cast(Media.id, String), literal(seed))
        return query.order_by(func.md5(hash_input))

    if base_sort == 'custom':
        id_list = None
        if 'id' in parsed_meta:
            for item in parsed_meta['id']:
                if ',' in item['value']:
                    try:
                        id_list = [int(x) for x in item['value'].split(',') if x.strip().isdigit()]
                        if id_list:
                            whens = {id_: i for i, id_ in enumerate(id_list)}
                            return query.order_by(case(whens, value=Media.id))
                    except (ValueError, TypeError):
                        pass

    if base_sort in ('similarity', 'similar') and similarity_ranked_ids:
        ordered_ids = similarity_ranked_ids if ascending else list(reversed(similarity_ranked_ids))
        capped = ordered_ids[:10000]
        whens = {mid: i for i, mid in enumerate(capped)}
        return query.order_by(
            case(whens, value=Media.id, else_=len(capped)),
            Media.id.asc() if ascending else Media.id.desc(),
        )

    # Fallback to default
    col = Media.uploaded_at
    return query.order_by(col.desc(), Media.id.desc())
