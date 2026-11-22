from typing import (
    Any,
    Dict,
    List,
    Tuple,
)
from sqlalchemy import (
    and_,
    exists,
    false,
    func,
    literal,
    not_,
    or_,
)
from sqlalchemy.orm import Query, Session, aliased
from ...enums import FileTypeEnum, parse_rating_filter
from ...models import (
    Album,
    Media,
    Tag,
    TagCategoryEnum,
    blombooru_media_tags,
)
from .conditions import (
    build_age_condition,
    build_date_condition,
    build_filename_condition,
    build_filesize_condition,
    build_range_condition,
)
from .sorting import apply_sort_ordering
from .tokens import parse_search_query, wildcard_to_regex

def _build_search_conditions_and_similarity(
    parsed_query: Dict[str, Any], db: Session
) -> Tuple[List[Any], List[int]]:
    """
    Builds a list of SQLAlchemy filter conditions for the given parsed search query.
    """
    conditions = []
    similarity_ranked_ids: List[int] = []
    tags = parsed_query.get('tags', {})

    include_names = [name.lower() for name in tags.get('include', [])]
    if include_names:
        found_tags = db.query(Tag).filter(Tag.name.in_(include_names)).all()
        # Use lowercase keys for robust lookup
        found_map = {t.name.lower(): t for t in found_tags}
        
        # If any included tag is missing, result is empty (AND logic)
        for name in include_names:
            if name not in found_map:
                return [literal(False)], []
            
        # Apply filters for found tags
        for tag in found_tags:
            conditions.append(Media.tags.any(Tag.id == tag.id))

    exclude_names = [name.lower() for name in tags.get('exclude', [])]
    if exclude_names:
        found_excluded = db.query(Tag).filter(Tag.name.in_(exclude_names)).all()
        for tag in found_excluded:
            conditions.append(~Media.tags.any(Tag.id == tag.id))

    for wildcard_type, pattern in tags.get('wildcards', []):
        regex_pattern = wildcard_to_regex(pattern)
        is_sqlite = bool(db.bind and db.bind.dialect.name == "sqlite")
        regex_op = 'REGEXP' if is_sqlite else '~*'
        subquery = exists().where(
            and_(
                blombooru_media_tags.c.media_id == Media.id,
                blombooru_media_tags.c.tag_id == Tag.id,
                Tag.name.op(regex_op)(regex_pattern)
            )
        )
        if wildcard_type == 'include':
            conditions.append(subquery)
        else:
            conditions.append(~subquery)
            
    meta = parsed_query.get('meta', {})
    
    def get_numeric_multi_conditions(key, column, converter=int):
        conds = []
        if key in meta:
            for item in meta[key]:
                cond = build_range_condition(column, item['value'], converter=converter)
                if cond is not None:
                    conds.append(not_(cond) if item['negated'] else cond)
        return conds

    conditions.extend(get_numeric_multi_conditions('id', Media.id))
    conditions.extend(get_numeric_multi_conditions('width', Media.width))
    conditions.extend(get_numeric_multi_conditions('height', Media.height))
    conditions.extend(get_numeric_multi_conditions('duration', Media.duration, converter=float))

    if 'filesize' in meta:
        for item in meta['filesize']:
            cond = build_filesize_condition(Media.file_size, item['value'])
            if cond is not None:
                conditions.append(not_(cond) if item['negated'] else cond)

    if 'date' in meta:
        for item in meta['date']:
            cond = build_date_condition(Media.uploaded_at, item['value'])
            if cond is not None:
                conditions.append(not_(cond) if item['negated'] else cond)

    if 'custom_date' in meta:
        for item in meta['custom_date']:
            cond = build_date_condition(Media.custom_date, item['value'])
            if cond is not None:
                conditions.append(not_(cond) if item['negated'] else cond)

    if 'age' in meta:
        for item in meta['age']:
            cond = build_age_condition(Media.uploaded_at, item['value'])
            if cond is not None:
                conditions.append(not_(cond) if item['negated'] else cond)

    if 'custom_age' in meta:
        for item in meta['custom_age']:
            cond = build_age_condition(Media.custom_date, item['value'])
            if cond is not None:
                conditions.append(not_(cond) if item['negated'] else cond)

    if 'rating' in meta:
        for item in meta['rating']:
            ratings = parse_rating_filter(item['value'])

            if ratings:
                if item['negated']:
                    conditions.append(~Media.rating.in_(ratings))
                else:
                    conditions.append(Media.rating.in_(ratings))

    if 'source' in meta:
        for item in meta['source']:
            vals = [v.strip() for v in item['value'].split(',') if v.strip()]
            conds = []
            for v in vals:
                v_lower = v.lower()
                if v_lower == 'none':
                    conds.append(or_(Media.source == None, Media.source == ""))
                elif v_lower == 'http':
                    conds.append(Media.source.like('http%'))
                else:
                    conds.append(or_(
                        Media.source.ilike(f"%{v}%"),
                        Media.source.ilike(f"{v}%")
                    ))

            if conds:
                combined_cond = or_(*conds) if len(conds) > 1 else conds[0]
                if item['negated']:
                    conditions.append(not_(combined_cond))
                else:
                    conditions.append(combined_cond)

    if 'md5' in meta:
        for item in meta['md5']:
            hashes = [h.strip() for h in item['value'].split(',') if h.strip()]
            if hashes:
                if item['negated']:
                    conditions.append(~Media.hash.in_(hashes))
                else:
                    conditions.append(Media.hash.in_(hashes))

    if 'filetype' in meta:
        for item in meta['filetype']:
            types = [t.strip().lower() for t in item['value'].split(',') if t.strip()]
            conds = []
            for t in types:
                if t in ('image', 'video'):
                    conds.append(Media.file_type == FileTypeEnum(t))
                elif t == 'gif':
                    conds.append(or_(Media.file_type == FileTypeEnum.gif, Media.filename.ilike('%.gif')))
                else:
                    conds.append(Media.filename.ilike(f"%.{t}"))

            if conds:
                combined_cond = or_(*conds) if len(conds) > 1 else conds[0]
                if item['negated']:
                    conditions.append(not_(combined_cond))
                else:
                    conditions.append(combined_cond)

    if 'filename' in meta or 'name' in meta:
        items = meta.get('filename', []) + meta.get('name', [])
        for item in items:
            cond = build_filename_condition(Media.filename, item['value'])
            if cond is not None:
                conditions.append(not_(cond) if item['negated'] else cond)

    if 'pool' in meta or 'album' in meta:
        items = meta.get('pool', []) + meta.get('album', [])
        for item in items:
            vals = [v.strip() for v in item['value'].split(',') if v.strip()]
            conds = []
            for v in vals:
                v_lower = v.lower()
                if v_lower == 'any':
                    conds.append(Media.albums.any())
                elif v_lower == 'none':
                    conds.append(~Media.albums.any())
                elif v.isdigit():
                    conds.append(Media.albums.any(Album.id == int(v)))
                else:
                    name_clean = v.replace('_', ' ')
                    conds.append(Media.albums.any(Album.name.ilike(name_clean)))

            if conds:
                combined_cond = or_(*conds) if len(conds) > 1 else conds[0]
                if item['negated']:
                    conditions.append(not_(combined_cond))
                else:
                    conditions.append(combined_cond)

    if 'pool_tree' in meta or 'album_tree' in meta:
        from ..album_utils import get_descendant_ids
        items = meta.get('pool_tree', []) + meta.get('album_tree', [])
        for item in items:
            vals = [v.strip() for v in item['value'].split(',') if v.strip()]
            conds = []
            for v in vals:
                v_lower = v.lower()
                if v_lower == 'any':
                    conds.append(Media.albums.any())
                elif v_lower == 'none':
                    conds.append(~Media.albums.any())
                elif v.isdigit():
                    target_id = int(v)
                    desc_map = get_descendant_ids(db, [target_id])
                    tree_ids = list(desc_map.get(target_id, {target_id}))
                    conds.append(Media.albums.any(Album.id.in_(tree_ids)))
                else:
                    name_clean = v.replace('_', ' ')
                    matching_ids = [
                        r[0] for r in db.query(Album.id).filter(Album.name.ilike(name_clean)).all()
                    ]
                    if matching_ids:
                        desc_map = get_descendant_ids(db, matching_ids)
                        all_tree_ids = set()
                        for aids in desc_map.values():
                            all_tree_ids.update(aids)
                        conds.append(Media.albums.any(Album.id.in_(list(all_tree_ids))))
                    else:
                        conds.append(false())

            if conds:
                combined_cond = or_(*conds) if len(conds) > 1 else conds[0]
                if item['negated']:
                    conditions.append(not_(combined_cond))
                else:
                    conditions.append(combined_cond)

    if 'parent' in meta:
        for item in meta['parent']:
            vals = [v.strip() for v in item['value'].split(',') if v.strip()]
            conds = []
            for v in vals:
                v_lower = v.lower()
                if v_lower == 'none':
                    conds.append(Media.parent_id == None)
                elif v_lower == 'any':
                    conds.append(Media.parent_id != None)
                elif v.isdigit():
                    pid = int(v)
                    conds.append(or_(Media.parent_id == pid, Media.id == pid))

            if conds:
                combined_cond = or_(*conds) if len(conds) > 1 else conds[0]
                if item['negated']:
                    conditions.append(not_(combined_cond))
                else:
                    conditions.append(combined_cond)

    if 'child' in meta:
        for item in meta['child']:
            vals = [v.strip() for v in item['value'].split(',') if v.strip()]
            conds = []
            for v in vals:
                v_lower = v.lower()
                child_alias = aliased(Media)
                if v_lower == 'none':
                    conds.append(~exists().where(child_alias.parent_id == Media.id))
                elif v_lower == 'any':
                    conds.append(exists().where(child_alias.parent_id == Media.id))
                elif v.isdigit():
                    cid = int(v)
                    conds.append(exists().where(and_(child_alias.parent_id == Media.id, child_alias.id == cid)))

            if conds:
                combined_cond = or_(*conds) if len(conds) > 1 else conds[0]
                if item['negated']:
                    conditions.append(not_(combined_cond))
                else:
                    conditions.append(combined_cond)

    tag_counts_map = {
        'tagcount': None,
        'gentags': TagCategoryEnum.general,
        'arttags': TagCategoryEnum.artist,
        'chartags': TagCategoryEnum.character,
        'copytags': TagCategoryEnum.copyright,
        'metatags': TagCategoryEnum.meta
    }
    
    for key, category in tag_counts_map.items():
        if key in meta:
            for item in meta[key]:
                if category is not None:
                     # Join Tag to check category
                     subq = (
                         db.query(func.count(blombooru_media_tags.c.tag_id))
                         .join(Tag, blombooru_media_tags.c.tag_id == Tag.id)
                         .filter(blombooru_media_tags.c.media_id == Media.id)
                         .filter(Tag.category == category)
                         .scalar_subquery()
                     )
                else:
                    subq = (
                        db.query(func.count(blombooru_media_tags.c.tag_id))
                        .filter(blombooru_media_tags.c.media_id == Media.id)
                        .scalar_subquery()
                    )

                cond = build_range_condition(subq, item['value'], converter=int)
                if cond is not None:
                    if item['negated']:
                        conditions.append(not_(cond))
                    else:
                        conditions.append(cond)

    if 'similar_to' in meta or 'similar_to_strict' in meta:
        from ...services.near_duplicates import get_max_distance, similar_to_condition
        strict_pos_values = [item['value'] for item in meta.get('similar_to_strict', []) if not item['negated']]
        pos_values = [item['value'] for item in meta.get('similar_to', []) if not item['negated']]
        neg_values = [
            item['value']
            for key in ('similar_to', 'similar_to_strict')
            for item in meta.get(key, [])
            if item['negated']
        ]
        if strict_pos_values:
            cond, strict_distances = similar_to_condition(
                db, strict_pos_values, negated=False, max_distance=get_max_distance()
            )
            conditions.append(cond)
            similarity_ranked_ids = list(strict_distances.keys())
        if pos_values:
            cond, distances = similar_to_condition(db, pos_values, negated=False)
            conditions.append(cond)
            if not similarity_ranked_ids:
                similarity_ranked_ids = list(distances.keys())
        if neg_values:
            cond, _ = similar_to_condition(db, neg_values, negated=True)
            conditions.append(cond)

    return conditions, similarity_ranked_ids

def build_search_criteria_conditions(parsed_query: Dict[str, Any], db: Session) -> List[Any]:
    """Builds a list of SQLAlchemy filter conditions for the given parsed search query."""
    conditions, _ = _build_search_conditions_and_similarity(parsed_query, db)
    return conditions

def apply_search_criteria(query: Query, parsed_query: Dict[str, Any], db: Session) -> Query:
    """
    Applies the parsed search criteria to a SQLAlchemy query.
    """
    conditions, similarity_ranked_ids = _build_search_conditions_and_similarity(parsed_query, db)
    for cond in conditions:
        query = query.filter(cond)

    order_val = None
    meta = parsed_query.get('meta', {})
    if 'order' in meta:
        order_val = meta['order'][-1]['value']
    elif 'sort' in meta:
        order_val = meta['sort'][-1]['value']
        
    if order_val:
        query = apply_sort_ordering(query, order_val, db, meta, similarity_ranked_ids=similarity_ranked_ids)
    elif similarity_ranked_ids:
        query = apply_sort_ordering(query, 'similarity', db, meta, similarity_ranked_ids=similarity_ranked_ids)

    return query

def apply_custom_filters_or(query: Query, custom_filters: Any, db: Session) -> Query:
    """
    Applies multiple custom filter query strings combined with OR logic.
    Each individual custom filter string has its internal tokens ANDed together.
    """
    if not custom_filters or not isinstance(custom_filters, (list, tuple, str, set)):
        return query

    if isinstance(custom_filters, str):
        filters_list = [custom_filters]
    else:
        filters_list = list(custom_filters)

    clean_filters = [cf.strip() for cf in filters_list if isinstance(cf, str) and cf.strip()]
    if not clean_filters:
        return query

    branch_conditions = []
    for cf in clean_filters:
        cf_parsed = parse_search_query(cf)
        conds = build_search_criteria_conditions(cf_parsed, db)
        if conds:
            if len(conds) == 1:
                branch_conditions.append(conds[0])
            else:
                branch_conditions.append(and_(*conds))
        else:
            branch_conditions.append(literal(True))

    if branch_conditions:
        if len(branch_conditions) == 1:
            query = query.filter(branch_conditions[0])
        else:
            query = query.filter(or_(*branch_conditions))

    return query
