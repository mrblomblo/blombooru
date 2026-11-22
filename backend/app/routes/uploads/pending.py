from typing import Dict
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ...auth import require_admin_mode
from ...database import get_db
from ...models import Album, Tag, User
from ...schemas import (
    FolderMappingRequest,
    PendingAlbumEntity,
    PendingAlbumUpdate,
    PendingEntitiesResponse,
    PendingTagEntity,
    PendingTagUpdate,
)
from ...utils.album_path_resolver import build_pending_album_tree, derive_item_suggested_album_path, resolve_album_path
from .session_store import (
    _get_session_dir,
    _get_session_lock,
    _load_session_meta,
    _save_session_meta,
)

router = APIRouter()

@router.get("/sessions/{session_id}/pending")
async def get_pending_entities(
    session_id: str,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db),
):
    """Aggregate and deduplicate all pending new tags and albums across the session."""
    session_dir = _get_session_dir(session_id)
    meta = _load_session_meta(session_dir)
    items = meta.get("items", {})

    pending_tags_map: Dict[str, dict] = {}

    for item_id, item in items.items():
        if item.get("is_duplicate", False):
            continue

        for t in item.get("tags", []):
            # Include all new tags, even if they have been assigned a category manually
            if t.get("is_new", False):
                name = t.get("name", "").strip().lower()
                if not name:
                    continue
                if name not in pending_tags_map:
                    pending_tags_map[name] = {
                        "name": name,
                        "category": t.get("category", "general"),
                        "rating": t.get("rating", "none"),
                        "used_by": [],
                        "merge_into": t.get("merge_into"),
                        "user_assigned": t.get("user_assigned", False),
                    }
                else:
                    if t.get("user_assigned", False):
                        pending_tags_map[name]["user_assigned"] = True
                if item_id not in pending_tags_map[name]["used_by"]:
                    pending_tags_map[name]["used_by"].append(item_id)

    pending_tags = [PendingTagEntity(**v) for v in pending_tags_map.values()]
    pending_albums_list = build_pending_album_tree(items, db)
    pending_albums = [PendingAlbumEntity(**v) for v in pending_albums_list]

    return PendingEntitiesResponse(
        pending_tags=pending_tags,
        pending_albums=pending_albums,
    )

@router.patch("/sessions/{session_id}/pending/tags/{tag_name}")
async def update_pending_tag(
    session_id: str,
    tag_name: str,
    update: PendingTagUpdate,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db),
):
    """Globally update a pending tag (rename, change category, merge into existing, or remove) across all referencing items."""
    async with _get_session_lock(session_id):
        session_dir = _get_session_dir(session_id)
        meta = _load_session_meta(session_dir)
        items = meta.get("items", {})

        target_name = tag_name.strip().lower()
        affected_count = 0

        for item_id, item in items.items():
            tags = item.get("tags", [])
            new_tags = []
            modified = False

            for t in tags:
                current_name = t.get("name", "").strip().lower()
                if current_name == target_name:
                    modified = True
                    if update.remove:
                        continue  # Remove tag from this item

                    if update.merge_into:
                        merge_target = update.merge_into.strip().lower()
                        # Check if merge_target exists in DB
                        existing_db_tag = db.query(Tag).filter(Tag.name == merge_target).first()
                        t["name"] = merge_target
                        t["is_new"] = existing_db_tag is None
                        t["category"] = existing_db_tag.category.value if existing_db_tag else t.get("category", "general")
                        t["rating"] = existing_db_tag.rating.value if existing_db_tag and existing_db_tag.rating else t.get("rating", "none")
                        t["user_assigned"] = True
                        new_tags.append(t)
                    else:
                        if update.new_name:
                            t["name"] = update.new_name.strip().lower()
                        if update.category:
                            t["category"] = update.category.value
                        if update.rating is not None:
                            t["rating"] = update.rating
                        t["user_assigned"] = True
                        new_tags.append(t)
                else:
                    new_tags.append(t)

            if modified:
                replacement_name = None
                if update.merge_into:
                    replacement_name = update.merge_into.strip().lower()
                elif update.new_name:
                    replacement_name = update.new_name.strip().lower()

                if replacement_name:
                    for t in new_tags:
                        if t.get("implied") and isinstance(t.get("implied_by"), list):
                            updated_grps = []
                            for grp in t["implied_by"]:
                                if isinstance(grp, list):
                                    new_grp = sorted({
                                        replacement_name if str(x).strip().lower() == target_name else str(x).strip().lower()
                                        for x in grp
                                        if x and str(x).strip()
                                    })
                                    if new_grp and new_grp not in updated_grps:
                                        updated_grps.append(new_grp)
                            t["implied_by"] = updated_grps

                # Deduplicate item's tags by name
                seen = set()
                deduped = []
                for t in new_tags:
                    n = t["name"].lower()
                    if n not in seen:
                        seen.add(n)
                        deduped.append(t)
                item["tags"] = deduped
                items[item_id] = item
                affected_count += 1

        _save_session_meta(session_dir, meta)
        return {"status": "updated", "affected_items": affected_count}

@router.patch("/sessions/{session_id}/pending/albums")
async def update_pending_album(
    session_id: str,
    update: PendingAlbumUpdate,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db),
):
    """Globally update a pending album path across all referencing items in the session."""
    async with _get_session_lock(session_id):
        session_dir = _get_session_dir(session_id)
        meta = _load_session_meta(session_dir)
        items = meta.get("items", {})

        target_path = update.path.replace("\\", "/").strip().strip("/")
        if not target_path:
            raise HTTPException(status_code=400, detail="Invalid album path")

        target_segments = [s.strip() for s in target_path.split("/") if s.strip()]
        affected_count = 0

        if update.remove:
            removed_paths = meta.setdefault("removed_album_paths", [])
            if target_path.lower() not in removed_paths:
                removed_paths.append(target_path.lower())

        elif update.new_name or update.merge_into_id is not None:
            new_name = None
            if update.new_name:
                new_name = update.new_name.strip()
            elif update.merge_into_id is not None:
                existing_alb = db.query(Album).filter(Album.id == update.merge_into_id).first()
                if existing_alb:
                    new_name = existing_alb.name

            if new_name:
                old_seg = target_segments[-1]
                meta.setdefault("album_renames", {})[old_seg.lower()] = new_name
                for k, v in list(meta.get("album_renames", {}).items()):
                    if v.lower() == old_seg.lower():
                        meta["album_renames"][k] = new_name
                meta.setdefault("album_path_renames", {})[target_path.lower()] = new_name

        for item_id, item in items.items():
            suggested_path = item.get("suggested_album_path")
            if not suggested_path:
                continue

            item_path = suggested_path.replace("\\", "/").strip().strip("/")
            item_segments = [s.strip() for s in item_path.split("/") if s.strip()]

            if len(item_segments) >= len(target_segments):
                matches = all(item_segments[i].lower() == target_segments[i].lower() for i in range(len(target_segments)))
                if matches:
                    if update.remove:
                        item["folder_album_removed"] = True
                        item["folder_album_custom_path"] = None
                        item["suggested_album_path"] = None
                        item["suggested_album_segments"] = None
                        affected_count += 1
                    elif update.promote_to_parent:
                        new_segs = item_segments[: len(target_segments) - 1] + item_segments[len(target_segments) :]
                        new_path = "/".join(new_segs) if new_segs else None
                        item["suggested_album_path"] = new_path
                        item["folder_album_custom_path"] = new_path
                        item["suggested_album_segments"] = resolve_album_path(db, new_path) if new_path else None
                        affected_count += 1
                    elif update.new_name:
                        new_name = update.new_name.strip()
                        if new_name:
                            item_segments[len(target_segments) - 1] = new_name
                            new_path = "/".join(item_segments)
                            item["suggested_album_path"] = new_path
                            if item.get("folder_album_custom_path"):
                                item["folder_album_custom_path"] = new_path
                            item["suggested_album_segments"] = resolve_album_path(db, new_path)
                            affected_count += 1
                    elif update.merge_into_id is not None:
                        existing_alb = db.query(Album).filter(Album.id == update.merge_into_id).first()
                        if existing_alb:
                            item_segments[len(target_segments) - 1] = existing_alb.name
                            new_path = "/".join(item_segments)
                            item["suggested_album_path"] = new_path
                            if item.get("folder_album_custom_path"):
                                item["folder_album_custom_path"] = new_path
                            item["suggested_album_segments"] = resolve_album_path(db, new_path)
                            affected_count += 1

        _save_session_meta(session_dir, meta)
        return {"status": "updated", "affected_items": affected_count}

@router.post("/sessions/{session_id}/folder-mapping")
async def update_folder_mapping(
    session_id: str,
    req: FolderMappingRequest,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db),
):
    """Recompute folder to album mappings for all staged items based on their stored relative_path while preserving user customizations."""
    async with _get_session_lock(session_id):
        session_dir = _get_session_dir(session_id)
        meta = _load_session_meta(session_dir)
        items = meta.get("items", {})

        meta["folder_mapping_enabled"] = req.enabled
        meta["folder_mapping_root_mode"] = req.root_mode

        affected_count = 0
        for item_id, item in items.items():
            new_path = derive_item_suggested_album_path(
                item=item,
                meta=meta,
                enabled=req.enabled,
                root_mode=req.root_mode,
            )
            item["suggested_album_path"] = new_path
            item["suggested_album_segments"] = resolve_album_path(db, new_path) if new_path else None
            affected_count += 1

        _save_session_meta(session_dir, meta)
        return {"status": "success", "affected_items": affected_count}
