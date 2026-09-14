import fnmatch
import time
from collections.abc import Iterable
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

if TYPE_CHECKING:
    from ..models import Tag

def resolve_aliases(db: Session, raw_names: list[str]) -> dict[str, tuple[str, str]]:
    """Build an alias lookup map for a list of (already lowercased) tag names."""
    from ..models import TagAlias

    if not raw_names:
        return {}

    aliases = db.query(TagAlias).filter(TagAlias.alias_name.in_(raw_names)).all()
    return {
        a.alias_name: (a.target_tag.name, a.target_tag.category)
        for a in aliases
    }

def _expand_implications(db: Session, tags: Iterable["Tag"], *, max_depth: int) -> list["Tag"]:
    """
    Recursively expand all tag implications given a list of tags.
    Returns all tags that were not in the original input.
    """

    if not tags:
        return []

    from ..models import Tag, TagImplication, blombooru_implication_targets
    from ..utils.logger import logger

    start_time = time.perf_counter()

    initial_tags = set(tags)
    active_tags = set(tags)
    active_ids: set[int] = {tag.id for tag in initial_tags}

    # Fetch standalone pattern rules (implications with wildcard patterns but no target tags)
    pattern_only_rules = db.execute(
        select(TagImplication)
        .where(
            TagImplication.target_tag_patterns.is_not(None),
            ~TagImplication.target_tags.any(),
        )
        .options(selectinload(TagImplication.implied_tags))
    ).scalars().all()

    applied_implications: set[int] = set()
    depth_reached = 0

    for depth in range(max_depth):
        depth_reached = depth
        newly_implied: set[Tag] = set()

        # Evaluate pattern-only implications against current tag names
        for rule in pattern_only_rules:
            if rule.id in applied_implications:
                continue
            patterns = rule.target_tag_patterns or []
            if patterns and all(any(fnmatch.fnmatch(tag.name, pat) for tag in active_tags) for pat in patterns):
                applied_implications.add(rule.id)
                newly_implied.update(rule.implied_tags)

        # Evaluate target-tag implications targeting any current tag IDs
        if active_ids:
            stmt = (
                select(TagImplication)
                .join(
                    blombooru_implication_targets,
                    TagImplication.id == blombooru_implication_targets.c.implication_id,
                )
                .where(
                    blombooru_implication_targets.c.tag_id.in_(active_ids),
                )
                .options(
                    selectinload(TagImplication.target_tags),
                    selectinload(TagImplication.implied_tags),
                )
                .distinct(TagImplication.id)
            )
            if applied_implications:
                stmt = stmt.where(~TagImplication.id.in_(applied_implications))

            candidates = db.execute(stmt).scalars().all()

            for rule in candidates:
                if rule.id in applied_implications:
                    continue

                # Every target tag must be present in the active ID set
                if not all(t.id in active_ids for t in rule.target_tags):
                    continue

                # Any associated pattern constraints must also be satisfied
                patterns = rule.target_tag_patterns
                if patterns:
                    if not all(any(fnmatch.fnmatch(tag.name, pat) for tag in active_tags) for pat in patterns):
                        continue

                applied_implications.add(rule.id)
                newly_implied.update(rule.implied_tags)

        # Determine if any genuinely new tags were introduced in this pass
        new_ids = {t.id for t in newly_implied if t.id not in active_ids}

        if not new_ids:
            break

        active_tags.update(newly_implied)
        active_ids.update(new_ids)

    logger.debug(
        f"Implication expansion finished in {time.perf_counter() - start_time:.3f}s "
        f"(depth={depth_reached}, implied={len(active_tags) - len(initial_tags)})"
    )
    return [tag for tag in active_tags - initial_tags]

def expand_implications(db: Session, tag_set: dict[int, "Tag"]) -> None:
    """Recursively expand tag implications into *tag_set*, mutating it in place."""
    if not tag_set:
        return

    implied_tags = _expand_implications(db, tag_set.values(), max_depth=1_000)
    tag_set |= {t.id: t for t in implied_tags}

def resolve_implications(db: Session, tags: list[str], max_depth: int = 10) -> list["Tag"]:
    """
    Recursively resolve all tag implications for a given list of tag names.
    Returns the names of all implied tags that were not in the original input.
    """
    if not tags:
        return []

    from ..models import Tag

    initial_raw = {t.strip().lower() for t in tags if t and t.strip()}
    if not initial_raw:
        return []

    alias_map = resolve_aliases(db, list(initial_raw))
    initial_names = {alias_map[t][0].lower() if t in alias_map else t for t in initial_raw}

    # Resolve database IDs for any known tags in the initial set
    inital_tags: set[Tag] = set(db.scalars(
        select(Tag).where(Tag.name.in_(initial_names))
    ).all())

    implied_tags = _expand_implications(db, inital_tags, max_depth=max_depth)

    return sorted(tag.name for tag in implied_tags)
