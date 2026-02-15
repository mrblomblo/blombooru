from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from ..database import get_db
from ..auth import require_admin_mode
from ..models import BooruConfig, User

router = APIRouter(prefix="/api/booru-config", tags=["booru-config"])

class BooruConfigBase(BaseModel):
    domain: str
    username: Optional[str] = None

class BooruConfigCreate(BooruConfigBase):
    api_key: Optional[str] = None

class BooruConfigResponse(BooruConfigBase):
    created_at: datetime
    updated_at: datetime
    has_api_key: bool

    class Config:
        from_attributes = True

@router.get("/", response_model=List[BooruConfigResponse])
async def list_booru_configs(
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """List all configured booru domains."""
    configs = db.query(BooruConfig).all()
    
    # Transform to hide API key
    results = []
    for c in configs:
        results.append(BooruConfigResponse(
            domain=c.domain,
            username=c.username,
            created_at=c.created_at,
            updated_at=c.updated_at,
            has_api_key=bool(c.api_key)
        ))
    return results

@router.post("/", response_model=BooruConfigResponse)
async def create_or_update_booru_config(
    idx: BooruConfigCreate,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Create or update a booru configuration."""
    # Normalize domain
    domain = idx.domain.strip().lower()
    if "://" in domain:
        domain = domain.split("://")[1]
    if domain.endswith("/"):
        domain = domain[:-1]

    config = db.query(BooruConfig).filter(BooruConfig.domain == domain).first()
    
    if config:
        # Update
        if idx.username is not None:
            config.username = idx.username
        if idx.api_key is not None:
            config.api_key = idx.api_key
        config.updated_at = datetime.utcnow()
    else:
        # Create
        config = BooruConfig(
            domain=domain,
            username=idx.username,
            api_key=idx.api_key
        )
        db.add(config)
    
    db.commit()
    db.refresh(config)
    
    return BooruConfigResponse(
        domain=config.domain,
        username=config.username,
        created_at=config.created_at,
        updated_at=config.updated_at,
        has_api_key=bool(config.api_key)
    )

@router.delete("/{domain}")
async def delete_booru_config(
    domain: str,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Delete a booru configuration."""
    config = db.query(BooruConfig).filter(BooruConfig.domain == domain).first()
    if not config:
        raise HTTPException(status_code=404, detail="admin.settings.booru_config.error_not_found")
        
    db.delete(config)
    db.commit()
    return {"status": "success", "message_key": "admin.settings.booru_config.delete_success", "message_args": {"domain": domain}}
