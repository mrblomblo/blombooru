from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import require_admin_mode
from ..database import get_db
from ..models import Tag, TagImplication, User

router = APIRouter(prefix="/api/tag-implications", tags=["tag-implications"])

class TagRef(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True

class TagImplicationResponse(BaseModel):
    id: int
    target_tags: List[TagRef]
    implied_tags: List[TagRef]

    class Config:
        from_attributes = True

class TagImplicationCreate(BaseModel):
    target_tags: List[str]
    implied_tags: List[str]

def _resolve_tag_names(db: Session, tag_names: List[str]) -> List[Tag]:
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

@router.get("/", response_model=List[TagImplicationResponse])
async def list_implications(
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """List all tag implications."""
    implications = db.query(TagImplication).all()

    # Filter out implications where cascading tag deletion left them empty
    results = []
    for imp in implications:
        if len(imp.target_tags) == 0 or len(imp.implied_tags) == 0:
            # Clean up orphaned implications
            db.delete(imp)
            continue
        results.append(imp)

    if len(results) != len(implications):
        db.commit()

    return results

@router.post("/", response_model=TagImplicationResponse, status_code=201)
async def create_implication(
    data: TagImplicationCreate,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Create a new tag implication."""
    if not data.target_tags or not data.implied_tags:
        raise HTTPException(status_code=400, detail="Both target_tags and implied_tags are required")

    target_tags = _resolve_tag_names(db, data.target_tags)
    implied_tags = _resolve_tag_names(db, data.implied_tags)

    if not target_tags or not implied_tags:
        raise HTTPException(status_code=400, detail="Both target_tags and implied_tags are required")

    implication = TagImplication()
    implication.target_tags = target_tags
    implication.implied_tags = implied_tags

    db.add(implication)
    db.commit()
    db.refresh(implication)

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

    if not data.target_tags or not data.implied_tags:
        raise HTTPException(status_code=400, detail="Both target_tags and implied_tags are required")

    target_tags = _resolve_tag_names(db, data.target_tags)
    implied_tags = _resolve_tag_names(db, data.implied_tags)

    if not target_tags or not implied_tags:
        raise HTTPException(status_code=400, detail="Both target_tags and implied_tags are required")

    implication.target_tags = target_tags
    implication.implied_tags = implied_tags

    db.commit()
    db.refresh(implication)

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

    return {"status": "success"}
