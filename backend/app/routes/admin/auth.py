from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...auth import (create_access_token, get_current_admin_user,
                     get_password_hash, require_admin_mode)
from ...config import settings
from ...utils.request_helpers import safe_error_detail
from ...database import get_db
from ...models import User
from ...schemas import Token, UserLogin
from ...utils.logger import logger

router = APIRouter()

@router.post("/login", response_model=Token)
async def login(credentials: UserLogin, request: Request, response: Response, db: Session = Depends(get_db)):
    """Admin login"""
    from ...auth import authenticate_user
    from ...login_rate_limiter import login_rate_limiter
    
    login_rate_limiter.check_rate_limit(request)
    
    logger.info(f"Login attempt for user: {credentials.username}")
    
    try:
        user = authenticate_user(db, credentials.username, credentials.password)
        
        if not user:
            logger.error(f"Authentication failed for user: {credentials.username}")
            
            login_rate_limiter.record_failed_attempt(request)
            
            remaining = login_rate_limiter.get_remaining_attempts(request)
            if remaining > 0:
                detail = f"Invalid username or password. {remaining} attempt(s) remaining."
            else:
                detail = "Invalid username or password."
            
            raise HTTPException(status_code=401, detail=detail)
        
        logger.info(f"Authentication successful for user: {credentials.username}")
        
        login_rate_limiter.clear_failed_attempts(request)
        
        access_token = create_access_token(
            data={"sub": user.username},
            expires_delta=timedelta(minutes=43200)
        )
        
        is_secure = request.url.scheme == "https"
        
        response.set_cookie(
            key="admin_token",
            value=access_token,
            httponly=True,
            max_age=43200 * 60,
            samesite="lax",
            secure=is_secure
        )

        # Enable admin mode by default on login so admin features work immediately.
        response.set_cookie(
            key="admin_mode",
            value="true",
            httponly=False,
            max_age=43200 * 60,
            samesite="lax",
            secure=is_secure
        )
        
        logger.debug("Login successful, token issued")
        
        return {"access_token": access_token, "token_type": "bearer"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail=safe_error_detail("Login failed", e))

@router.post("/logout")
async def logout(response: Response):
    """Admin logout"""
    response.delete_cookie(key="admin_token")
    response.delete_cookie(key="admin_mode")
    return {"message_key": "notifications.admin.logged_out"}

@router.post("/update-admin-password")
async def update_admin_password(
    data: dict,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Update admin password"""
    new_password = data.get('new_password', '').strip()
    
    if not new_password:
        raise HTTPException(status_code=400, detail="New password is required")
    
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    
    if len(new_password) > 50:
        raise HTTPException(status_code=400, detail="Password is too long (max 50 characters)")
    
    try:
        password_hash = get_password_hash(new_password)
        current_user.password_hash = password_hash
        db.commit()
        
        logger.info(f"Password updated for user: {current_user.username}")
        
        return {"message_key": "notifications.admin.password_updated"}
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating password: {e}")
        raise HTTPException(status_code=500, detail=safe_error_detail("Failed to update password", e))

@router.post("/update-admin-username")
async def update_admin_username(
    data: dict,
    request: Request,
    response: Response,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Update admin username"""
    new_username = data.get('new_username', '').strip()
    
    if not new_username:
        raise HTTPException(status_code=400, detail="New username is required")
    
    if len(new_username) < 1:
        raise HTTPException(status_code=400, detail="Username cannot be empty")
    
    existing_user = db.query(User).filter(User.username == new_username).first()
    if existing_user and existing_user.id != current_user.id:
        raise HTTPException(status_code=400, detail="Username already exists")
    
    try:
        old_username = current_user.username
        
        current_user.username = new_username
        db.commit()
        
        logger.info(f"Username updated from '{old_username}' to '{new_username}'")
        
        access_token = create_access_token(
            data={"sub": new_username},
            expires_delta=timedelta(minutes=43200)
        )
        
        is_secure = request.url.scheme == "https"
        
        response.set_cookie(
            key="admin_token",
            value=access_token,
            httponly=True,
            max_age=43200 * 60,
            samesite="lax",
            secure=is_secure
        )
        
        return {
            "message_key": "notifications.admin.username_updated",
            "new_username": new_username
        }
        
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Database integrity error: {e}")
        raise HTTPException(status_code=400, detail="Username already exists")
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating username: {e}")
        raise HTTPException(status_code=500, detail=safe_error_detail("Failed to update username", e))

@router.post("/toggle-admin-mode")
async def toggle_admin_mode(
    enabled: bool,
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_admin_user)
):
    """Toggle admin mode UI toggle.
    
    The admin_mode cookie is a UX safeguard that prevents accidental destructive
    actions. It is NOT a security gate - actual auth is enforced via JWT by
    get_current_admin_user. The cookie is non-httponly so the frontend JS can
    read it to show/hide admin UI elements.
    """
    is_secure = request.url.scheme == "https"
    
    if enabled:
        response.set_cookie(
            key="admin_mode",
            value="true",
            httponly=False,
            max_age=43200 * 60,
            samesite="lax",
            secure=is_secure
        )
    else:
        response.delete_cookie(key="admin_mode")
    
    return {"admin_mode": enabled}
