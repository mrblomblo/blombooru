from typing import Iterable, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from ..models import Media
from .logger import logger

def normalize_child_ids(child_media_ids: Optional[Iterable[int]]) -> List[int]:
    """Drop falsy values and duplicates, keeping the order."""
    return list(dict.fromkeys(int(c) for c in (child_media_ids or []) if c))

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
