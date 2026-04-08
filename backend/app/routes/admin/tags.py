import csv
import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...auth import get_current_admin_user, require_admin_mode
from ...config import settings
from ...utils.request_helpers import safe_error_detail
from ...database import get_db
from ...models import Tag, TagAlias, User
from ...utils.logger import logger

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
                if alias_name not in existing_aliases:
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
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Get tag statistics"""
    total_tags = db.query(Tag).count()
    total_aliases = db.query(TagAlias).count()
    
    return {
        "total_tags": total_tags,
        "total_aliases": total_aliases,
    }

@router.get("/search-tags")
async def search_tags(
    q: str,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Search tags"""
    tags = db.query(Tag).filter(
        Tag.name.ilike(f"%{q}%")
    ).order_by(Tag.post_count.desc()).limit(50).all()
    
    return {"tags": tags}

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
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=safe_error_detail("Database error", e))
        
    return {
        "message_key": "notifications.admin.bulk_tag_creation_complete",
        "created": created,
        "skipped": skipped,
        "errors": errors
    }
