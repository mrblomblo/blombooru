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

def verify_api_key_record(db: Session, key: str):
    """
    Verify an API key and return the ApiKey model if valid.
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
    
    return api_key

def verify_api_key(db: Session, key: str) -> Optional[User]:
    """
    Verify an API key and return the associated User if valid.
    Also updates the last_used_at timestamp.
    """
    record = verify_api_key_record(db, key)
    return record.user if record else None

def get_api_key_from_request(
    request: Request,
    db: Session = Depends(get_db)
):
    if hasattr(request.state, "current_api_key") and request.state.current_api_key is not None:
        return request.state.current_api_key

    import base64 as _base64

    auth_header = request.headers.get("Authorization", "")
    api_key_record = None

    # Bearer blom_<key>
    if auth_header.startswith("Bearer blom_"):
        key = auth_header[7:]
        api_key_record = verify_api_key_record(db, key)

    # Bare blom_<key> (no Bearer prefix)
    elif auth_header.startswith("blom_"):
        api_key_record = verify_api_key_record(db, auth_header)

    # Basic auth with API key as the password field
    elif auth_header.startswith("Basic "):
        try:
            decoded = _base64.b64decode(auth_header[6:]).decode("utf-8")
            if ":" in decoded:
                _, password = decoded.split(":", 1)
                if password.startswith("blom_"):
                    api_key_record = verify_api_key_record(db, password)
        except Exception:
            pass

    # ?api_key= query parameter
    if not api_key_record:
        api_key = request.query_params.get("api_key")
        if api_key and api_key.startswith("blom_"):
            api_key_record = verify_api_key_record(db, api_key)

    if api_key_record:
        request.state.current_api_key = api_key_record

    return api_key_record

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
    api_key_record = get_api_key_from_request(request, db)
    return api_key_record.user if api_key_record else None

def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    admin_token: Optional[str] = Cookie(default=None),
    db: Session = Depends(get_db)
):
    token_to_use = admin_token or token
    
    if not token_to_use or token_to_use.startswith("blom_"):
        return None
    
    try:
        payload = jwt.decode(token_to_use, settings.SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
    except JWTError:
        return None
    
    user = db.query(User).filter(User.username == username).first()
    return user

def _enforce_api_key_permission(request: Request, api_key_user: User) -> User:
    """Enforce permission tier for API key authentication (fail-closed to 'read')."""
    api_key = getattr(request.state, "current_api_key", None)
    permission = getattr(api_key, "permission", "read") if api_key else "read"
    if request.url.path.startswith("/api/admin") and permission != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This API key requires administrator access"
        )
    elif permission not in ("write", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This API key has read-only access"
        )
    return api_key_user

def _authenticate_admin_request(
    request: Request,
    current_user: Optional[User],
    api_key_user: Optional[User]
) -> tuple[User, bool]:
    """Authenticate request via API key or session JWT.
    
    Returns (user, is_api_key).
    Raises 401 if unauthenticated, or 403 if API key lacks required permissions.
    """
    if api_key_user:
        return _enforce_api_key_permission(request, api_key_user), True

    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return current_user, False

def get_current_admin_user(
    request: Request,
    current_user: Optional[User] = Depends(get_current_user),
    api_key_user: Optional[User] = Depends(get_current_user_from_api_key)
) -> User:
    user, _ = _authenticate_admin_request(request, current_user, api_key_user)
    return user

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
) -> User:
    """Require admin credentials (session JWT or API key) plus the admin_mode UI toggle for browser sessions."""
    user, is_api_key = _authenticate_admin_request(request, current_user, api_key_user)

    if is_api_key:
        return user

    # Only enforce the admin_mode UI toggle for browser sessions (identified by the admin_token cookie)
    has_session_cookie = bool(request.cookies.get("admin_token"))
    if has_session_cookie and not admin_mode_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You need to be logged in as the admin to perform this action"
        )
    return user
