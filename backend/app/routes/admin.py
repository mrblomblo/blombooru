from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError, IntegrityError
from sqlalchemy import create_engine as sqlalchemy_create_engine, text
from typing import Optional
from datetime import timedelta
from ..database import get_db, init_db
from ..auth import get_password_hash, create_access_token, get_current_admin_user, require_admin_mode
from ..models import User, Album
from ..schemas import OnboardingData, SettingsUpdate, UserLogin, Token
from ..config import settings
from ..utils.file_scanner import scan_for_new_media

router = APIRouter(prefix="/api/admin", tags=["admin"])

@router.get("/first-run")
async def check_first_run():
    """Check if this is first run"""
    return {"first_run": settings.IS_FIRST_RUN}

@router.post("/onboarding")
async def complete_onboarding(data: OnboardingData):
    """Complete first-time setup"""
    if not settings.IS_FIRST_RUN:
        raise HTTPException(status_code=400, detail="Onboarding already completed")
    
    # Validate inputs
    if not data.app_name or len(data.app_name.strip()) == 0:
        raise HTTPException(status_code=400, detail="Application name is required")
    
    if not data.admin_username or len(data.admin_username.strip()) == 0:
        raise HTTPException(status_code=400, detail="Admin username is required")
    
    if not data.admin_password or len(data.admin_password) < 6:
        raise HTTPException(status_code=400, detail="Admin password must be at least 6 characters")
    
    if len(data.admin_password) > 128:
        raise HTTPException(status_code=400, detail="Admin password is too long (max 128 characters)")
    
    # Test database connection
    print("=== Starting onboarding process ===")
    print(f"1. Testing database connection to {data.database.host}:{data.database.port}/{data.database.name}")
    
    try:
        test_url = f"postgresql://{data.database.user}:{data.database.password}@{data.database.host}:{data.database.port}/{data.database.name}"
        
        test_engine = sqlalchemy_create_engine(test_url, pool_pre_ping=True)
        with test_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            print("✓ Database connection successful")
        test_engine.dispose()
    except OperationalError as e:
        error_msg = str(e)
        print(f"✗ Database connection failed: {error_msg}")
        
        # Provide more helpful error messages
        if "password authentication failed" in error_msg:
            raise HTTPException(status_code=400, detail="Database authentication failed. Please check your username and password.")
        elif "could not connect to server" in error_msg:
            raise HTTPException(status_code=400, detail="Could not connect to database server. Please check the host and port.")
        elif "database" in error_msg and "does not exist" in error_msg:
            raise HTTPException(status_code=400, detail=f"Database '{data.database.name}' does not exist. Please create it first.")
        else:
            raise HTTPException(status_code=400, detail=f"Database connection failed: {error_msg}")
    except Exception as e:
        print(f"✗ Unexpected database error: {e}")
        raise HTTPException(status_code=400, detail=f"Database error: {str(e)}")
    
    # Create database schema and admin user (but don't save settings yet)
    print("2. Creating database schema...")
    new_session_local = None
    temp_engine = None
    
    try:
        from .. import database
        from sqlalchemy.orm import sessionmaker
        
        # Create temporary engine
        temp_db_url = f"postgresql://{data.database.user}:{data.database.password}@{data.database.host}:{data.database.port}/{data.database.name}"
        temp_engine = sqlalchemy_create_engine(temp_db_url, pool_pre_ping=True)
        new_session_local = sessionmaker(autocommit=False, autoflush=False, bind=temp_engine)
        
        # Create all tables
        database.Base.metadata.create_all(bind=temp_engine)
        print("✓ Database schema created")
        
        # Create admin user and favorites album
        print("3. Creating admin user and favorites album...")
        db = new_session_local()
        try:
            # Hash the password
            try:
                password_hash = get_password_hash(data.admin_password)
                print(f"✓ Password hashed successfully")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to hash password: {str(e)}")
            
            # Create admin user
            admin = User(
                username=data.admin_username,
                password_hash=password_hash
            )
            db.add(admin)
            
            # Create favorites album
            favorites = Album(
                name="Favorites",
                description="Your favorite media",
                is_system=True
            )
            db.add(favorites)
            
            # Commit everything
            db.commit()
            print("✓ Admin user and favorites album created")
            
        except IntegrityError as e:
            db.rollback()
            error_msg = str(e)
            print(f"✗ Database integrity error: {error_msg}")
            
            if "unique constraint" in error_msg.lower():
                raise HTTPException(status_code=400, detail="Username already exists in database")
            else:
                raise HTTPException(status_code=400, detail=f"Database constraint violation: {error_msg}")
        except Exception as e:
            db.rollback()
            print(f"✗ Error creating admin user: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to create admin user: {str(e)}")
        finally:
            db.close()
        
        # Everything worked! Now save settings to file
        print("4. Saving settings...")
        try:
            settings.save_settings({
                "app_name": data.app_name,
                "database": {
                    "host": data.database.host,
                    "port": data.database.port,
                    "name": data.database.name,
                    "user": data.database.user,
                    "password": data.database.password
                },
                "first_run": False
            })
            print("✓ Settings saved to file")
        except Exception as e:
            print(f"✗ Failed to save settings: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to save settings: {str(e)}")
        
        # Update module-level database variables
        database.engine = temp_engine
        database.SessionLocal = new_session_local
        
        print("=== Onboarding completed successfully ===")
            
    except HTTPException:
        # Clean up on HTTP exceptions
        if new_session_local:
            try:
                new_session_local.close_all()
            except:
                pass
        if temp_engine:
            try:
                temp_engine.dispose()
            except:
                pass
        raise
    except Exception as e:
        # Clean up on other exceptions
        if new_session_local:
            try:
                new_session_local.close_all()
            except:
                pass
        if temp_engine:
            try:
                temp_engine.dispose()
            except:
                pass
        print(f"✗ Error initializing database: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to initialize database: {str(e)}")
    
    return {"message": "Onboarding completed successfully"}

@router.post("/login", response_model=Token)
async def login(credentials: UserLogin, response: Response, db: Session = Depends(get_db)):
    """Admin login"""
    from ..auth import authenticate_user
    
    print(f"Login attempt for user: {credentials.username}")
    
    try:
        user = authenticate_user(db, credentials.username, credentials.password)
        
        if not user:
            print(f"Authentication failed for user: {credentials.username}")
            raise HTTPException(status_code=401, detail="Invalid username or password")
        
        print(f"Authentication successful for user: {credentials.username}")
        
        access_token = create_access_token(
            data={"sub": user.username},
            expires_delta=timedelta(minutes=43200)
        )
        
        # Set cookie
        response.set_cookie(
            key="admin_token",
            value=access_token,
            httponly=True,
            max_age=43200 * 60,
            samesite="lax"
        )
        
        print(f"Login successful, token issued")
        
        return {"access_token": access_token, "token_type": "bearer"}
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"Login error: {e}")
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")

@router.post("/logout")
async def logout(response: Response):
    """Admin logout"""
    response.delete_cookie(key="admin_token")
    response.delete_cookie(key="admin_mode")
    return {"message": "Logged out successfully"}

@router.post("/toggle-admin-mode")
async def toggle_admin_mode(
    enabled: bool,
    response: Response,
    current_user: User = Depends(get_current_admin_user)
):
    """Toggle admin mode"""
    if enabled:
        response.set_cookie(
            key="admin_mode",
            value="true",
            httponly=False,
            max_age=43200 * 60,
            samesite="lax"
        )
    else:
        response.delete_cookie(key="admin_mode")
    
    return {"admin_mode": enabled}

@router.get("/settings")
async def get_settings(current_user: User = Depends(get_current_admin_user)):
    """Get current settings"""
    # Don't return sensitive data
    safe_settings = settings.settings.copy()
    if "database" in safe_settings:
        safe_settings["database"] = {**safe_settings["database"], "password": "***"}
    safe_settings.pop("secret_key", None)
    return safe_settings

@router.patch("/settings")
async def update_settings(
    updates: SettingsUpdate,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Update settings"""
    update_dict = updates.dict(exclude_unset=True)
    settings.save_settings(update_dict)
    return {"message": "Settings updated successfully"}

@router.post("/scan-media")
async def scan_media(
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Manually trigger media scan"""
    result = scan_for_new_media(db)
    return result

@router.get("/themes")
async def get_available_themes():
    """Get list of available themes"""
    theme_dir = settings.BASE_DIR / "frontend" / "static" / "css" / "themes"
    themes = []
    
    if theme_dir.exists():
        for theme_file in theme_dir.glob("*.css"):
            themes.append(theme_file.stem)
    
    return {"themes": themes}

@router.post("/maintenance/fix-album-memberships")
async def fix_album_memberships(current_user: User = Depends(require_admin_mode), db: Session = Depends(get_db)):
    # 1) Remove duplicates (keep one)
    delete_sql = text("""
        DELETE FROM blombooru_album_media a
        USING blombooru_album_media b
        WHERE a.ctid < b.ctid
          AND a.album_id = b.album_id
          AND a.media_id = b.media_id
    """)
    db.execute(delete_sql)

    # 2) Add a unique index to prevent future duplicates
    unique_sql = text("""
        CREATE UNIQUE INDEX IF NOT EXISTS blombooru_album_media_unique
        ON blombooru_album_media (album_id, media_id)
    """)
    db.execute(unique_sql)

    db.commit()
    return {"message": "Album memberships deduplicated and unique index ensured"}
