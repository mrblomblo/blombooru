from typing import Dict, Iterable, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from ..models import Media
from .logger import logger

def normalize_child_ids(child_media_ids: Optional[Iterable[int]]) -> List[int]:
    """Drop falsy values and duplicates, keeping the order."""
    return list(dict.fromkeys(int(c) for c in (child_media_ids or []) if c))

def queued_children_of(items: Dict[str, dict], item_id: str) -> List[str]:
    """Return staged item IDs in the session currently pointing at ``item_id`` as their parent."""
    return [
        oid for oid, other in items.items()
        if oid != item_id and other.get("parent_item_id") == item_id
    ]

def parent_problem(db: Session, parent_media_id: int) -> Optional[Tuple[int, str]]:
    """Why the new post cannot become a child of ``parent_media_id`` as ``(status, message)``."""
    parent = db.query(Media.id, Media.parent_id).filter(Media.id == parent_media_id).first()
    if parent is None:
        return 404, "Parent media not found"
    if parent.parent_id:
        return 400, "The selected parent is already a child of another item"
    return None

def child_problem(db: Session, child_media_id: int) -> Optional[Tuple[int, str]]:
    """Why the new post cannot become the parent of ``child_media_id`` as ``(status, message)``."""
    if db.query(Media.id).filter(Media.id == child_media_id).first() is None:
        return 404, f"Media {child_media_id} not found"
    if db.query(Media.id).filter(Media.parent_id == child_media_id).first() is not None:
        return 400, f"Media {child_media_id} already has children and cannot be a child itself"
    return None

def relation_problem(
    db: Session,
    parent_media_id: Optional[int],
    child_media_ids: Optional[Iterable[int]],
) -> Optional[Tuple[int, str]]:
    """First problem with a requested pending relation, or ``None`` if it is valid right now."""
    children = normalize_child_ids(child_media_ids)
    if parent_media_id and children:
        return 400, "An upload cannot be both a child and a parent"
    if parent_media_id:
        return parent_problem(db, parent_media_id)
    for child_id in children:
        problem = child_problem(db, child_id)
        if problem:
            return problem
    return None

def staged_relation_problem(
    db: Session,
    items: Dict[str, dict],
    item_id: str,
    parent_media_id: Optional[int],
    child_media_ids: Optional[Iterable[int]],
    parent_item_id: Optional[str],
) -> Optional[Tuple[int, str]]:
    """Validate pending relations for a staged item, including queue-to-queue links."""
    if parent_media_id and parent_item_id:
        return 400, "An upload cannot have two parents"

    children = normalize_child_ids(child_media_ids)
    queued_children = queued_children_of(items, item_id)
    if (parent_media_id or parent_item_id) and (children or queued_children):
        return 400, "An upload cannot be both a child and a parent"

    if parent_item_id:
        if parent_item_id == item_id:
            return 400, "An upload cannot be its own parent"
        parent_item = items.get(parent_item_id)
        if parent_item is None:
            return 404, "Parent staged item not found"
        if parent_item.get("parent_media_id") or parent_item.get("parent_item_id"):
            return 400, "The selected parent is already a child of another item"

    return relation_problem(db, parent_media_id, children)

def apply_pending_relations(
    db: Session,
    new_media: Media,
    parent_media_id: Optional[int],
    child_media_ids: Optional[Iterable[int]],
) -> Set[int]:
    """Apply an upload's pending relation to its freshly created post (the caller commits)."""
    affected: Set[int] = set()

    if parent_media_id:
        problem = parent_problem(db, parent_media_id)
        if problem:
            logger.warning(f"Skipping relation of new media {new_media.id} to parent {parent_media_id}: {problem[1]}")
        else:
            new_media.parent_id = parent_media_id
            affected.update({new_media.id, parent_media_id})
        return affected

    for child_id in normalize_child_ids(child_media_ids):
        problem = child_problem(db, child_id)
        if problem:
            logger.warning(f"Skipping relation of new media {new_media.id} as parent of {child_id}: {problem[1]}")
            continue
        child = db.query(Media).filter(Media.id == child_id).one()
        if child.parent_id:
            affected.add(child.parent_id)  # loses a child
        child.parent_id = new_media.id
        affected.update({new_media.id, child_id})
    return affected

def apply_pending_queue_relations(
    db: Session,
    created_by_item_id: Dict[str, Media],
    items: Dict[str, dict],
) -> Set[int]:
    """Apply pending parent_item_id links between newly created posts from the same session."""
    affected: Set[int] = set()
    for item_id, item in items.items():
        parent_item_id = item.get("parent_item_id")
        if not parent_item_id:
            continue
        child_media = created_by_item_id.get(item_id)
        parent_media = created_by_item_id.get(parent_item_id)
        if child_media is None or parent_media is None:
            logger.warning(
                f"Skipping queue relation for staged item {item_id} -> {parent_item_id}: target post was not created"
            )
            continue
        if child_media.id == parent_media.id:
            continue
        if child_media.parent_id:
            logger.warning(f"Skipping queue relation for new media {child_media.id}: already has parent {child_media.parent_id}")
            continue
        if parent_media.parent_id:
            logger.warning(f"Skipping queue relation for new media {child_media.id}: parent {parent_media.id} is already a child")
            continue
        if db.query(Media.id).filter(Media.parent_id == child_media.id).first() is not None:
            logger.warning(f"Skipping queue relation for new media {child_media.id}: already has children")
            continue
        child_media.parent_id = parent_media.id
        affected.update({child_media.id, parent_media.id})
        db.flush()
    return affected
