from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...auth import require_admin_mode
from ...utils.request_helpers import safe_error_detail
from ...auth import generate_api_key, hash_api_key
from ...database import get_db
from ...models import ApiKey, User
from ...schemas import ApiKeyCreate, ApiKeyListResponse, ApiKeyResponse

router = APIRouter()

@router.get("/api-keys", response_model=list[ApiKeyListResponse])
async def list_api_keys(
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """List all API keys"""
    keys = db.query(ApiKey).filter(ApiKey.is_active == True).order_by(ApiKey.created_at.desc()).all()
    return keys

@router.post("/api-keys", response_model=ApiKeyResponse)
async def create_api_key(
    data: ApiKeyCreate,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Generate a new API key"""
    raw_key = generate_api_key()
    key_hash = hash_api_key(raw_key)
    key_prefix = raw_key[:12]
    
    new_key = ApiKey(
        key_hash=key_hash,
        key_prefix=key_prefix,
        name=data.name,
        user_id=current_user.id
    )
    
    try:
        db.add(new_key)
        db.commit()
        db.refresh(new_key)
        
        return {
            "id": new_key.id,
            "key": raw_key,
            "key_prefix": new_key.key_prefix,
            "name": new_key.name,
            "created_at": new_key.created_at
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=safe_error_detail("Failed to create API key", e))

@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    key_id: int,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Revoke an API key"""
    key = db.query(ApiKey).filter(ApiKey.id == key_id).first()
    
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")
    
    if not key.is_active:
        raise HTTPException(status_code=400, detail="API key is already revoked")

    try:
        key.is_active = False
        db.commit()
        return {"message_key": "notifications.admin.api_key_revoked"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=safe_error_detail("Failed to revoke API key", e))
