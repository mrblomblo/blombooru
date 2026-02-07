from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict
import csv
import io
from ..database import get_db
from ..auth import require_admin_mode
from ..models import User, Tag, TagAlias, TagCategoryEnum
from ..schemas import TagResponse
from ..utils.cache import cache_response, invalidate_tag_cache
from fastapi import Request

router = APIRouter(prefix="/api/tags-management", tags=["tag-management"])

def parse_tag_category(category_num: str) -> TagCategoryEnum:
    """Convert numeric category to enum"""
    mapping = {
        "0": TagCategoryEnum.general,
        "1": TagCategoryEnum.artist,
        "3": TagCategoryEnum.copyright,
        "4": TagCategoryEnum.character,
        "5": TagCategoryEnum.meta
    }
    return mapping.get(category_num, TagCategoryEnum.general)

def parse_aliases(aliases_str: str) -> List[str]:
    """Parse comma-separated aliases"""
    if not aliases_str or aliases_str.strip() == '':
        return []
    
    aliases_str = aliases_str.strip('"\'')
    
    return [tag.strip() for tag in aliases_str.split(',') if tag.strip()]

@router.post("/import-csv")
async def import_tags_csv(
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Import tags from CSV file"""
    
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV")
    
    try:
        content = await file.read()
        csv_text = content.decode('utf-8')
        csv_reader = csv.reader(io.StringIO(csv_text))
        
        stats = {
            "tags_created": 0,
            "tags_updated": 0,
            "aliases_created": 0,
            "errors": []
        }
        
        for row_num, row in enumerate(csv_reader, 1):
            try:
                if len(row) < 4:
                    stats["errors"].append(f"Row {row_num}: Invalid format (expected 4 columns)")
                    continue
                
                tag_name = row[0].strip().lower()
                category = parse_tag_category(row[1].strip())
                # Skip row[2] (usage count)
                aliases_str = row[3].strip()
                
                if not tag_name:
                    continue
                
                tag = db.query(Tag).filter(Tag.name == tag_name).first()
                
                if tag:
                    if tag.category != category:
                        tag.category = category
                        stats["tags_updated"] += 1
                else:
                    tag = Tag(
                        name=tag_name,
                        category=category,
                        post_count=0
                    )
                    db.add(tag)
                    db.flush()  # Get the ID
                    stats["tags_created"] += 1
                
                alias_names = parse_aliases(aliases_str)
                
                for alias_name in alias_names:
                    alias_name = alias_name.lower()
                    
                    existing_alias = db.query(TagAlias).filter(
                        TagAlias.alias_name == alias_name
                    ).first()
                    
                    if not existing_alias:
                        alias = TagAlias(
                            alias_name=alias_name,
                            target_tag_id=tag.id
                        )
                        db.add(alias)
                        stats["aliases_created"] += 1
                
            except Exception as e:
                stats["errors"].append(f"Row {row_num}: {str(e)}")
                continue
        
        db.commit()
        invalidate_tag_cache()
        
        return {
            "success": True,
            "stats": stats
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to import CSV: {str(e)}")

@router.get("/stats")
@cache_response(expire=3600, key_prefix="tags")
async def get_tag_stats(
    request: Request,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Get tag statistics"""
    
    total_tags = db.query(func.count(Tag.id)).scalar()
    total_aliases = db.query(func.count(TagAlias.id)).scalar()
    
    category_counts = db.query(
        Tag.category,
        func.count(Tag.id)
    ).group_by(Tag.category).all()
    
    return {
        "total_tags": total_tags or 0,
        "total_aliases": total_aliases or 0,
        "tags_by_category": {
            cat.value: count for cat, count in category_counts
        } if category_counts else {}
    }

@router.delete("/clear-all")
async def clear_all_tags(
    confirm: bool = False,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Clear all tags from database (dangerous!)"""
    
    if not confirm:
        raise HTTPException(
            status_code=400, 
            detail="Must confirm deletion by setting confirm=true"
        )
    
    try:
        db.query(TagAlias).delete()
        db.query(Tag).delete()
        db.commit()
        invalidate_tag_cache()
        
        # Also clear shared database if enabled
        from ..config import settings
        if settings.SHARED_TAGS_ENABLED:
            from ..database import is_shared_db_available, get_shared_db
            if is_shared_db_available():
                shared_db_gen = get_shared_db()
                shared_db = next(shared_db_gen, None)
                if shared_db:
                    try:
                        from ..services.shared_tags import SharedTagService
                        service = SharedTagService(db, shared_db)
                        service.clear_all_shared()
                    finally:
                        try:
                            next(shared_db_gen, None)
                        except StopIteration:
                            pass
        
        return {"success": True, "message": "All tags cleared"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/search")
@cache_response(expire=3600, key_prefix="tags")
async def search_tags(
    request: Request,
    q: str,
    limit: int = 50,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Search tags for management"""
    
    query = db.query(Tag)
    
    if q:
        query = query.filter(Tag.name.ilike(f"%{q}%"))
    
    tags = query.order_by(Tag.post_count.desc()).limit(limit).all()
    
    results = []
    for tag in tags:
        aliases = db.query(TagAlias).filter(
            TagAlias.target_tag_id == tag.id
        ).all()
        
        results.append({
            "id": tag.id,
            "name": tag.name,
            "category": tag.category.value,
            "post_count": tag.post_count,
            "aliases": [a.alias_name for a in aliases]
        })
    
    return results

@router.delete("/{tag_id}")
async def delete_tag(
    tag_id: int,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Delete a specific tag"""
    
    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    
    tag_name = tag.name  # Save name before deletion
    
    try:
        db.delete(tag)
        db.commit()
        invalidate_tag_cache()
        
        # Also delete from shared database if enabled
        from ..config import settings
        if settings.SHARED_TAGS_ENABLED:
            from ..database import is_shared_db_available, get_shared_db
            if is_shared_db_available():
                shared_db_gen = get_shared_db()
                shared_db = next(shared_db_gen, None)
                if shared_db:
                    try:
                        from ..services.shared_tags import SharedTagService
                        service = SharedTagService(db, shared_db)
                        service.delete_from_shared(tag_name)
                    finally:
                        try:
                            next(shared_db_gen, None)
                        except StopIteration:
                            pass
        
        return {"success": True, "message": f"Tag '{tag_name}' deleted"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

