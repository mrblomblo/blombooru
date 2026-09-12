import asyncio
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, model_validator
from pydantic.types import conset, StringConstraints
from sqlalchemy import cast, func, or_, select, String
from sqlalchemy.orm import selectinload, Session
from typing import Annotated, Self

from ..auth import require_admin_mode
from ..database import get_db
from ..models import blombooru_implication_implied, blombooru_implication_targets, Media, Tag, TagImplication, User 
from ..utils.cache import invalidate_tag_cache
from ..utils.tag_utils import resolve_implications

router = APIRouter(prefix="/api/tag-implications", tags=["tag-implications"])

class TagRef(BaseModel):
    id: int
    name: str

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
    implied_tags: conset(Tag_Or_Pattern, min_length=1)

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

    query = db.query(TagImplication).options(
        selectinload(TagImplication.target_tags),
        selectinload(TagImplication.implied_tags),
    )

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

@router.post("/expand")
async def expand_tag_implications(
    data: ExpandImplicationsRequest,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db),
):
    """Return additional tags implied by the active implication rules that are not already present in the input set."""
    input_names = [t.strip().lower() for t in data.tags if t.strip()]
    if not input_names:
        return {"implied_tags": []}

    implied = resolve_implications(db, input_names)
    return {"implied_tags": sorted(implied)}

@router.post("/simulate-apply-all")
async def simulate_apply_all_implications(
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """
    Simulate applying all tag implications to all media in the database.
    Runs asynchronously in an executor to avoid blocking the event loop.
    Returns a list of affected media along with the newly implied tags.
    """
    loop = asyncio.get_event_loop()

    def do_simulate_apply_all():
        import fnmatch
        from collections import defaultdict, deque
        from ..models import (
            blombooru_implication_implied,
            blombooru_implication_targets,
            blombooru_media_tags,
            Tag,
            TagImplication,
        )

        # 1. Quick check if any implications exist
        has_implications = db.execute(select(TagImplication.id).limit(1)).scalar_one_or_none()
        if not has_implications:
            return []

        # 2. Bulk load tag id -> name mapping
        tag_rows = db.execute(select(Tag.id, Tag.name)).all()
        if not tag_rows:
            return []
        id_to_name = {tid: name for tid, name in tag_rows}

        # 3. Bulk load implication relationships from association tables
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

        # Map implication_id -> set of implied tag_ids
        imp_to_implied = defaultdict(set)
        for imp_id, tag_id in implied_rows:
            imp_to_implied[imp_id].add(tag_id)

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

        # 4. Compute transitive closure for each tag with outgoing edges using BFS
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

        # 5. Bulk load media tags directly from association table
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

        # 6. For each media item, compute newly implied tags from the closure
        affected_media = []
        for m_id, current_tag_ids in media_to_tags.items():
            implied_ids = set()
            for t_id in current_tag_ids:
                if t_id in closure:
                    implied_ids.update(closure[t_id])

            new_tag_ids = implied_ids - current_tag_ids
            if new_tag_ids:
                added_tags = sorted(id_to_name[tid] for tid in new_tag_ids if tid in id_to_name)
                if added_tags:
                    affected_media.append({
                        "media_id": m_id,
                        "added_tags": added_tags
                    })

        return affected_media

    affected_media = await loop.run_in_executor(None, do_simulate_apply_all)
    return {"affected_media": affected_media}
