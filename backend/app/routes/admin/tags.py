import asyncio
import csv
import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import case, desc, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from ...auth import require_admin_mode
from ...config import settings
from ...utils.request_helpers import safe_error_detail
from ...database import get_db
from ... import database
from ...enums import RatingEnum, TagCategoryEnum
from ...models import Media, Tag, TagAlias, TagImplication, User
from ...schemas import BulkRatingUpdateRequest, TagResponse
from ...services.maintenance_jobs import maintenance_jobs
from ...utils.cache import invalidate_media_cache, invalidate_tag_cache
from ...utils.logger import logger
from ...utils.album_utils import handle_media_rating_changed
from ...utils.tag_utils import get_escalated_rating, normalize_tag_rating

router = APIRouter()

def import_tags_csv_logic(csv_text: str, db: Session):
    """
    Core logic for importing tags from CSV content.
    Returns a dict with import statistics.
    """
    category_map = {
        0: 'general',
        1: 'artist',
        3: 'copyright',
        4: 'character',
        5: 'meta'
    }
    
    MAX_TAG_LENGTH = 255
    MAX_ALIAS_LENGTH = 255
    
    tags_created = 0
    aliases_created = 0
    tags_updated = 0
    errors = []
    skipped_long_tags = 0
    skipped_long_aliases = 0
    
    BATCH_SIZE = 1000
    
    # PASS 1: Import tags only
    logger.info("Pass 1: Importing tags...")
    csv_reader = csv.reader(io.StringIO(csv_text))
    
    tag_data = []
    tags_to_create = []
    rows_processed = 0
    existing_tags = {tag.name: tag for tag in db.query(Tag).all()}
    
    for row_num, row in enumerate(csv_reader, 1):
        try:
            if len(row) < 2:
                continue
            
            tag_name = row[0].strip().lower()
            if not tag_name:
                continue
            
            if len(tag_name) > MAX_TAG_LENGTH:
                skipped_long_tags += 1
                errors.append({"key": "notifications.admin.error_tag_too_long", "row": row_num, "tag": tag_name[:50], "length": len(tag_name)})
                continue
            
            try:
                category_num = int(row[1])
            except (ValueError, IndexError):
                errors.append({"key": "notifications.admin.error_invalid_category", "row": row_num})
                continue
            
            aliases_str = row[3] if len(row) > 3 else ""
            category = category_map.get(category_num, 'general')
            
            tag_data.append((tag_name, category, aliases_str))
            
            if tag_name in existing_tags:
                tag = existing_tags[tag_name]
                if tag.category != category:
                    tag.category = category
                    tags_updated += 1
            else:
                tags_to_create.append({
                    'name': tag_name,
                    'category': category,
                    'post_count': 0
                })
                tags_created += 1
            
            rows_processed += 1
            
            if rows_processed % BATCH_SIZE == 0:
                try:
                    if tags_to_create:
                        db.bulk_insert_mappings(Tag, tags_to_create)
                        tags_to_create = []
                    
                    db.commit()
                    logger.debug(f"Pass 1: Processed {rows_processed} tags...")
                    db.expire_all()
                except Exception as e:
                    db.rollback()
                    errors.append({"key": "notifications.admin.error_batch_error", "row": row_num, "error": str(e)})
                    tags_to_create = []
                    existing_tags = {tag.name: tag for tag in db.query(Tag).all()}
        
        except Exception as e:
            errors.append({"key": "notifications.admin.error_row_error", "row": row_num, "error": str(e)})
            continue
    
    # Final commit for pass 1
    try:
        if tags_to_create:
            db.bulk_insert_mappings(Tag, tags_to_create)
        db.commit()
    except Exception as e:
        db.rollback()
        errors.append({"key": "notifications.admin.error_final_batch_pass1", "error": str(e)})
    
    logger.info(f"Pass 1 complete: {tags_created} tags created, {tags_updated} updated, {skipped_long_tags} skipped")
    
    existing_tags = None
    tags_to_create = None
    db.expire_all()
    
    # PASS 2: Import aliases
    logger.info("Pass 2: Importing aliases...")
    logger.debug("Building tag mapping...")
    tag_map = {}
    offset = 0
    chunk_size = 10000
    
    while True:
        tags_chunk = db.query(Tag.name, Tag.id).limit(chunk_size).offset(offset).all()
        if not tags_chunk:
            break
        
        for name, tag_id in tags_chunk:
            tag_map[name] = tag_id
        
        offset += chunk_size
        if offset % 50000 == 0:
            logger.debug(f"Loaded {offset} tag mappings...")
    
    logger.info(f"Tag mapping complete: {len(tag_map)} tags")
    
    existing_aliases = {alias.alias_name for alias in db.query(TagAlias.alias_name).all()}
    aliases_to_create = []
    rows_processed = 0
    
    for tag_name, category, aliases_str in tag_data:
        try:
            if not aliases_str or tag_name not in tag_map:
                continue
            
            tag_id = tag_map[tag_name]
            
            alias_names = set()
            for a in aliases_str.split(','):
                alias = a.strip().lower()
                if not alias or alias == tag_name:
                    continue
                
                if len(alias) > MAX_ALIAS_LENGTH:
                    skipped_long_aliases += 1
                    continue
                
                alias_names.add(alias)
            
            for alias_name in alias_names:
                if alias_name not in existing_aliases and alias_name not in tag_map:
                    aliases_to_create.append({
                        'alias_name': alias_name,
                        'target_tag_id': tag_id
                    })
                    existing_aliases.add(alias_name)
                    aliases_created += 1
            
            rows_processed += 1
            
            if rows_processed % BATCH_SIZE == 0:
                try:
                    if aliases_to_create:
                        db.bulk_insert_mappings(TagAlias, aliases_to_create)
                        aliases_to_create = []
                    
                    db.commit()
                    logger.debug(f"Pass 2: Processed {rows_processed} tags, created {aliases_created} aliases...")
                    db.expire_all()
                except IntegrityError as e:
                    db.rollback()
                    errors.append({"key": "notifications.admin.error_alias_batch_integrity", "row": rows_processed, "error": str(e)})
                    aliases_to_create = []
                    existing_aliases = {alias.alias_name for alias in db.query(TagAlias.alias_name).all()}
                except Exception as e:
                    db.rollback()
                    errors.append({"key": "notifications.admin.error_alias_batch", "row": rows_processed, "error": str(e)})
                    aliases_to_create = []
                    existing_aliases = {alias.alias_name for alias in db.query(TagAlias.alias_name).all()}
        
        except Exception as e:
            errors.append({"key": "notifications.admin.error_pass2_tag", "tag": tag_name, "error": str(e)})
            continue
    
    # Final commit for pass 2
    try:
        if aliases_to_create:
            db.bulk_insert_mappings(TagAlias, aliases_to_create)
        db.commit()
    except Exception as e:
        db.rollback()
        errors.append({"key": "notifications.admin.error_final_batch_pass2", "error": str(e)})
    
    logger.info(f"Pass 2 complete: {aliases_created} aliases created, {skipped_long_aliases} skipped")
    
    invalidate_tag_cache()

    return {
        "message_key": "notifications.admin.tags_imported",
        "tags_created": tags_created,
        "tags_updated": tags_updated,
        "aliases_created": aliases_created,
        "rows_processed": len(tag_data),
        "skipped_long_tags": skipped_long_tags,
        "skipped_long_aliases": skipped_long_aliases,
        "errors": errors[:20] if errors else [],
        "total_errors": len(errors)
    }


@router.post("/import-tags-csv")
async def import_tags_csv(
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Import tags from CSV file (two-pass, non-streaming)"""
    
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
        
    try:
        contents = await file.read()
        csv_text = contents.decode('utf-8')
        
        result = import_tags_csv_logic(csv_text, db)
        return result
    
    except Exception as e:
        db.rollback()
        logger.error(f"Error during import: {str(e)}")
        raise HTTPException(status_code=400, detail=safe_error_detail("Error importing CSV", e))

@router.get("/tag-stats")
async def get_tag_stats(
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Get tag statistics"""
    total_tags = db.query(Tag).count()
    total_aliases = db.query(TagAlias).count()
    total_implications = db.query(TagImplication).count()
    
    return {
        "total_tags": total_tags,
        "total_aliases": total_aliases,
        "total_implications": total_implications,
    }

@router.get("/search-tags")
async def search_tags(
    q: str,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Search tags"""
    q_lower = q.strip().lower() if q else ""
    if not q_lower:
        return {"tags": []}

    priority = case(
        (func.lower(Tag.name) == q_lower, 1),
        (Tag.name.ilike(f"{q_lower}%"), 2),
        else_=3
    )

    tags = db.query(Tag).filter(
        Tag.name.ilike(f"%{q_lower}%")
    ).order_by(
        priority,
        desc(Tag.post_count),
        func.length(Tag.name),
        Tag.name
    ).limit(50).all()

    return {"tags": [TagResponse.model_validate(tag) for tag in tags]}

@router.delete("/clear-tags")
async def clear_all_tags(
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Clear all tags"""
    try:
        db.query(TagAlias).delete()
        db.query(Tag).delete()
        
        db.commit()
        invalidate_tag_cache()
        
        return {"message_key": "notifications.admin.tags_cleared"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=safe_error_detail("Error clearing tags", e))

@router.delete("/tags/{tag_id}")
async def delete_tag(
    tag_id: int,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Delete a single tag and its aliases"""
    try:
        tag = db.query(Tag).filter(Tag.id == tag_id).first()
        
        if not tag:
            raise HTTPException(status_code=404, detail="error_tag_not_found")
        
        tag_name = tag.name
        
        db.delete(tag)
        db.commit()
        invalidate_tag_cache()
        
        if settings.SHARED_TAGS_ENABLED:
            from ...database import get_shared_db, is_shared_db_available
            if is_shared_db_available():
                shared_db_gen = get_shared_db()
                shared_db = next(shared_db_gen, None)
                if shared_db:
                    try:
                        from ...services.shared_tags import SharedTagService
                        service = SharedTagService(db, shared_db)
                        service.delete_from_shared(tag_name)
                    finally:
                        try:
                            next(shared_db_gen, None)
                        except StopIteration:
                            pass
        
        return {"message_key": "notifications.admin.tag_deleted", "tag_name": tag_name}
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=safe_error_detail("Error deleting tag", e))

@router.get("/tags/{tag_id}")
async def get_tag(
    tag_id: int,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Get tag details including aliases"""
    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="error_tag_not_found")
    
    aliases = [a.alias_name for a in tag.aliases]

    return {
        "id": tag.id,
        "name": tag.name,
        "category": tag.category,
        "rating": tag.rating.value if tag.rating else "none",
        "post_count": tag.post_count,
        "aliases": aliases
    }

@router.put("/tags/{tag_id}")
async def update_tag(
    tag_id: int,
    data: dict,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Rename a tag, change its category, update its aliases, change its rating"""
    try:
        tag = db.query(Tag).filter(Tag.id == tag_id).first()
        if not tag:
            raise HTTPException(status_code=404, detail="error_tag_not_found")

        if "name" in data:
            new_name = (data.get("name") or "").strip().lower()
            if not new_name:
                raise HTTPException(status_code=400, detail="error_tag_name_empty")
        else:
            new_name = tag.name

        new_category = data.get("category", tag.category)

        old_name = tag.name

        # Only validate name conflict when the name is actually changing
        if new_name != old_name:
            conflict = db.query(Tag).filter(Tag.name == new_name).first()
            if conflict:
                raise HTTPException(status_code=409, detail="error_tag_name_conflict")

            alias_conflict = db.query(TagAlias).filter(TagAlias.alias_name == new_name).first()
            if alias_conflict:
                raise HTTPException(status_code=409, detail="error_tag_name_conflict")

            tag.name = new_name

        tag.category = new_category

        if "aliases" in data and isinstance(data["aliases"], list):
            # Normalize requested aliases
            cleaned_aliases = []
            seen = set()
            for alias_raw in data["aliases"]:
                alias = str(alias_raw).strip().lower().replace(" ", "_")
                if not alias:
                    continue
                if alias == new_name:
                    continue  # Alias cannot be tag's own name
                if alias in seen:
                    continue
                seen.add(alias)
                cleaned_aliases.append(alias)

            # Check conflicts for newly added aliases
            existing_alias_objs = db.query(TagAlias).filter(TagAlias.target_tag_id == tag.id).all()
            existing_alias_names = {a.alias_name for a in existing_alias_objs}

            for alias in cleaned_aliases:
                if alias not in existing_alias_names:
                    # Check if alias conflicts with ANY tag name
                    if db.query(Tag).filter(Tag.name == alias).first():
                        raise HTTPException(status_code=409, detail=f"Alias '{alias}' conflicts with an existing tag name")
                    # Check if alias conflicts with ANOTHER tag's alias
                    other_alias = db.query(TagAlias).filter(TagAlias.alias_name == alias, TagAlias.target_tag_id != tag.id).first()
                    if other_alias:
                        raise HTTPException(status_code=409, detail=f"Alias '{alias}' conflicts with an existing alias")

            # Remove aliases no longer present
            for a_obj in existing_alias_objs:
                if a_obj.alias_name not in seen:
                    db.delete(a_obj)

            # Add new aliases
            for alias in cleaned_aliases:
                if alias not in existing_alias_names:
                    db.add(TagAlias(alias_name=alias, target_tag_id=tag.id))

        if "rating" in data:
            tag.rating = normalize_tag_rating(data.get("rating"))

        db.commit()
        invalidate_tag_cache()

        updated_aliases = [a.alias_name for a in db.query(TagAlias).filter(TagAlias.target_tag_id == tag.id).all()]
        tag_rating = tag.rating.value if tag.rating else "none"
        return {"old_name": old_name, "tag_name": tag.name, "category": tag.category, "rating": tag_rating, "aliases": updated_aliases}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=safe_error_detail("Error updating tag", e))

@router.get("/check-alias")
async def check_alias(
    name: str,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Check if a name exists as an alias"""
    alias = db.query(TagAlias).filter(TagAlias.alias_name == name.lower()).first()
    return {"exists": alias is not None}

@router.post("/bulk-create-tags")
async def bulk_create_tags(
    data: dict,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Bulk create tags"""
    tags_to_create = data.get('tags', [])
    
    created = 0
    skipped = 0
    errors = []
    
    for tag_data in tags_to_create:
        try:
            tag_name = tag_data['name'].lower().strip()
            if not tag_name:
                continue

            category = tag_data.get('category', 'general')
            
            existing = db.query(Tag).filter(Tag.name == tag_name).first()
            if existing:
                skipped += 1
                continue
            
            alias = db.query(TagAlias).filter(TagAlias.alias_name == tag_name).first()
            if alias:
                skipped += 1
                continue
            
            tag = Tag(name=tag_name, category=category)
            db.add(tag)
            created += 1
            
        except Exception as e:
            errors.append({"key": "notifications.admin.error_creating_tag", "tag": tag_data.get('name'), "error": str(e)})
            
    try:
        db.commit()
        if created > 0:
            invalidate_tag_cache()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=safe_error_detail("Database error", e))
        
    return {
        "message_key": "notifications.admin.bulk_tag_creation_complete",
        "created": created,
        "skipped": skipped,
        "errors": errors
    }

class BulkCategoryUpdateRequest(BaseModel):
    tag_ids: list[int]
    category: TagCategoryEnum

@router.post("/tags/bulk-category")
async def bulk_update_tag_category(
    data: BulkCategoryUpdateRequest,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Bulk update tag category for selected tags."""
    if not data.tag_ids:
        return {"updated": 0}

    updated = db.query(Tag).filter(Tag.id.in_(data.tag_ids)).update(
        {Tag.category: data.category},
        synchronize_session=False
    )
    db.commit()
    invalidate_tag_cache()
    return {"updated": updated}

@router.post("/tags/bulk-rating")
async def bulk_update_tag_rating(
    data: BulkRatingUpdateRequest,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Bulk update tag rating for selected tags."""
    if not data.tag_ids:
        return {"updated": 0}

    rating_enum = normalize_tag_rating(data.rating)

    updated = db.query(Tag).filter(Tag.id.in_(data.tag_ids)).update(
        {Tag.rating: rating_enum},
        synchronize_session=False
    )
    db.commit()
    invalidate_tag_cache()
    return {"updated": updated}

def cleanup_aliased_tags_logic(db: Session):
    """
    Deletes any Tag record in blombooru_tags whose name exists as an alias_name in blombooru_tag_aliases.
    This prevents a tag from existing as both a tag and an alias simultaneously.
    """
    alias_names = [a[0] for a in db.query(TagAlias.alias_name).all()]
    if alias_names:
        tags_to_delete = db.query(Tag).filter(Tag.name.in_(alias_names)).all()
        if tags_to_delete:
            count = len(tags_to_delete)
            for t in tags_to_delete:
                db.delete(t)
            db.commit()
            invalidate_tag_cache()
            return count
    return 0

@router.post("/cleanup-aliased-tags")
async def cleanup_aliased_tags(
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Delete all Tag records whose names match an alias name in TagAlias."""
    count = cleanup_aliased_tags_logic(db)
    return {"deleted_count": count}

def _do_simulate_apply_aliases(progress_cb=None):
    local_db = database.SessionLocal()
    try:
        aliases = (
            local_db.query(TagAlias)
            .options(joinedload(TagAlias.target_tag))
            .all()
        )
        if not aliases:
            return []

        # alias tag name -> target tag name
        alias_map = {a.alias_name: a.target_tag.name for a in aliases if a.target_tag}
        if not alias_map:
            return []

        # Only fetch media that actually own at least one alias-named tag,
        # instead of loading the entire media table.
        media_items = (
            local_db.query(Media)
            .options(joinedload(Media.tags))
            .filter(Media.tags.any(Tag.name.in_(alias_map.keys())))
            .all()
        )

        total = len(media_items)
        if progress_cb:
            progress_cb(current=0, total=total, current_file=None)

        affected_media = []
        for idx, media in enumerate(media_items):
            if progress_cb:
                progress_cb(current=idx + 1, current_file=media.filename)

            original_tags = {t.name for t in media.tags}
            removed_tags = original_tags & alias_map.keys()
            added_tags = {
                alias_map[name] for name in removed_tags
            } - original_tags

            final_tags = (original_tags - removed_tags) | added_tags
            if final_tags != original_tags:
                affected_media.append({
                    "media_id": media.id,
                    "added_tags": list(added_tags),
                    "removed_tags": list(removed_tags),
                })

        return affected_media
    finally:
        local_db.close()

@router.post("/simulate-apply-aliases")
async def simulate_apply_aliases(
    background: bool = False,
    current_user: User = Depends(require_admin_mode),
):
    """Simulate applying all tag aliases to all media in the database."""
    if background:
        started, status = maintenance_jobs.start_job(
            "apply_aliases",
            lambda cb: {"affected_media": _do_simulate_apply_aliases(progress_cb=cb)},
        )
        return {"status": "started" if started else "already_running", "job": status}

    loop = asyncio.get_running_loop()
    affected_media = await loop.run_in_executor(None, _do_simulate_apply_aliases)
    return {"affected_media": affected_media}

def _do_simulate_apply_tag_ratings(progress_cb=None):
    local_db = database.SessionLocal()
    try:
        rated_tags_count = local_db.query(Tag.id).filter(Tag.rating.isnot(None)).count()
        if rated_tags_count == 0:
            return []

        media_items = (
            local_db.query(Media)
            .options(joinedload(Media.tags))
            .filter(Media.rating != RatingEnum.explicit)
            .filter(Media.tags.any(Tag.rating.isnot(None)))
            .all()
        )

        total = len(media_items)
        if progress_cb:
            progress_cb(current=0, total=total, current_file=None)

        affected_media = []
        for idx, media in enumerate(media_items):
            if progress_cb:
                progress_cb(current=idx + 1, current_file=media.filename)

            escalated = get_escalated_rating(media.rating, media.tags)
            if escalated and escalated != media.rating:
                affected_media.append({
                    "media_id": media.id,
                    "current_rating": media.rating.value if hasattr(media.rating, "value") else media.rating,
                    "new_rating": escalated.value if hasattr(escalated, "value") else escalated,
                })

        return affected_media
    finally:
        local_db.close()

@router.post("/simulate-apply-tag-ratings")
async def simulate_apply_tag_ratings(
    background: bool = False,
    current_user: User = Depends(require_admin_mode),
):
    """Simulate retroactively applying/escalating media ratings based on tag ratings."""
    if background:
        started, status = maintenance_jobs.start_job(
            "apply_tag_ratings",
            lambda cb: {"affected_media": _do_simulate_apply_tag_ratings(progress_cb=cb)},
        )
        return {"status": "started" if started else "already_running", "job": status}

    loop = asyncio.get_running_loop()
    affected_media = await loop.run_in_executor(None, _do_simulate_apply_tag_ratings)
    return {"affected_media": affected_media}


class MergeTagRequest(BaseModel):
    target_tag_name: str

@router.post("/tags/{tag_id}/merge-into")
async def merge_tag(
    tag_id: int,
    request_data: MergeTagRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_mode)
):
    """
    Merge a tag into another tag.
    1. Reassign all existing aliases of source tag to target tag.
    2. Make source tag name an alias of target tag.
    3. Replace source tag with target tag on all media.
    4. Delete source tag.
    """
    source_tag = db.query(Tag).filter(Tag.id == tag_id).first()
    if not source_tag:
        raise HTTPException(status_code=404, detail="Source tag not found")
        
    target_name = request_data.target_tag_name.lower().strip()
    if not target_name:
        raise HTTPException(status_code=400, detail="Target tag name cannot be empty")
        
    if source_tag.name == target_name:
        raise HTTPException(status_code=400, detail="Cannot merge tag into itself")
        
    target_tag = db.query(Tag).filter(Tag.name == target_name).first()
    if not target_tag:
        target_tag = Tag(name=target_name, category=source_tag.category)
        db.add(target_tag)
        db.flush()

    if target_tag.rating is None and source_tag.rating is not None:
        target_tag.rating = source_tag.rating
        
    # 1. Remove any alias that has target_name as its alias_name (e.g. if target_name was an alias of source_tag or another tag)
    db.query(TagAlias).filter(TagAlias.alias_name == target_name).delete(synchronize_session='fetch')

    # 2. Reassign existing aliases of source tag to target tag (excluding target_name and source_name)
    db.query(TagAlias).filter(
        TagAlias.target_tag_id == source_tag.id,
        TagAlias.alias_name != target_name,
        TagAlias.alias_name != source_tag.name
    ).update({
        TagAlias.target_tag_id: target_tag.id
    }, synchronize_session='fetch')
    
    # 3. Remove any existing alias that matches source_tag.name if it exists
    db.query(TagAlias).filter(TagAlias.alias_name == source_tag.name).delete(synchronize_session='fetch')
        
    # 4. Add source tag name as an alias for target tag
    db.add(TagAlias(alias_name=source_tag.name, target_tag_id=target_tag.id))
    
    # 5. Update media items and implication rules
    from sqlalchemy import and_
    from ...models import TagImplication, blombooru_media_tags

    source_id = source_tag.id
    source_name = source_tag.name
    target_id = target_tag.id

    # Replace source_tag with target_tag in any TagImplication rules
    implications_with_source = (
        db.query(TagImplication)
        .filter(
            (TagImplication.target_tags.any(Tag.id == source_id))
            | (TagImplication.implied_tags.any(Tag.id == source_id))
        )
        .all()
    )
    for imp in implications_with_source:
        if source_tag in imp.target_tags:
            imp.target_tags.remove(source_tag)
            if target_tag not in imp.target_tags and target_tag not in imp.implied_tags:
                imp.target_tags.append(target_tag)
        if source_tag in imp.implied_tags:
            imp.implied_tags.remove(source_tag)
            if target_tag not in imp.implied_tags and target_tag not in imp.target_tags:
                imp.implied_tags.append(target_tag)
        if not imp.target_tags and not imp.target_tag_patterns:
            db.delete(imp)
        elif not imp.implied_tags:
            db.delete(imp)

    source_implied_rows = db.query(
        blombooru_media_tags.c.media_id,
        blombooru_media_tags.c.implied,
        blombooru_media_tags.c.implied_by,
    ).filter(
        blombooru_media_tags.c.tag_id == source_id,
        blombooru_media_tags.c.implied.is_(True),
    ).all()
    source_implied_by_media = {
        m_id: (imp_by if isinstance(imp_by, list) else [])
        for m_id, _, imp_by in source_implied_rows
    }

    target_existing_rows = db.query(
        blombooru_media_tags.c.media_id,
        blombooru_media_tags.c.implied,
        blombooru_media_tags.c.implied_by,
    ).filter(
        blombooru_media_tags.c.tag_id == target_id,
    ).all()
    target_existing_by_media = {
        m_id: (bool(is_imp), imp_by if isinstance(imp_by, list) else [])
        for m_id, is_imp, imp_by in target_existing_rows
    }

    media_with_source = db.query(Media).filter(Media.tags.any(id=source_id)).all()
    rating_changed_media = []
    newly_linked_target_media_ids = []
    for media in media_with_source:
        if target_tag not in media.tags:
            media.tags.append(target_tag)
            newly_linked_target_media_ids.append(media.id)
            # The target tag is newly added to this media, so it may escalate its rating.
            escalated = get_escalated_rating(media.rating, [target_tag])
            if escalated and escalated != media.rating:
                media.rating = escalated
                rating_changed_media.append((media.id, escalated.value))
            
    # 6. Delete source tag
    db.delete(source_tag)
    db.flush()

    def _replace_source_in_groups(raw_groups: list, row_tag_id: int) -> list[list[int]]:
        cleaned: list[list[int]] = []
        for grp in raw_groups:
            if not isinstance(grp, list):
                continue
            new_grp: list[int] = []
            for item in grp:
                tid_val = None
                if isinstance(item, int) and not isinstance(item, bool):
                    tid_val = target_id if item == source_id else item
                elif isinstance(item, str):
                    s = item.strip().lower()
                    if s.isdigit():
                        val = int(s)
                        tid_val = target_id if val == source_id else val
                    elif s == source_name:
                        tid_val = target_id
                if tid_val is not None and tid_val != row_tag_id and tid_val not in new_grp:
                    new_grp.append(tid_val)
            if new_grp:
                new_grp.sort()
                if new_grp not in cleaned:
                    cleaned.append(new_grp)
        return cleaned

    for m_id in newly_linked_target_media_ids:
        if m_id in source_implied_by_media:
            updated_groups = _replace_source_in_groups(source_implied_by_media[m_id], target_id)
            db.execute(
                blombooru_media_tags.update()
                .where(
                    and_(
                        blombooru_media_tags.c.media_id == m_id,
                        blombooru_media_tags.c.tag_id == target_id,
                    )
                )
                .values(implied=True, implied_by=updated_groups)
            )

    for m_id, src_groups in source_implied_by_media.items():
        if m_id in newly_linked_target_media_ids:
            continue
        if m_id in target_existing_by_media:
            tgt_is_imp, tgt_groups = target_existing_by_media[m_id]
            if tgt_is_imp:
                merged_raw = list(tgt_groups) + list(src_groups)
                updated_groups = _replace_source_in_groups(merged_raw, target_id)
                db.execute(
                    blombooru_media_tags.update()
                    .where(
                        and_(
                            blombooru_media_tags.c.media_id == m_id,
                            blombooru_media_tags.c.tag_id == target_id,
                        )
                    )
                    .values(implied=True, implied_by=updated_groups)
                )

    # Replace source_id with target_id inside implied_by across all media tag links
    all_implied_rows = db.query(
        blombooru_media_tags.c.media_id,
        blombooru_media_tags.c.tag_id,
        blombooru_media_tags.c.implied_by,
    ).filter(
        blombooru_media_tags.c.implied.is_(True),
        blombooru_media_tags.c.implied_by.isnot(None),
    ).all()

    for m_id, t_id, imp_by in all_implied_rows:
        if not isinstance(imp_by, list):
            continue
        has_source_ref = False
        for grp in imp_by:
            if isinstance(grp, list):
                for item in grp:
                    if item == source_id or (isinstance(item, str) and item.strip().lower() in (str(source_id), source_name)):
                        has_source_ref = True
                        break
            if has_source_ref:
                break
        if has_source_ref:
            new_imp_by = _replace_source_in_groups(imp_by, t_id)
            db.execute(
                blombooru_media_tags.update()
                .where(
                    and_(
                        blombooru_media_tags.c.media_id == m_id,
                        blombooru_media_tags.c.tag_id == t_id,
                    )
                )
                .values(implied_by=new_imp_by)
            )

    for media in media_with_source:
        db.expire(media, ["media_tag_links", "tags"])

    # 7. Update target tag post counts
    from ..media import update_tag_counts
    update_tag_counts(db, [target_tag.id])
    
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=safe_error_detail("Failed to merge tag", e))

    for m_id, new_rating in rating_changed_media:
        handle_media_rating_changed(db, m_id, new_rating)

    invalidate_media_cache()
    invalidate_tag_cache()

    return {
        "message": f"Successfully merged '{source_name}' into '{target_name}'",
        "source_tag_name": source_name,
        "target_tag_name": target_name
    }
