import json
from datetime import timedelta

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from sqlalchemy import create_engine as sqlalchemy_create_engine
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import sessionmaker

from ... import database
from ...auth import create_access_token, get_password_hash
from ...config import settings
from ...models import User
from ...schemas import OnboardingData
from ...utils.backup import import_full_backup
from ...utils.logger import logger
from ...utils.request_helpers import safe_error_detail

router = APIRouter()

@router.get("/first-run")
async def check_first_run():
    """Check if this is first run"""
    return {"first_run": settings.IS_FIRST_RUN}

def _setup_onboarding(data: OnboardingData) -> None:
    """Core setup routine: validates credentials, tests DB connection, creates tables, admin user, and saves config."""
    if not settings.IS_FIRST_RUN:
        raise HTTPException(status_code=400, detail="Onboarding already completed")
    
    if not data.app_name or len(data.app_name.strip()) == 0:
        raise HTTPException(status_code=400, detail="Application name is required")
    
    if not data.admin_username or len(data.admin_username.strip()) == 0:
        raise HTTPException(status_code=400, detail="Admin username is required")
    
    if not data.admin_password or len(data.admin_password) < 6:
        raise HTTPException(status_code=400, detail="Admin password must be at least 6 characters")
    
    if len(data.admin_password) > 128:
        raise HTTPException(status_code=400, detail="Admin password is too long (max 128 characters)")
    
    logger.info("=== Starting onboarding process ===")
    logger.debug(f"1. Testing database connection to {data.database.host}:{data.database.port}/{data.database.name}")
    
    try:
        test_url = URL.create(
            drivername="postgresql",
            username=data.database.user,
            password=data.database.password,
            host=data.database.host,
            port=data.database.port,
            database=data.database.name,
        )
        
        test_engine = sqlalchemy_create_engine(test_url, pool_pre_ping=True)
        with test_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            logger.info("Database connection successful")
        test_engine.dispose()
    except OperationalError as e:
        error_msg = str(e)
        logger.error(f"Database connection failed: {error_msg}")
        
        if "password authentication failed" in error_msg:
            raise HTTPException(status_code=400, detail="Database authentication failed. Please check your username and password.")
        elif "could not connect to server" in error_msg:
            raise HTTPException(status_code=400, detail="Could not connect to database server. Please check the host and port.")
        elif "database" in error_msg and "does not exist" in error_msg:
            raise HTTPException(status_code=400, detail=f"Database '{data.database.name}' does not exist. Please create it first.")
        else:
            raise HTTPException(status_code=400, detail=safe_error_detail("Database connection failed", e))
    except Exception as e:
        logger.error(f"Unexpected database error: {e}")
        raise HTTPException(status_code=400, detail=safe_error_detail("Database error", e))
    
    logger.debug("2. Creating database schema...")
    new_session_local = None
    temp_engine = None
    
    try:
        temp_db_url = URL.create(
            drivername="postgresql",
            username=data.database.user,
            password=data.database.password,
            host=data.database.host,
            port=data.database.port,
            database=data.database.name,
        )
        temp_engine = sqlalchemy_create_engine(temp_db_url, pool_pre_ping=True)
        new_session_local = sessionmaker(autocommit=False, autoflush=False, bind=temp_engine)
        
        database.Base.metadata.create_all(bind=temp_engine)
        logger.info("Database schema created")
        
        logger.debug("3. Creating admin user...")
        db = new_session_local()
        try:
            try:
                password_hash = get_password_hash(data.admin_password)
                logger.debug("Password hashed successfully")
            except Exception as e:
                raise HTTPException(status_code=500, detail=safe_error_detail("Failed to hash password", e))
            
            admin = User(
                username=data.admin_username,
                password_hash=password_hash
            )
            db.add(admin)
            
            db.commit()
            logger.info("Admin user created")
            
        except IntegrityError as e:
            db.rollback()
            error_msg = str(e)
            logger.error(f"Database integrity error: {error_msg}")
            
            if "unique constraint" in error_msg.lower():
                raise HTTPException(status_code=400, detail="Username already exists in database")
            else:
                raise HTTPException(status_code=400, detail=safe_error_detail("Database constraint violation", e))
        except Exception as e:
            db.rollback()
            logger.error(f"Error creating admin user: {e}")
            raise HTTPException(status_code=500, detail=safe_error_detail("Failed to create admin user", e))
        finally:
            db.close()
        
        logger.debug("4. Saving settings...")
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
                "redis": {
                    "host": data.redis.host,
                    "port": data.redis.port,
                    "db": data.redis.db,
                    "password": data.redis.password,
                    "enabled": data.redis.enabled
                },
                "first_run": False
            })
            logger.info("Settings saved to file")
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
            raise HTTPException(status_code=500, detail=safe_error_detail("Failed to save settings", e))
        
        database.engine = temp_engine
        database.SessionLocal = new_session_local
        
        logger.info("=== Onboarding completed successfully ===")
            
    except HTTPException:
        if new_session_local:
            try:
                new_session_local.close_all()
            except Exception:
                pass
        if temp_engine:
            try:
                temp_engine.dispose()
            except Exception:
                pass
        raise
    except Exception as e:
        if new_session_local:
            try:
                new_session_local.close_all()
            except Exception:
                pass
        if temp_engine:
            try:
                temp_engine.dispose()
            except Exception:
                pass
        logger.error(f"Error initializing database: {e}")
        raise HTTPException(status_code=500, detail=safe_error_detail("Failed to initialize database", e))
    
@router.post("/onboarding")
async def complete_onboarding(data: OnboardingData):
    """Complete first-time setup"""
    _setup_onboarding(data)
    return {"message_key": "notifications.admin.onboarding_completed"}
    
@router.post("/onboarding/import")
async def complete_onboarding_with_backup(
    data: str = Form(...),
    file: UploadFile = File(...)
):
    """Complete first-time setup and restore a full backup archive"""
    if not settings.IS_FIRST_RUN:
        raise HTTPException(status_code=400, detail="Onboarding already completed")

    try:
        parsed_data = json.loads(data)
        onboarding_data = OnboardingData(**parsed_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid onboarding configuration data: {e}")

    # 1. Initialize schema, admin user, and database engine
    _setup_onboarding(onboarding_data)

    # 2. Restore full backup archive
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Uploaded backup file must be a ZIP archive")

    db = database.SessionLocal()
    try:
        stats = import_full_backup(file.file, db)
        return {
            "message_key": "notifications.admin.onboarding_completed",
            "stats": stats
        }
    except Exception as e:
        logger.error(f"Error during backup restore in onboarding: {e}")
        raise HTTPException(status_code=500, detail=safe_error_detail("Failed to restore backup archive", e))
    finally:
        db.close()
