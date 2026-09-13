from typing import Any, Dict, List, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Album, blombooru_album_hierarchy

def resolve_album_path(db: Session, relative_dir: Optional[str]) -> List[Dict[str, Any]]:
    """Given a relative directory path, walk existing Album rows top-down, matching by case-insensitive name at each hierarchy depth."""
    if not relative_dir:
        return []

    normalized = relative_dir.replace("\\", "/").strip().strip("/")
    if not normalized:
        return []

    segments = [s.strip() for s in normalized.split("/") if s.strip()]
    if not segments:
        return []

    results: List[Dict[str, Any]] = []
    prev_existing_id: Optional[int] = None

    for depth, seg in enumerate(segments):
        canonical_name = seg
        existing_id: Optional[int] = None

        if depth == 0:
            # Look for root album (no parent in blombooru_album_hierarchy) matching case-insensitively
            root_album = (
                db.query(Album)
                .filter(
                    func.lower(Album.name) == seg.lower(),
                    ~Album.id.in_(db.query(blombooru_album_hierarchy.c.child_album_id)),
                )
                .first()
            )
            if root_album:
                existing_id = root_album.id
                canonical_name = root_album.name
        else:
            # Look for child album of prev_existing_id if previous segment resolved
            if prev_existing_id is not None:
                child_album = (
                    db.query(Album)
                    .join(
                        blombooru_album_hierarchy,
                        Album.id == blombooru_album_hierarchy.c.child_album_id,
                    )
                    .filter(
                        blombooru_album_hierarchy.c.parent_album_id == prev_existing_id,
                        func.lower(Album.name) == seg.lower(),
                    )
                    .first()
                )
                if child_album:
                    existing_id = child_album.id
                    canonical_name = child_album.name

        results.append({
            "name": canonical_name,
            "existing_id": existing_id,
            "depth": depth,
        })
        prev_existing_id = existing_id

    return results

def apply_folder_mapping_to_path(relative_path: Optional[str], mode: str = "use_root") -> Optional[str]:
    """Given a relative file path, extract and transform its directory path according to the chosen folder mapping mode."""
    if not relative_path or mode == "flatten":
        return None

    normalized = relative_path.replace("\\", "/").strip().strip("/")
    if "/" not in normalized:
        return None

    parts = [p.strip() for p in normalized.split("/") if p.strip()]
    if len(parts) <= 1:
        return None

    # Strip the filename (last component)
    dir_parts = parts[:-1]
    if not dir_parts:
        return None

    if mode == "use_root":
        return "/".join(dir_parts)
    elif mode == "skip_root":
        if len(dir_parts) <= 1:
            return None
        return "/".join(dir_parts[1:])

    return "/".join(dir_parts)

def derive_item_suggested_album_path(
    item: dict,
    meta: dict,
    enabled: bool = True,
    root_mode: str = "use_root",
) -> Optional[str]:
    """Derive the effective suggested album path for a staged item given session meta and folder mapping settings."""
    if not enabled:
        return None

    if item.get("folder_album_removed", False):
        return None

    if item.get("folder_album_custom_path"):
        return item["folder_album_custom_path"]

    rel_path = item.get("relative_path")
    if not rel_path:
        return None

    base_path = apply_folder_mapping_to_path(rel_path, mode=root_mode)
    if not base_path:
        return None

    raw_segments = [s.strip() for s in base_path.replace("\\", "/").strip("/").split("/") if s.strip()]
    if not raw_segments:
        return None

    removed_paths = set(p.lower() for p in meta.get("removed_album_paths", []))
    album_renames = meta.get("album_renames", {})
    album_path_renames = meta.get("album_path_renames", {})

    # Check if any raw segment prefix was removed
    for i in range(1, len(raw_segments) + 1):
        raw_prefix = "/".join(raw_segments[:i]).lower()
        if raw_prefix in removed_paths:
            return None

    # Apply renames
    renamed_segments = []
    for i, seg in enumerate(raw_segments):
        raw_prefix = "/".join(raw_segments[: i + 1]).lower()
        new_name = album_path_renames.get(raw_prefix) or album_renames.get(seg.lower()) or seg
        renamed_segments.append(new_name)

    # Check if any renamed segment prefix was removed
    for i in range(1, len(renamed_segments) + 1):
        renamed_prefix = "/".join(renamed_segments[:i]).lower()
        if renamed_prefix in removed_paths:
            return None

    return "/".join(renamed_segments)

def build_pending_album_tree(items: dict, db: Session) -> List[Dict[str, Any]]:
    """Scans all items in the session and returns a structured list of pending album entities."""
    nodes_map: Dict[str, Dict[str, Any]] = {}

    for item_id, item in items.items():
        if item.get("is_duplicate", False):
            continue

        suggested_path = item.get("suggested_album_path")
        if not suggested_path:
            continue

        normalized = suggested_path.replace("\\", "/").strip().strip("/")
        if not normalized:
            continue

        segments = [s.strip() for s in normalized.split("/") if s.strip()]
        if not segments:
            continue

        leaf_path = "/".join(segments)

        for idx in range(len(segments)):
            path_key = "/".join(segments[: idx + 1])
            parent_path = "/".join(segments[:idx]) if idx > 0 else None
            seg_name = segments[idx]

            if path_key not in nodes_map:
                nodes_map[path_key] = {
                    "path": path_key,
                    "name": seg_name,
                    "parent_path": parent_path,
                    "depth": idx,
                    "existing_id": None,
                    "used_by": set(),
                }

            if path_key == leaf_path:
                nodes_map[path_key]["used_by"].add(item_id)

    if not nodes_map:
        return []

    # Resolve existing IDs for all path keys
    resolved_paths_cache: Dict[str, List[Dict[str, Any]]] = {}
    for path_key in nodes_map.keys():
        if path_key not in resolved_paths_cache:
            resolved_paths_cache[path_key] = resolve_album_path(db, path_key)

    # Populate resolved existing_id and canonical name
    for path_key, node in nodes_map.items():
        resolved_segs = resolved_paths_cache.get(path_key, [])
        if resolved_segs:
            last_seg = resolved_segs[-1]
            node["existing_id"] = last_seg.get("existing_id")
            node["name"] = last_seg.get("name", node["name"])

    # Determine child relationships
    parent_to_children: Dict[str, List[str]] = {}
    for path_key, node in nodes_map.items():
        parent = node["parent_path"]
        if parent:
            parent_to_children.setdefault(parent, []).append(path_key)

    results: List[Dict[str, Any]] = []
    # Sort by depth first, then by path
    sorted_keys = sorted(nodes_map.keys(), key=lambda k: (nodes_map[k]["depth"], k.lower()))

    for path_key in sorted_keys:
        node = nodes_map[path_key]

        # Exclude albums that already exist in the database
        if node["existing_id"] is not None:
            continue

        used_by_list = sorted(list(node["used_by"]))
        has_children = len(parent_to_children.get(path_key, [])) > 0
        is_leaf = not has_children

        # Single item warning if only 1 item total and is a leaf
        single_item_warning = (len(used_by_list) == 1 and is_leaf)

        results.append({
            "path": node["path"],
            "name": node["name"],
            "parent_path": node["parent_path"],
            "depth": node["depth"],
            "existing_id": node["existing_id"],
            "used_by": used_by_list,
            "item_count": len(used_by_list),
            "single_item_warning": single_item_warning,
        })

    return results
