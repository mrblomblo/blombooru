import asyncio
import fnmatch
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic.types import StringConstraints
from sqlalchemy import cast, func, or_, select, String
from sqlalchemy.orm import selectinload, Session
from typing import Annotated, Self

from ..auth import require_admin_mode
from ..database import get_db
from .. import database
from ..enums import RatingEnum, TagCategoryEnum
from ..models import blombooru_implication_implied, blombooru_implication_targets, Tag, TagImplication, User 
from ..schemas import TagRatingValue
from ..services.maintenance_jobs import maintenance_jobs
from ..utils.cache import invalidate_media_cache, invalidate_tag_cache
from ..utils.tag_utils import (
    _build_rule_trigger_groups,
    resolve_implications_with_sources,
)

router = APIRouter(prefix="/api/tag-implications", tags=["tag-implications"])

class TagRef(BaseModel):
    id: int
    name: str
    category: TagCategoryEnum = TagCategoryEnum.general
    rating: TagRatingValue = "none"

    @field_validator("rating", mode="before")
    @classmethod
    def normalize_rating(cls, v):
        if v is None:
            return "none"
        if isinstance(v, RatingEnum):
            return v.value
        return str(v).lower()

    class Config:
        from_attributes = True

class TagImplicationResponse(BaseModel):
    id: int
    target_tags: List[TagRef]
    target_tag_patterns: List[str]
    implied_tags: List[TagRef]

    class Config:
        from_attributes = True

# Ensure a lower-case string stripped from whitespace with a minimum length of 1
Tag_Or_Pattern = Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, min_length=1)]

class TagImplicationCreate(BaseModel):
    target_tags: set[Tag_Or_Pattern] = set()
    target_tag_patterns: set[Tag_Or_Pattern] = set()
    implied_tags: set[Tag_Or_Pattern] = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_target_presence(self) -> Self:
        if not self.target_tags and not self.target_tag_patterns:
            raise ValueError("either 'target_tags' or 'target_tag_patterns' is required")
        return self

def _resolve_tag_names(db: Session, tag_names: set[str]) -> List[Tag]:
    """Look up Tag objects by name. Raises 400 if any tag is not found."""
    tags = []
    for name in tag_names:
        normalized = name.strip().lower()
        if not normalized:
            continue
        tag = db.query(Tag).filter(Tag.name == normalized).first()
        if not tag:
            raise HTTPException(status_code=400, detail=f"Tag not found: {normalized}")
        tags.append(tag)
    return tags

def _clean_patterns(patterns: Optional[List[str]]) -> List[str]:
    """Normalize pattern list: strip whitespace, deduplicate, drop empties."""
    if not patterns:
        return []
    seen = set()
    result = []
    for p in patterns:
        p = p.strip().lower()
        if p and p not in seen:
            seen.add(p)
            result.append(p)
    return result

@router.get("/", response_model=List[TagImplicationResponse])
async def list_implications(
    limit: Optional[int] = Query(default=None, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    search: Optional[str] = Query(default=None),
    tag: Optional[str] = Query(default=None, description="Exact tag name to match as target, implied, or pattern"),
    response: Response = Response(),
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """List tag implications, optionally paginated and filtered by search term."""
    # Clean up orphaned implications left empty by cascading tag deletions
    potential_orphans = (
        db.query(TagImplication)
        .options(
            selectinload(TagImplication.target_tags),
            selectinload(TagImplication.implied_tags),
        )
        .filter(~TagImplication.target_tags.any() | ~TagImplication.implied_tags.any())
        .all()
    )

    had_deletions = False
    for imp in potential_orphans:
        patterns = imp.target_tag_patterns or []
        has_targets = len(imp.target_tags) > 0 or len(patterns) > 0
        if not has_targets or len(imp.implied_tags) == 0:
            # Clean up orphaned implications
            db.delete(imp)
            had_deletions = True

    if had_deletions:
        db.commit()

    clean_limit = limit if isinstance(limit, int) else None
    clean_offset = offset if isinstance(offset, int) else 0
    clean_search = search.strip() if isinstance(search, str) and search.strip() else None
    clean_tag = tag.strip().lower() if isinstance(tag, str) and tag.strip() else None

    query = db.query(TagImplication).options(
        selectinload(TagImplication.target_tags),
        selectinload(TagImplication.implied_tags),
    )

    if clean_tag:
        tag_condition = or_(
            TagImplication.target_tags.any(func.lower(Tag.name) == clean_tag),
            TagImplication.implied_tags.any(func.lower(Tag.name) == clean_tag),
        )
        pattern_rows = (
            db.query(TagImplication.id, TagImplication.target_tag_patterns)
            .filter(TagImplication.target_tag_patterns.is_not(None))
            .all()
        )
        matching_pattern_ids = [
            imp_id for imp_id, patterns in pattern_rows
            if any(fnmatch.fnmatch(clean_tag, pat) for pat in (patterns or []))
        ]
        if matching_pattern_ids:
            query = query.filter(or_(tag_condition, TagImplication.id.in_(matching_pattern_ids)))
        else:
            query = query.filter(tag_condition)

    if clean_search:
        term = f"%{clean_search.lower()}%"
        query = query.filter(
            or_(
                TagImplication.target_tags.any(func.lower(Tag.name).like(term)),
                TagImplication.implied_tags.any(func.lower(Tag.name).like(term)),
                cast(TagImplication.target_tag_patterns, String).ilike(term),
            )
        )

    total_count = query.count() if (clean_limit is not None or response is not None) else None

    query = query.order_by(TagImplication.id.desc())
    if clean_offset:
        query = query.offset(clean_offset)
    if clean_limit is not None:
        query = query.limit(clean_limit)

    results = query.all()

    for imp in results:
        if imp.target_tag_patterns is None:
            imp.target_tag_patterns = []

    if response is not None and total_count is not None:
        response.headers["X-Total-Count"] = str(total_count)

    return results

@router.post("/", response_model=TagImplicationResponse, status_code=201)
async def create_implication(
    data: TagImplicationCreate,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Create a new tag implication."""

    target_tags = _resolve_tag_names(db, data.target_tags) if data.target_tags else []
    implied_tags = _resolve_tag_names(db, data.implied_tags)

    target_ids = [tag.id for tag in target_tags]
    implied_ids = [tag.id for tag in implied_tags]

    def matching_count_sq(table, tag_set):
        """Generate a subquery selecting the count of matching tags (target or implied) for each implication"""
        return (
            select(func.count(table.c.tag_id))
            .where(
                table.c.implication_id == TagImplication.id,
                table.c.tag_id.in_([tag.id for tag in tag_set])
            )
            .scalar_subquery()
        )

    def total_count_sq(table):
        """Generate a subquery selecting the total count of tags (target or implied) for each implication"""
        return (
            select(func.count(table.c.tag_id))
            .where(
                table.c.implication_id == TagImplication.id
            )
            .scalar_subquery()
        )

    matching_implied_count = matching_count_sq(blombooru_implication_implied, implied_tags)
    total_implied_count = total_count_sq(blombooru_implication_implied)
    matching_target_count = matching_count_sq(blombooru_implication_targets, target_tags)
    total_target_count = total_count_sq(blombooru_implication_targets)

    stmt = (
        select(TagImplication)
        .where(
            matching_implied_count == len(implied_tags), # it must contain at least the implied tags
            total_implied_count == len(implied_tags),  # but it must not contain any more then those
            matching_target_count == len(target_tags),
            total_target_count == len(target_tags),
        )
    )

    implications = db.execute(stmt).scalars().all()
    exists = any(
        set(imp.target_tag_patterns or ()) == data.target_tag_patterns
        for imp in implications
    )

    if exists:
        raise HTTPException(status_code=409, detail="Implication already exist")

    implication = TagImplication()
    implication.target_tags = target_tags
    implication.target_tag_patterns = list(data.target_tag_patterns) if data.target_tag_patterns else None
    implication.implied_tags = implied_tags

    db.add(implication)
    db.commit()
    db.refresh(implication)
    invalidate_tag_cache()

    if implication.target_tag_patterns is None:
        implication.target_tag_patterns = []

    return implication

@router.put("/{implication_id}", response_model=TagImplicationResponse)
async def update_implication(
    implication_id: int,
    data: TagImplicationCreate,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Update an existing tag implication."""
    implication = db.query(TagImplication).filter(TagImplication.id == implication_id).first()
    if not implication:
        raise HTTPException(status_code=404, detail="Implication not found")

    patterns = _clean_patterns(data.target_tag_patterns)

    if not data.target_tags and not patterns:
        raise HTTPException(status_code=400, detail="At least one target tag or target pattern is required")
    if not data.implied_tags:
        raise HTTPException(status_code=400, detail="At least one implied tag is required")

    target_tags = _resolve_tag_names(db, data.target_tags)
    implied_tags = _resolve_tag_names(db, data.implied_tags)

    if not implied_tags:
        raise HTTPException(status_code=400, detail="At least one implied tag is required")

    implication.target_tags = target_tags
    implication.target_tag_patterns = patterns if patterns else None
    implication.implied_tags = implied_tags

    db.commit()
    db.refresh(implication)
    invalidate_tag_cache()

    if implication.target_tag_patterns is None:
        implication.target_tag_patterns = []

    return implication

@router.delete("/{implication_id}")
async def delete_implication(
    implication_id: int,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Delete a tag implication."""
    implication = db.query(TagImplication).filter(TagImplication.id == implication_id).first()
    if not implication:
        raise HTTPException(status_code=404, detail="Implication not found")

    db.delete(implication)
    db.commit()
    invalidate_tag_cache()

    return {"status": "success"}

class ExpandImplicationsRequest(BaseModel):
    tags: List[str]
    new_tags: Optional[List[str]] = None

@router.post("/expand")
async def expand_tag_implications(
    data: ExpandImplicationsRequest,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db),
):
    """Return additional tags implied by the active implication rules that are not already present in the input set."""
    input_names = [t.strip().lower() for t in data.tags if t.strip()]
    if not input_names:
        return {"implied_tags": [], "implied_by": {}}

    seed_names = None
    if data.new_tags is not None:
        seed_names = [t.strip().lower() for t in data.new_tags if t.strip()]
        if not seed_names:
            return {"implied_tags": [], "implied_by": {}}

    implied, implied_by = resolve_implications_with_sources(db, input_names, seed_tags=seed_names)
    return {"implied_tags": sorted(implied), "implied_by": implied_by}

def _load_implication_rule_structures(db: Session):
    """Load tag lookup maps and compiled implication rule structures for batch operations."""
    from collections import defaultdict
    from ..models import (
        blombooru_implication_implied,
        blombooru_implication_targets,
        Tag,
        TagImplication,
    )

    has_implications = db.execute(select(TagImplication.id).limit(1)).scalar_one_or_none()
    if not has_implications:
        return None

    tag_rows = db.execute(select(Tag.id, Tag.name)).all()
    if not tag_rows:
        return None
    id_to_name = {tid: name for tid, name in tag_rows}

    target_rows = db.execute(
        select(blombooru_implication_targets.c.implication_id, blombooru_implication_targets.c.tag_id)
    ).all()

    implied_rows = db.execute(
        select(blombooru_implication_implied.c.implication_id, blombooru_implication_implied.c.tag_id)
    ).all()

    pattern_rows = db.execute(
        select(TagImplication.id, TagImplication.target_tag_patterns)
        .where(TagImplication.target_tag_patterns.is_not(None))
    ).all()

    imp_to_targets = defaultdict(set)
    for imp_id, tag_id in target_rows:
        imp_to_targets[imp_id].add(tag_id)

    imp_to_implied = defaultdict(set)
    for imp_id, tag_id in implied_rows:
        imp_to_implied[imp_id].add(tag_id)

    imp_to_patterns = {}
    unique_patterns = set()
    for imp_id, patterns in pattern_rows:
        if patterns:
            imp_to_patterns[imp_id] = patterns
            unique_patterns.update(patterns)

    pat_matching_tids = {}
    for pat in unique_patterns:
        pat_matching_tids[pat] = {
            tid for tid, name in tag_rows if fnmatch.fnmatch(name, pat)
        }

    implied_to_rules = defaultdict(list)
    for imp_id, imp_tids in imp_to_implied.items():
        req_tids = imp_to_targets.get(imp_id, set())
        req_pats = imp_to_patterns.get(imp_id, [])
        if not req_tids and not req_pats:
            continue
        for imp_tid in imp_tids:
            implied_to_rules[imp_tid].append((req_tids, req_pats))

    name_to_id = {name: tid for tid, name in tag_rows}

    def compute_groups_for_tag(tid: int, post_tag_ids: set[int]) -> list[list[str]]:
        rules = implied_to_rules.get(tid)
        if not rules:
            return []
        other_tag_ids = post_tag_ids - {tid}
        if not other_tag_ids:
            return []
        groups: list[list[str]] = []
        for req_tids, req_pats in rules:
            if tid in req_tids or not req_tids.issubset(other_tag_ids):
                continue
            base_names = [id_to_name[t] for t in req_tids if t in id_to_name]
            if not req_pats:
                grp = sorted(set(base_names))
                if grp and grp not in groups:
                    groups.append(grp)
            else:
                if not all(bool(other_tag_ids & pat_matching_tids.get(pat, set())) for pat in req_pats):
                    continue
                active_other_names = {id_to_name[t] for t in other_tag_ids if t in id_to_name}
                for grp in _build_rule_trigger_groups(base_names, req_pats, active_other_names):
                    if grp and grp not in groups:
                        groups.append(grp)
        return groups

    def compute_id_groups_for_tag(tid: int, post_tag_ids: set[int]) -> list[list[int]]:
        name_groups = compute_groups_for_tag(tid, post_tag_ids)
        id_groups: list[list[int]] = []
        for grp in name_groups:
            ids = sorted({name_to_id[n] for n in grp if n in name_to_id})
            if ids and ids not in id_groups:
                id_groups.append(ids)
        return id_groups

    return {
        "tag_rows": tag_rows,
        "id_to_name": id_to_name,
        "name_to_id": name_to_id,
        "target_rows": target_rows,
        "implied_rows": implied_rows,
        "pattern_rows": pattern_rows,
        "imp_to_targets": imp_to_targets,
        "imp_to_implied": imp_to_implied,
        "imp_to_patterns": imp_to_patterns,
        "pat_matching_tids": pat_matching_tids,
        "implied_to_rules": implied_to_rules,
        "compute_groups_for_tag": compute_groups_for_tag,
        "compute_id_groups_for_tag": compute_id_groups_for_tag,
    }

def _do_simulate_apply_all_implications(progress_cb=None):
    from collections import defaultdict, deque
    from ..models import blombooru_media_tags

    db = database.SessionLocal()
    try:
        structures = _load_implication_rule_structures(db)
        if not structures:
            return []

        tag_rows = structures["tag_rows"]
        id_to_name = structures["id_to_name"]
        target_rows = structures["target_rows"]
        pattern_rows = structures["pattern_rows"]
        imp_to_implied = structures["imp_to_implied"]
        compute_groups_for_tag = structures["compute_groups_for_tag"]

        # Build trigger graph: trigger_tag_id -> set of implied tag_ids
        direct_graph = defaultdict(set)
        for imp_id, tag_id in target_rows:
            if imp_id in imp_to_implied:
                direct_graph[tag_id].update(imp_to_implied[imp_id])

        # Evaluate wildcard patterns across existing tags
        if pattern_rows:
            for imp_id, patterns in pattern_rows:
                if not patterns or imp_id not in imp_to_implied:
                    continue
                rule_implied = imp_to_implied[imp_id]
                for tid, name in tag_rows:
                    if any(fnmatch.fnmatch(name, pat) for pat in patterns):
                        direct_graph[tid].update(rule_implied)

        if not direct_graph:
            return []

        # Compute transitive closure for each tag with outgoing edges using BFS
        closure = {}
        for start_tag in direct_graph:
            visited = set()
            queue = deque([start_tag])
            while queue:
                curr = queue.popleft()
                for nxt in direct_graph.get(curr, ()):
                    if nxt not in visited and nxt != start_tag:
                        visited.add(nxt)
                        queue.append(nxt)
            if visited:
                closure[start_tag] = visited

        if not closure:
            return []

        # Bulk load media tags directly from association table
        media_tag_rows = db.execute(
            select(blombooru_media_tags.c.media_id, blombooru_media_tags.c.tag_id)
            .order_by(blombooru_media_tags.c.media_id)
        ).all()

        if not media_tag_rows:
            return []

        # Group tag IDs by media_id
        media_to_tags = defaultdict(set)
        for m_id, t_id in media_tag_rows:
            media_to_tags[m_id].add(t_id)

        total = len(media_to_tags)
        if progress_cb:
            progress_cb(current=0, total=total)

        # For each media item, compute newly implied tags from the closure
        affected_media = []
        for idx, (m_id, current_tag_ids) in enumerate(media_to_tags.items(), start=1):
            if progress_cb and (idx % 100 == 0 or idx == total):
                progress_cb(current=idx)

            implied_ids = set()
            for t_id in current_tag_ids:
                if t_id in closure:
                    implied_ids.update(closure[t_id])

            new_tag_ids = implied_ids - current_tag_ids
            if new_tag_ids:
                all_post_tids = current_tag_ids | new_tag_ids
                added_tags = sorted(id_to_name[tid] for tid in new_tag_ids if tid in id_to_name)
                if added_tags:
                    item_implied_by = {}
                    for tid in new_tag_ids:
                        t_name = id_to_name.get(tid)
                        if not t_name:
                            continue
                        groups = compute_groups_for_tag(tid, all_post_tids)
                        if groups:
                            item_implied_by[t_name] = groups
                    affected_media.append({
                        "media_id": m_id,
                        "added_tags": added_tags,
                        "implied_by": item_implied_by,
                    })

        return affected_media
    finally:
        db.close()

@router.post("/simulate-apply-all")
async def simulate_apply_all_implications(
    background: bool = False,
    current_user: User = Depends(require_admin_mode),
):
    """
    Simulate applying all tag implications to all media in the database.
    Runs asynchronously in an executor to avoid blocking the event loop.
    Returns a list of affected media along with the newly implied tags.
    """
    if background:
        started, status = maintenance_jobs.start_job(
            "apply_implications",
            lambda cb: {"affected_media": _do_simulate_apply_all_implications(progress_cb=cb)},
        )
        return {"status": "started" if started else "already_running", "job": status}

    loop = asyncio.get_running_loop()
    affected_media = await loop.run_in_executor(None, _do_simulate_apply_all_implications)
    return {"affected_media": affected_media}

def _do_backfill_implied_tags(progress_cb=None):
    from collections import defaultdict
    from sqlalchemy import and_
    from ..models import blombooru_media_tags

    db = database.SessionLocal()
    try:
        structures = _load_implication_rule_structures(db)
        if not structures:
            return {"status": "success", "updated_media_count": 0, "updated_tags_count": 0}

        implied_to_rules = structures["implied_to_rules"]
        name_to_id = structures["name_to_id"]
        compute_id_groups_for_tag = structures["compute_id_groups_for_tag"]
        if not implied_to_rules:
            return {"status": "success", "updated_media_count": 0, "updated_tags_count": 0}

        rows = db.execute(
            select(
                blombooru_media_tags.c.media_id,
                blombooru_media_tags.c.tag_id,
                blombooru_media_tags.c.implied,
                blombooru_media_tags.c.implied_by,
            ).order_by(blombooru_media_tags.c.media_id)
        ).all()

        if not rows:
            return {"status": "success", "updated_media_count": 0, "updated_tags_count": 0}

        def _normalize_id_groups(raw_grps) -> list[list[int]]:
            if not isinstance(raw_grps, list):
                return []
            norm: list[list[int]] = []
            for g in raw_grps:
                if not isinstance(g, list):
                    continue
                ids: list[int] = []
                for x in g:
                    tid_val = None
                    if isinstance(x, int) and not isinstance(x, bool):
                        tid_val = x
                    elif isinstance(x, str):
                        s = x.strip().lower()
                        if s.isdigit():
                            tid_val = int(s)
                        else:
                            tid_val = name_to_id.get(s)
                    if tid_val is not None and tid_val not in ids:
                        ids.append(tid_val)
                if ids:
                    ids.sort()
                    if ids not in norm:
                        norm.append(ids)
            return norm

        media_to_tags = defaultdict(set)
        existing_meta = {}
        for m_id, t_id, is_imp, imp_by in rows:
            media_to_tags[m_id].add(t_id)
            existing_meta[(m_id, t_id)] = (bool(is_imp), _normalize_id_groups(imp_by), imp_by)

        total = len(media_to_tags)
        if progress_cb:
            progress_cb(current=0, total=total, updated_media=0, updated_tags=0)

        candidate_implied_tids = set(implied_to_rules.keys())
        updates_to_apply = []
        affected_media_ids = set()

        for idx, (m_id, post_tag_ids) in enumerate(media_to_tags.items(), start=1):
            possible_tids = post_tag_ids & candidate_implied_tids
            if possible_tids:
                for tid in possible_tids:
                    groups = compute_id_groups_for_tag(tid, post_tag_ids)
                    if not groups:
                        continue
                    old_imp, old_groups, raw_old = existing_meta.get((m_id, tid), (False, [], None))
                    merged_groups = list(old_groups)
                    for grp in groups:
                        if grp not in merged_groups:
                            merged_groups.append(grp)
                    if not old_imp or merged_groups != raw_old:
                        updates_to_apply.append((m_id, tid, merged_groups))
                        affected_media_ids.add(m_id)

            if progress_cb and (idx % 100 == 0 or idx == total):
                progress_cb(
                    current=idx,
                    updated_media=len(affected_media_ids),
                    updated_tags=len(updates_to_apply),
                )

        if updates_to_apply:
            for m_id, tid, merged_groups in updates_to_apply:
                db.execute(
                    blombooru_media_tags.update()
                    .where(
                        and_(
                            blombooru_media_tags.c.media_id == m_id,
                            blombooru_media_tags.c.tag_id == tid,
                        )
                    )
                    .values(implied=True, implied_by=merged_groups)
                )
            db.commit()
            invalidate_media_cache()

        return {
            "status": "success",
            "updated_media_count": len(affected_media_ids),
            "updated_tags_count": len(updates_to_apply),
        }
    finally:
        db.close()

@router.post("/backfill-implied-tags")
async def backfill_implied_tags(
    background: bool = False,
    current_user: User = Depends(require_admin_mode),
):
    """
    Backfill implied=True and implied_by on existing blombooru_media_tags rows
    where both trigger tag(s) and implied tag are present on a media item.
    """
    if background:
        started, status = maintenance_jobs.start_job(
            "backfill_implied_tags",
            _do_backfill_implied_tags,
            initial_fields={"updated_media": 0, "updated_tags": 0},
        )
        return {"status": "started" if started else "already_running", "job": status}

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _do_backfill_implied_tags)
