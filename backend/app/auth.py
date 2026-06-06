import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import User
from .utils.logger import logger

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login", auto_error=False)

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 43200  # 30 days

def get_password_hash(password: str) -> str:
    """Hash a password using PBKDF2-SHA256"""
    salt = secrets.token_hex(32)
    pwdhash = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000  # iterations
    )
    
    return f"{salt}${pwdhash.hex()}"

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    try:
        salt, stored_hash = hashed_password.split('$')
        pwdhash = hashlib.pbkdf2_hmac(
            'sha256',
            plain_password.encode('utf-8'),
            salt.encode('utf-8'),
            100000  # iterations
        )
        
        return pwdhash.hex() == stored_hash
    except Exception as e:
        logger.error(f"Password verification error: {e}")
        return False

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def authenticate_user(db: Session, username: str, password: str):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return False
    if not verify_password(password, user.password_hash):
        return False
    return user

def generate_api_key() -> str:
    """Generate a new API key with 'blom_' prefix"""
    random_part = secrets.token_urlsafe(32)
    return f"blom_{random_part}"

def hash_api_key(key: str) -> str:
    """Hash an API key using SHA-256"""
    return hashlib.sha256(key.encode('utf-8')).hexdigest()

def verify_api_key(db: Session, key: str) -> Optional[User]:
    """
    Verify an API key and return the associated User if valid.
    Also updates the last_used_at timestamp.
    """
    from .models import ApiKey
    
    key_hash = hash_api_key(key)
    
    api_key = db.query(ApiKey).filter(
        ApiKey.key_hash == key_hash,
        ApiKey.is_active == True
    ).first()
    
    if not api_key:
        return None
    
    # Update last_used_at
    api_key.last_used_at = datetime.now(timezone.utc)
    db.commit()
    
    return api_key.user

def get_current_user_from_api_key(
    request: Request,
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    FastAPI dependency to get current user from any API key presentation:
    - Authorization: Bearer blom_<key>
    - Authorization: blom_<key>  (bare, no Bearer prefix)
    - Authorization: Basic <base64(user:blom_key)>
    - ?api_key=blom_<key> query parameter
    """
    import base64 as _base64

    auth_header = request.headers.get("Authorization", "")

    # Bearer blom_<key>
    if auth_header.startswith("Bearer blom_"):
        key = auth_header[7:]
        return verify_api_key(db, key)

    # Bare blom_<key> (no Bearer prefix)
    if auth_header.startswith("blom_"):
        return verify_api_key(db, auth_header)

    # Basic auth with API key as the password field
    if auth_header.startswith("Basic "):
        try:
            decoded = _base64.b64decode(auth_header[6:]).decode("utf-8")
            if ":" in decoded:
                _, password = decoded.split(":", 1)
                if password.startswith("blom_"):
                    return verify_api_key(db, password)
        except Exception:
            pass

    # ?api_key= query parameter
    api_key = request.query_params.get("api_key")
    if api_key and api_key.startswith("blom_"):
        return verify_api_key(db, api_key)

    return None

def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    admin_token: Optional[str] = Cookie(default=None),
    db: Session = Depends(get_db)
):
    token_to_use = admin_token or token
    
    if not token_to_use:
        return None
    
    if token_to_use.startswith("blom_"):
        return verify_api_key(db, token_to_use)
    
    try:
        payload = jwt.decode(token_to_use, settings.SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
    except JWTError:
        return None
    
    user = db.query(User).filter(User.username == username).first()
    return user

def get_current_admin_user(
    current_user: Optional[User] = Depends(get_current_user)
):
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    return current_user

def is_admin_mode(admin_mode: Optional[str] = Cookie(default=None)):
    """Check if the admin_mode UI toggle cookie is set.
    
    NOTE: This is NOT a security gate. It is a UI safety toggle that prevents
    accidental destructive actions. Authentication is enforced separately.
    """
    return admin_mode == "true"

def require_admin_mode(
    request: Request,
    current_user: Optional[User] = Depends(get_current_user),
    admin_mode_active: bool = Depends(is_admin_mode),
    api_key_user: Optional[User] = Depends(get_current_user_from_api_key)
):
    """Require admin credentials (session JWT or API key) plus the admin_mode UI toggle for browser sessions."""
    # API key takes priority as API clients don't have the admin_mode cookie
    if api_key_user:
        return api_key_user

    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Only enforce the admin_mode toggle for browser sessions (identified by the admin_token cookie)
    has_session_cookie = bool(request.cookies.get("admin_token"))
    if has_session_cookie and not admin_mode_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You need to be logged in as the admin to perform this action"
        )
    return current_user
