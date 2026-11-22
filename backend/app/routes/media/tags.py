from typing import (
    Dict,
    List,
    Optional,
    Set,
    Union,
)
from sqlalchemy import and_, func
from sqlalchemy.orm import Session
from ...models import Media, Tag, blombooru_media_tags
from ...schemas import ProposedTag
from ...utils.tag_utils import convert_implied_by_names_to_ids, validate_and_resolve_implied_by_ids

def update_tag_counts(db: Session, tag_ids: List[int]):
    """Update post counts for given tags"""
    if not tag_ids:
        return
    counts = db.query(
        blombooru_media_tags.c.tag_id,
        func.count(blombooru_media_tags.c.media_id)
    ).filter(
        blombooru_media_tags.c.tag_id.in_(tag_ids)
    ).group_by(blombooru_media_tags.c.tag_id).all()
    count_map = dict(counts)
    for tag_id in tag_ids:
        db.query(Tag).filter(Tag.id == tag_id).update(
            {"post_count": count_map.get(tag_id, 0)},
            synchronize_session=False
        )

def _clean_implied_by_groups(groups: Optional[list]) -> list[list[str]]:
    if not groups or not isinstance(groups, list):
        return []
    result: list[list[str]] = []
    for grp in groups:
        if isinstance(grp, list):
            cleaned = sorted({str(x).strip().lower() for x in grp if x and str(x).strip()})
            if cleaned and cleaned not in result:
                result.append(cleaned)
    return result

def _normalize_db_implied_by_ids(db: Session, groups: Optional[list]) -> list[list[int]]:
    """Normalize stored implied_by groups into list[list[int]] of Tag.id values."""
    if not groups or not isinstance(groups, list):
        return []
    str_names: set[str] = set()
    for grp in groups:
        if isinstance(grp, list):
            for item in grp:
                if isinstance(item, str) and not item.strip().isdigit():
                    norm = item.strip().lower()
                    if norm:
                        str_names.add(norm)
    name_to_id: dict[str, int] = {}
    if str_names:
        for t_name, t_id in db.query(Tag.name, Tag.id).filter(Tag.name.in_(list(str_names))).all():
            name_to_id[t_name.lower()] = t_id

    result: list[list[int]] = []
    for grp in groups:
        if not isinstance(grp, list):
            continue
        ids: list[int] = []
        for item in grp:
            tid: Optional[int] = None
            if isinstance(item, int) and not isinstance(item, bool):
                tid = item
            elif isinstance(item, str):
                s = item.strip().lower()
                if s.isdigit():
                    tid = int(s)
                else:
                    tid = name_to_id.get(s)
            if tid is not None and tid not in ids:
                ids.append(tid)
        if ids:
            ids.sort()
            if ids not in result:
                result.append(ids)
    return result

def get_or_create_tags_with_implications(
    db: Session,
    tag_names: List[str],
    category_hints: Optional[dict] = None,
    expand: bool = True,
    pre_implied_map: Optional[Dict[str, List[List[str]]]] = None,
) -> tuple[List[Tag], dict[int, list[list[int]]]]:
    """Get or create tags by name, resolving aliases and applying implications,
    returning (tags_list, implied_by_tag_id) where implied_by_tag_id maps
    tag_id -> list[list[int]] of trigger Tag.id groups."""
    from ...models import TagAlias
    from ...utils.tag_utils import expand_implications, resolve_aliases

    # Deduplicate input names
    seen_names: set[str] = set()
    unique_names: list[str] = []
    for name in tag_names:
        name = name.strip().lower()
        if not name or name in seen_names:
            continue
        seen_names.add(name)
        unique_names.append(name)

    all_lookup_names = set(unique_names)
    if pre_implied_map:
        for k in pre_implied_map.keys():
            if k and k.strip():
                all_lookup_names.add(k.strip().lower())

    alias_map = resolve_aliases(db, list(all_lookup_names))

    norm_pre_implied: dict[str, list[list[str]]] = {}
    if pre_implied_map:
        for k, groups in pre_implied_map.items():
            norm_k = k.strip().lower()
            if not norm_k:
                continue
            canon_k = alias_map[norm_k][0].lower() if norm_k in alias_map else norm_k
            cleaned = _clean_implied_by_groups(groups)
            existing = norm_pre_implied.setdefault(canon_k, [])
            for grp in cleaned:
                if grp not in existing:
                    existing.append(grp)

    explicit_tag_set: dict[int, Tag] = {}
    pre_implied_tag_set: dict[int, Tag] = {}

    for name in unique_names:
        if name in alias_map:
            alias = db.query(TagAlias).filter(TagAlias.alias_name == name).first()
            tag = alias.target_tag if alias else None
        else:
            tag = db.query(Tag).filter(Tag.name == name).first()
            if not tag:
                category = "general"
                if category_hints and name in category_hints:
                    category = category_hints[name]
                tag = Tag(name=name, post_count=0, category=category)
                db.add(tag)
                db.flush()

        if tag:
            if tag.name.lower() in norm_pre_implied and tag.id not in explicit_tag_set:
                pre_implied_tag_set[tag.id] = tag
            else:
                explicit_tag_set[tag.id] = tag
                pre_implied_tag_set.pop(tag.id, None)

    explicit_ids = set(explicit_tag_set.keys())
    tag_set: dict[int, Tag] = dict(explicit_tag_set)

    implied_by_name: dict[str, list[list[str]]] = {}
    if expand:
        implied_by_name = expand_implications(db, tag_set)

    for tid, tag in pre_implied_tag_set.items():
        if tid not in tag_set:
            tag_set[tid] = tag

    if expand and pre_implied_tag_set:
        extra_implied_by = expand_implications(
            db,
            tag_set,
            seed_trigger_names={t.name.lower() for t in pre_implied_tag_set.values()},
        )
        for tname, grps in extra_implied_by.items():
            target_list = implied_by_name.setdefault(tname, [])
            for grp in grps:
                if grp not in target_list:
                    target_list.append(grp)

    combined_by_name: dict[str, list[list[str]]] = {}
    for tid, tag in tag_set.items():
        if tid in explicit_ids:
            continue
        merged_groups: list[list[str]] = []
        for grp in norm_pre_implied.get(tag.name.lower(), []):
            if grp not in merged_groups:
                merged_groups.append(grp)
        for grp in implied_by_name.get(tag.name, []):
            if grp not in merged_groups:
                merged_groups.append(grp)
        combined_by_name[tag.name] = merged_groups

    converted_ids = convert_implied_by_names_to_ids(db, combined_by_name, tag_set)
    implied_by_tag_id: dict[int, list[list[int]]] = {}
    for tid in tag_set.keys():
        if tid in explicit_ids:
            continue
        implied_by_tag_id[tid] = converted_ids.get(tid, [])

    return list(tag_set.values()), implied_by_tag_id

def apply_media_tag_implications(
    db: Session,
    media: Media,
    implied_by_tag_id: dict[int, list[list[int]]],
) -> None:
    """Persist implied and implied_by (as Tag.id groups) for a Media item."""
    if not media or not media.id:
        return

    current_tag_ids = [t.id for t in media.tags]
    if not current_tag_ids:
        db.expire(media, ["media_tag_links"])
        return

    non_implied_ids = [tid for tid in current_tag_ids if tid not in implied_by_tag_id]
    if non_implied_ids:
        db.execute(
            blombooru_media_tags.update()
            .where(
                and_(
                    blombooru_media_tags.c.media_id == media.id,
                    blombooru_media_tags.c.tag_id.in_(non_implied_ids),
                )
            )
            .values(implied=False, implied_by=None)
        )

    for tid, groups in implied_by_tag_id.items():
        if tid in current_tag_ids:
            db.execute(
                blombooru_media_tags.update()
                .where(
                    and_(
                        blombooru_media_tags.c.media_id == media.id,
                        blombooru_media_tags.c.tag_id == tid,
                    )
                )
                .values(implied=True, implied_by=groups)
            )

    db.expire(media, ["media_tag_links"])

def resolve_media_tag_update(
    db: Session,
    media_id: int,
    requested_tags: List[str],
    client_implied_tags: Optional[Dict[str, List[List[str]]]] = None,
    category_hints: Optional[dict] = None,
    expand: bool = False,
) -> tuple[List[Tag], dict[int, list[list[int]]]]:
    """Resolve tags and implication attribution when updating an existing media item."""
    from ...models import TagAlias
    from ...utils.tag_utils import expand_implications, resolve_aliases

    old_rows = db.query(
        blombooru_media_tags.c.tag_id,
        blombooru_media_tags.c.implied,
        blombooru_media_tags.c.implied_by,
    ).filter(blombooru_media_tags.c.media_id == media_id).all()

    old_explicit_ids: set[int] = set()
    old_implied_by_id: dict[int, list[list[int]]] = {}
    for t_id, is_imp, imp_by in old_rows:
        if is_imp:
            old_implied_by_id[t_id] = _normalize_db_implied_by_ids(db, imp_by)
        else:
            old_explicit_ids.add(t_id)

    seen_names: set[str] = set()
    unique_names: list[str] = []
    for name in requested_tags:
        name = name.strip().lower()
        if not name or name in seen_names:
            continue
        seen_names.add(name)
        unique_names.append(name)

    alias_map = resolve_aliases(db, unique_names)

    tag_set: dict[int, Tag] = {}
    for name in unique_names:
        if name in alias_map:
            alias = db.query(TagAlias).filter(TagAlias.alias_name == name).first()
            tag = alias.target_tag if alias else None
        else:
            tag = db.query(Tag).filter(Tag.name == name).first()
            if not tag:
                category = "general"
                if category_hints and name in category_hints:
                    category = category_hints[name]
                tag = Tag(name=name, post_count=0, category=category)
                db.add(tag)
                db.flush()
        if tag and tag.id not in tag_set:
            tag_set[tag.id] = tag

    validated_client_implied = validate_and_resolve_implied_by_ids(
        db, tag_set, client_implied_tags
    )

    implied_by_tag_id: dict[int, list[list[int]]] = {}
    newly_added_explicit_names: set[str] = set()

    for tid, tag_obj in tag_set.items():
        if tid in old_explicit_ids:
            continue
        elif tid in old_implied_by_id:
            merged = list(old_implied_by_id[tid])
            for grp in validated_client_implied.get(tid, []):
                if grp not in merged:
                    merged.append(grp)
            implied_by_tag_id[tid] = merged
        else:
            if tid in validated_client_implied:
                implied_by_tag_id[tid] = list(validated_client_implied[tid])
            else:
                newly_added_explicit_names.add(tag_obj.name.lower())

    if expand and client_implied_tags is None and newly_added_explicit_names:
        seed_names = None if not old_rows else newly_added_explicit_names
        backend_implied_by = expand_implications(db, tag_set, seed_trigger_names=seed_names)
        backend_id_groups = convert_implied_by_names_to_ids(db, backend_implied_by, tag_set)
        for tid, tag_obj in tag_set.items():
            if tid in old_explicit_ids or tag_obj.name.lower() in newly_added_explicit_names:
                continue
            if tid in backend_id_groups:
                merged = implied_by_tag_id.setdefault(tid, [])
                for grp in backend_id_groups[tid]:
                    if grp not in merged:
                        merged.append(grp)

    return list(tag_set.values()), implied_by_tag_id

def preview_or_create_tags(
    db: Session,
    tag_names: List[Union[str, dict, "ProposedTag"]],
    category_hints: Optional[dict] = None,
    expand: bool = True,
    dry_run: bool = False,
    pre_implied_map: Optional[Dict[str, List[List[str]]]] = None,
    seed_trigger_names: Optional[Set[str]] = None,
):
    """Get or create tags by name (or preview them without creating if dry_run=True).
    Resolves aliases and applies tag implications.

    Args:
        db: Database session
        tag_names: List of tag name strings, ProposedTag objects, or dicts
        category_hints: Optional dict mapping tag names to category strings
                       (e.g. {"artist_name": "artist", "char_name": "character"}).
                       When a tag doesn't exist and a hint is provided, the tag
                       is created with that category instead of the default "general".
        expand: Whether to recursively expand tag implications. Defaults to True.
        dry_run: When True, do not create new Tag rows in the database;
                 instead return proposed tag objects with is_new boolean.
        pre_implied_map: Optional mapping of previously staged implied tag names
                         to their implied_by trigger groups, carried forward on re-preview.
        seed_trigger_names: Optional set of tag names to seed implication expansion.
    """
    from ...models import TagAlias
    from ...utils.tag_utils import expand_implications, resolve_aliases

    combined_pre_implied: dict[str, list[list[str]]] = {}
    if pre_implied_map:
        for k, grps in pre_implied_map.items():
            if k and str(k).strip():
                norm_k = str(k).strip().lower()
                cleaned = _clean_implied_by_groups(grps)
                target = combined_pre_implied.setdefault(norm_k, [])
                for grp in cleaned:
                    if grp not in target:
                        target.append(grp)

    raw_string_names: list[str] = []
    for item in tag_names:
        if isinstance(item, str):
            raw_string_names.append(item)
        elif isinstance(item, dict):
            n = str(item.get("name", "")).strip()
            if n:
                raw_string_names.append(n)
                if item.get("implied"):
                    norm_n = n.lower()
                    cleaned = _clean_implied_by_groups(item.get("implied_by"))
                    target = combined_pre_implied.setdefault(norm_n, [])
                    for grp in cleaned:
                        if grp not in target:
                            target.append(grp)
        else:
            n = str(getattr(item, "name", "")).strip()
            if n:
                raw_string_names.append(n)
                if getattr(item, "implied", False):
                    norm_n = n.lower()
                    cleaned = _clean_implied_by_groups(getattr(item, "implied_by", None))
                    target = combined_pre_implied.setdefault(norm_n, [])
                    for grp in cleaned:
                        if grp not in target:
                            target.append(grp)

    if not dry_run:
        tags_list, _ = get_or_create_tags_with_implications(
            db,
            raw_string_names,
            category_hints=category_hints,
            expand=expand,
            pre_implied_map=combined_pre_implied if combined_pre_implied else None,
        )
        return tags_list

    # Deduplicate input names
    seen_names: set[str] = set()
    unique_names: list[str] = []
    for name in raw_string_names:
        name = name.strip().lower()
        if not name or name in seen_names:
            continue
        seen_names.add(name)
        unique_names.append(name)

    all_lookup_names = set(unique_names) | set(combined_pre_implied.keys())
    alias_map = resolve_aliases(db, list(all_lookup_names))

    norm_pre_implied: dict[str, list[list[str]]] = {}
    for k, groups in combined_pre_implied.items():
        canon_k = alias_map[k][0].lower() if k in alias_map else k
        existing = norm_pre_implied.setdefault(canon_k, [])
        for grp in groups:
            if grp not in existing:
                existing.append(grp)

    # Dry run

    tag_set: dict[int, Tag] = {}
    explicit_ids: set[int] = set()
    new_tags: list[ProposedTag] = []
    seen_canonical: set[str] = set()

    for name in unique_names:
        if name in alias_map:
            canonical_name, canonical_category = alias_map[name]
            if canonical_name in seen_canonical:
                continue
            seen_canonical.add(canonical_name)
            tag = db.query(Tag).filter(Tag.name == canonical_name).first()
            if tag:
                tag_set[tag.id] = tag
                if canonical_name.lower() not in norm_pre_implied:
                    explicit_ids.add(tag.id)
        else:
            if name in seen_canonical:
                continue
            seen_canonical.add(name)
            tag = db.query(Tag).filter(Tag.name == name).first()
            if tag:
                tag_set[tag.id] = tag
                if name.lower() not in norm_pre_implied:
                    explicit_ids.add(tag.id)
            else:
                category = "general"
                if category_hints and name in category_hints:
                    category = category_hints[name]
                is_pre_imp = name.lower() in norm_pre_implied
                new_tags.append(ProposedTag(
                    name=name,
                    category=category,
                    rating="none",
                    is_new=True,
                    source="user",
                    implied=is_pre_imp,
                    implied_by=list(norm_pre_implied.get(name.lower(), [])) if is_pre_imp else [],
                ))

    implied_by_map: dict[str, list[list[str]]] = {}
    if expand:
        implied_by_map = expand_implications(
            db,
            tag_set,
            extra_names=[nt.name for nt in new_tags],
            seed_trigger_names=seed_trigger_names,
        )

    result: list[ProposedTag] = []
    for tag in tag_set.values():
        is_imp = tag.id not in explicit_ids
        imp_by: list[list[str]] = []
        if is_imp:
            for grp in norm_pre_implied.get(tag.name.lower(), []):
                if grp not in imp_by:
                    imp_by.append(grp)
            for grp in implied_by_map.get(tag.name, []):
                if grp not in imp_by:
                    imp_by.append(grp)
        result.append(ProposedTag(
            name=tag.name,
            category=tag.category,
            rating=tag.rating.value if tag.rating else "none",
            is_new=False,
            source="user",
            implied=is_imp,
            implied_by=imp_by,
        ))
    for n_tag in new_tags:
        if not any(r.name == n_tag.name for r in result):
            result.append(n_tag)

    return result

def get_or_create_tags(db: Session, tag_names: List[str], category_hints: Optional[dict] = None, expand: bool = True) -> List[Tag]:
    """Get or create tags by name, resolving aliases and applying implications."""
    return preview_or_create_tags(db, tag_names, category_hints=category_hints, expand=expand, dry_run=False)
