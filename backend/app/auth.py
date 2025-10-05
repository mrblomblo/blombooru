from datetime import datetime, timedelta
from typing import Optional
import hashlib
import secrets
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status, Cookie
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from .database import get_db
from .models import User
from .config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login", auto_error=False)

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 43200  # 30 days

def get_password_hash(password: str) -> str:
    """Hash a password using PBKDF2-SHA256"""
    # Generate a random salt
    salt = secrets.token_hex(32)
    
    # Hash the password with the salt
    pwdhash = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000  # iterations
    )
    
    # Return salt and hash combined
    return f"{salt}${pwdhash.hex()}"

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    try:
        # Split the stored password into salt and hash
        salt, stored_hash = hashed_password.split('$')
        
        # Hash the provided password with the same salt
        pwdhash = hashlib.pbkdf2_hmac(
            'sha256',
            plain_password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        )
        
        # Compare the hashes
        return pwdhash.hex() == stored_hash
    except Exception as e:
        print(f"Password verification error: {e}")
        return False

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
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

def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    admin_token: Optional[str] = Cookie(default=None),
    db: Session = Depends(get_db)
):
    # Check cookie first, then bearer token
    token_to_use = admin_token or token
    
    if not token_to_use:
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
    return admin_mode == "true"

def require_admin_mode(
    current_user: User = Depends(get_current_admin_user),
    admin_mode_active: bool = Depends(is_admin_mode)
):
    if not admin_mode_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin mode required for this operation"
        )
    return current_user
