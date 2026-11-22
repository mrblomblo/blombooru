import shutil
from pathlib import Path
from typing import (
    Dict,
    List,
    Optional,
    Union,
)
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ...auth import require_admin_mode
from ...database import get_db
from ...enums import RatingEnum, TagCategoryEnum
from ...models import User
from ...schemas import ProposedTag, UploadSessionItemUpdate
from ...utils.album_path_resolver import resolve_album_path
from ...utils.media_relations import normalize_child_ids, staged_relation_problem
from ...utils.tag_utils import get_escalated_rating, get_newly_added_tags
from ...utils.thumbnail_generator import THUMBNAIL_EXT
from ..media import preview_or_create_tags
from .session_store import (
    _get_session_dir,
    _get_session_lock,
    _get_session_pending_tags_map,
    _load_session_meta,
    _save_session_meta,
    _session_locks,
)

router = APIRouter()

class BulkUpdateRequest(BaseModel):
    item_ids: List[str]
    rating: Optional[RatingEnum] = None
    source: Optional[str] = None
    description: Optional[str] = None
    album_ids: Optional[List[int]] = None
    add_album_ids: Optional[List[int]] = None
    remove_album_ids: Optional[List[int]] = None
    suggested_album_path: Optional[str] = None
    add_tags: Optional[List[Union[str, ProposedTag]]] = None
    remove_tag_names: Optional[List[str]] = None
    custom_date: Optional[str] = None

@router.patch("/sessions/{session_id}/items/{item_id}")
async def update_staged_item(
    session_id: str,
    item_id: str,
    update: UploadSessionItemUpdate,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db),
):
    """Update staged item properties (tags, rating, source, description, albums)."""
    async with _get_session_lock(session_id):
        session_dir = _get_session_dir(session_id)
        meta = _load_session_meta(session_dir)
        items = meta.get("items", {})
        item = items.get(item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

        fields_set = update.model_fields_set if hasattr(update, "model_fields_set") else getattr(update, "__fields_set__", set())
        if update.rating is not None:
            item["rating"] = update.rating.value
        if update.source is not None:
            item["source"] = update.source
        if update.description is not None:
            item["description"] = update.description
        if update.album_ids is not None:
            item["album_ids"] = update.album_ids
        if "suggested_album_path" in fields_set:
            if update.suggested_album_path is None or update.suggested_album_path == "":
                item["folder_album_removed"] = True
                item["folder_album_custom_path"] = None
                item["suggested_album_path"] = None
                item["suggested_album_segments"] = None
            else:
                item["folder_album_removed"] = False
                item["folder_album_custom_path"] = update.suggested_album_path
                item["suggested_album_path"] = update.suggested_album_path
                item["suggested_album_segments"] = resolve_album_path(db, update.suggested_album_path)

        if "parent_media_id" in fields_set or "child_media_ids" in fields_set or "parent_item_id" in fields_set:
            new_parent = update.parent_media_id if "parent_media_id" in fields_set else item.get("parent_media_id")
            new_parent_item = update.parent_item_id if "parent_item_id" in fields_set else item.get("parent_item_id")
            new_children = (
                normalize_child_ids(update.child_media_ids) if "child_media_ids" in fields_set
                else item.get("child_media_ids", [])
            )
            problem = staged_relation_problem(db, items, item_id, new_parent, new_children, new_parent_item)
            if problem:
                raise HTTPException(status_code=problem[0], detail=problem[1])
            item["parent_media_id"] = new_parent or None
            item["parent_item_id"] = new_parent_item or None
            item["child_media_ids"] = new_children

        if "custom_date" in fields_set:
            if update.custom_date is not None and str(update.custom_date).strip() != "":
                from ...utils.date_extractor import parse_explicit_custom_date
                parsed_dt = parse_explicit_custom_date(update.custom_date)
                if parsed_dt is None:
                    raise HTTPException(status_code=422, detail="Invalid custom_date format")
                item["custom_date"] = parsed_dt.isoformat()
                item["custom_date_origin"] = "explicit"
            else:
                auto_date = item.get("custom_date_auto")
                auto_origin = item.get("custom_date_auto_origin")
                if auto_date:
                    item["custom_date"] = auto_date
                    item["custom_date_origin"] = auto_origin or "default"
                else:
                    from ...utils.date_extractor import resolve_custom_date
                    raw_path = (session_dir / "raw" / item.get("staged_filename")) if item.get("staged_filename") else None
                    if not raw_path or not raw_path.exists():
                        source_p = item.get("source_path")
                        raw_path = Path(source_p) if source_p and Path(source_p).exists() else None
                    resolved_dt, date_origin = resolve_custom_date(file_path=raw_path)
                    item["custom_date"] = resolved_dt.isoformat()
                    item["custom_date_origin"] = date_origin

    if update.tags is not None:
        previous_staged_tags = list(item.get("tags", []))
        other_items = {k: v for k, v in meta.get("items", {}).items() if k != item_id}
        session_pending_map = _get_session_pending_tags_map(other_items)

        pre_implied_map: Dict[str, List[List[str]]] = {
            t["name"].strip().lower(): (t.get("implied_by") or [])
            for t in previous_staged_tags
            if t.get("name") and t.get("implied")
        }
        for t in update.tags:
            if getattr(t, "implied", False):
                t_lower = t.name.strip().lower()
                existing_grps = pre_implied_map.setdefault(t_lower, [])
                for grp in (getattr(t, "implied_by", None) or []):
                    if grp not in existing_grps:
                        existing_grps.append(grp)

        prev_tag_names = {t["name"].strip().lower() for t in previous_staged_tags if t.get("name")}
        newly_added_names = {
            t.name.strip().lower()
            for t in update.tags
            if t.name and t.name.strip().lower() not in prev_tag_names
        }
        seed_triggers = None if not prev_tag_names else newly_added_names

        # Build category hints from user assigned tag categories
        hints = {t.name.lower(): t.category.value for t in update.tags}
        names = [t.name for t in update.tags]
        proposed = preview_or_create_tags(
            db,
            names,
            category_hints=hints,
            expand=True,
            dry_run=True,
            pre_implied_map=pre_implied_map,
            seed_trigger_names=seed_triggers,
        )
        # Preserve user_assigned flag if explicitly passed
        user_assigned_set = {t.name.lower() for t in update.tags if getattr(t, "user_assigned", False)}
        result_tags = []
        for pt in proposed:
            dump = pt.model_dump() if hasattr(pt, "model_dump") else dict(pt)
            t_name = dump["name"].lower()
            if t_name in user_assigned_set:
                dump["user_assigned"] = True
                if t_name in hints:
                    dump["category"] = hints[t_name]
            elif dump.get("is_new", False) and t_name in session_pending_map:
                dump["category"] = session_pending_map[t_name]["category"]
                if "rating" in session_pending_map[t_name]:
                    dump["rating"] = session_pending_map[t_name]["rating"]
                if session_pending_map[t_name].get("user_assigned", False):
                    dump["user_assigned"] = True
            result_tags.append(dump)
        item["tags"] = result_tags
        item["tags_reviewed"] = True
        # Only tags added by this update escalate, and never over a rating the
        # same request explicitly set.
        if update.rating is None:
            current_r = RatingEnum.normalize(item.get("rating")) or RatingEnum.safe
            escalated = get_escalated_rating(current_r, get_newly_added_tags(previous_staged_tags, result_tags))
            if escalated and escalated != current_r:
                item["rating"] = escalated.value

    meta["items"][item_id] = item
    _save_session_meta(session_dir, meta)

    return item

@router.post("/sessions/{session_id}/items/bulk-update")
async def bulk_update_staged_items(
    session_id: str,
    req: BulkUpdateRequest,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db),
):
    """Apply updates to multiple staged items at once."""
    async with _get_session_lock(session_id):
        session_dir = _get_session_dir(session_id)
        meta = _load_session_meta(session_dir)
        items = meta.get("items", {})

        updated_items = []
        target_ids = set(req.item_ids)
        bulk_fields_set = req.model_fields_set if hasattr(req, "model_fields_set") else getattr(req, "__fields_set__", set())

        parsed_bulk_custom_date = None
        has_custom_date_update = "custom_date" in bulk_fields_set
        if has_custom_date_update:
            if req.custom_date is not None and str(req.custom_date).strip() != "":
                from ...utils.date_extractor import parse_explicit_custom_date
                parsed_bulk_custom_date = parse_explicit_custom_date(req.custom_date)
                if parsed_bulk_custom_date is None:
                    raise HTTPException(status_code=422, detail="Invalid custom_date format")

        for item_id, item in items.items():
            if item_id not in target_ids:
                continue

            if has_custom_date_update:
                if parsed_bulk_custom_date is not None:
                    item["custom_date"] = parsed_bulk_custom_date.isoformat()
                    item["custom_date_origin"] = "explicit"
                else:
                    auto_date = item.get("custom_date_auto")
                    auto_origin = item.get("custom_date_auto_origin")
                    if auto_date:
                        item["custom_date"] = auto_date
                        item["custom_date_origin"] = auto_origin or "default"
                    else:
                        from ...utils.date_extractor import resolve_custom_date
                        raw_path = (session_dir / "raw" / item.get("staged_filename")) if item.get("staged_filename") else None
                        if not raw_path or not raw_path.exists():
                            source_p = item.get("source_path")
                            raw_path = Path(source_p) if source_p and Path(source_p).exists() else None
                        resolved_dt, date_origin = resolve_custom_date(file_path=raw_path)
                        item["custom_date"] = resolved_dt.isoformat()
                        item["custom_date_origin"] = date_origin

            if req.rating is not None:
                item["rating"] = req.rating.value
            if req.source is not None:
                item["source"] = req.source
            if req.description is not None:
                item["description"] = req.description
            if req.album_ids is not None:
                item["album_ids"] = req.album_ids
            if req.add_album_ids is not None:
                cur_aids = set(item.get("album_ids", []))
                cur_aids.update(req.add_album_ids)
                item["album_ids"] = list(cur_aids)
            if req.remove_album_ids is not None:
                cur_aids = set(item.get("album_ids", []))
                cur_aids.difference_update(req.remove_album_ids)
                item["album_ids"] = list(cur_aids)
            if "suggested_album_path" in bulk_fields_set:
                if req.suggested_album_path is None or req.suggested_album_path == "":
                    item["folder_album_removed"] = True
                    item["folder_album_custom_path"] = None
                    item["suggested_album_path"] = None
                    item["suggested_album_segments"] = None
                else:
                    item["folder_album_removed"] = False
                    item["folder_album_custom_path"] = req.suggested_album_path
                    item["suggested_album_path"] = req.suggested_album_path
                    item["suggested_album_segments"] = resolve_album_path(db, req.suggested_album_path)

            # Tags update
            current_tags_dict = {t["name"].lower(): t for t in item.get("tags", []) if t.get("name")}
            previous_staged_tags = list(current_tags_dict.values())

            if req.remove_tag_names:
                remove_set = {n.strip().lower() for n in req.remove_tag_names}
                current_tags_dict = {k: v for k, v in current_tags_dict.items() if k not in remove_set}

            user_assigned_map: Dict[str, str] = {}
            if req.add_tags:
                for t in req.add_tags:
                    if isinstance(t, str):
                        t_name = t.strip().lower()
                        if t_name and t_name not in current_tags_dict:
                            current_tags_dict[t_name] = {"name": t_name, "category": "general", "rating": "none", "is_new": True, "user_assigned": False}
                    else:
                        t_name = t.name.strip().lower()
                        if t_name:
                            is_user_assigned = getattr(t, "user_assigned", False) or t.category != TagCategoryEnum.general
                            current_tags_dict[t_name] = {
                                "name": t_name,
                                "category": t.category.value,
                                "rating": getattr(t, "rating", "none") or "none",
                                "is_new": t.is_new,
                                "user_assigned": is_user_assigned,
                            }
                            if is_user_assigned:
                                user_assigned_map[t_name] = t.category.value

            # Re-evaluate with preview_or_create_tags
            names = list(current_tags_dict.keys())
            hints = {k: v["category"] for k, v in current_tags_dict.items() if v.get("category")}
            hints.update(user_assigned_map)

            pre_implied_map: Dict[str, List[List[str]]] = {
                k: (v.get("implied_by") or [])
                for k, v in current_tags_dict.items()
                if v.get("implied")
            }
            prev_tag_names = {t["name"].strip().lower() for t in previous_staged_tags if t.get("name")}
            newly_added_names = {k for k in names if k not in prev_tag_names}
            seed_triggers = None if not prev_tag_names else newly_added_names

            other_items = {k: v for k, v in items.items() if k != item_id}
            session_pending_map = _get_session_pending_tags_map(other_items)

            proposed = preview_or_create_tags(
                db,
                names,
                category_hints=hints,
                expand=True,
                dry_run=True,
                pre_implied_map=pre_implied_map,
                seed_trigger_names=seed_triggers,
            )
            resolved_tags = []
            for pt in proposed:
                pt_dict = pt.model_dump() if hasattr(pt, "model_dump") else dict(pt)
                t_name = pt.name.lower()
                # Preserve user_assigned flag if set
                orig = current_tags_dict.get(t_name)
                if orig and orig.get("user_assigned", False):
                    pt_dict["user_assigned"] = True
                elif pt_dict.get("is_new", False) and t_name in session_pending_map:
                    pt_dict["category"] = session_pending_map[t_name]["category"]
                    if "rating" in session_pending_map[t_name]:
                        pt_dict["rating"] = session_pending_map[t_name]["rating"]
                    if session_pending_map[t_name].get("user_assigned", False):
                        pt_dict["user_assigned"] = True
                resolved_tags.append(pt_dict)

            item["tags"] = resolved_tags
            if req.add_tags or req.remove_tag_names:
                item["tags_reviewed"] = True
            # Only tags added by this update escalate, and never over a rating the
            # same request explicitly set.
            if req.rating is None:
                current_r = RatingEnum.normalize(item.get("rating")) or RatingEnum.safe
                escalated = get_escalated_rating(current_r, get_newly_added_tags(previous_staged_tags, resolved_tags))
                if escalated and escalated != current_r:
                    item["rating"] = escalated.value

            items[item_id] = item
            updated_items.append(item)

        _save_session_meta(session_dir, meta)
        return {"updated_count": len(updated_items), "items": updated_items}

@router.delete("/sessions/{session_id}/items/{item_id}")
async def delete_staged_item(
    session_id: str,
    item_id: str,
    current_user: User = Depends(require_admin_mode),
):
    """Delete a single staged item from the session."""
    async with _get_session_lock(session_id):
        session_dir = _get_session_dir(session_id)
        meta = _load_session_meta(session_dir)
        items = meta.get("items", {})

        if item_id not in items:
            raise HTTPException(status_code=404, detail="Item not found in upload session")

        staged_filename = items[item_id].get("staged_filename")
        if staged_filename:
            (session_dir / "raw" / staged_filename).unlink(missing_ok=True)
        (session_dir / "thumbs" / f"{item_id}{THUMBNAIL_EXT}").unlink(missing_ok=True)

        del items[item_id]
        for other in items.values():
            if other.get("parent_item_id") == item_id:
                other["parent_item_id"] = None
        if len(items) == 0:
            shutil.rmtree(session_dir, ignore_errors=True)
            _session_locks.pop(Path(session_id).name, None)
            return {"status": "session_deleted", "item_id": item_id, "session_empty": True}

        _save_session_meta(session_dir, meta)
        return {"status": "deleted", "item_id": item_id, "session_empty": False}
