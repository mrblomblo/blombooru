import os
from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, File, Request
import json
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import OperationalError, IntegrityError
from sqlalchemy import create_engine as sqlalchemy_create_engine, text
from typing import Optional
from datetime import timedelta
import csv
import io
from ..database import get_db, init_db
from ..auth import get_password_hash, create_access_token, get_current_admin_user, require_admin_mode, generate_api_key, hash_api_key
from ..models import User, Tag, TagAlias, ApiKey
from ..schemas import OnboardingData, SettingsUpdate, UserLogin, Token, ApiKeyCreate, ApiKeyResponse, ApiKeyListResponse
from ..config import settings
from ..utils.file_scanner import find_untracked_media
from ..themes import theme_registry
from ..utils.backup import generate_tags_dump, stream_zip_generator, get_media_files_generator, import_full_backup, generate_tags_csv_stream
from fastapi.responses import StreamingResponse
import tempfile
import shutil
import zipfile
from pathlib import Path

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
    
    if not data.app_name or len(data.app_name.strip()) == 0:
        raise HTTPException(status_code=400, detail="Application name is required")
    
    if not data.admin_username or len(data.admin_username.strip()) == 0:
        raise HTTPException(status_code=400, detail="Admin username is required")
    
    if not data.admin_password or len(data.admin_password) < 6:
        raise HTTPException(status_code=400, detail="Admin password must be at least 6 characters")
    
    if len(data.admin_password) > 128:
        raise HTTPException(status_code=400, detail="Admin password is too long (max 128 characters)")
    
    print("=== Starting onboarding process ===")
    print(f"1. Testing database connection to {data.database.host}:{data.database.port}/{data.database.name}")
    
    try:
        test_url = f"postgresql://{data.database.user}:{data.database.password}@{data.database.host}:{data.database.port}/{data.database.name}"
        
        test_engine = sqlalchemy_create_engine(test_url, pool_pre_ping=True)
        with test_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            print("Database connection successful")
        test_engine.dispose()
    except OperationalError as e:
        error_msg = str(e)
        print(f"Database connection failed: {error_msg}")
        
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
        print(f"Unexpected database error: {e}")
        raise HTTPException(status_code=400, detail=f"Database error: {str(e)}")
    
    # Create database schema and admin user (but don't save settings yet)
    print("2. Creating database schema...")
    new_session_local = None
    temp_engine = None
    
    try:
        from .. import database
        from sqlalchemy.orm import sessionmaker
        
        temp_db_url = f"postgresql://{data.database.user}:{data.database.password}@{data.database.host}:{data.database.port}/{data.database.name}"
        temp_engine = sqlalchemy_create_engine(temp_db_url, pool_pre_ping=True)
        new_session_local = sessionmaker(autocommit=False, autoflush=False, bind=temp_engine)
        
        database.Base.metadata.create_all(bind=temp_engine)
        print("Database schema created")
        
        print("3. Creating admin user...")
        db = new_session_local()
        try:
            try:
                password_hash = get_password_hash(data.admin_password)
                print("Password hashed successfully")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to hash password: {str(e)}")
            
            admin = User(
                username=data.admin_username,
                password_hash=password_hash
            )
            db.add(admin)
            
            db.commit()
            print("Admin user created")
            
        except IntegrityError as e:
            db.rollback()
            error_msg = str(e)
            print(f"Database integrity error: {error_msg}")
            
            if "unique constraint" in error_msg.lower():
                raise HTTPException(status_code=400, detail="Username already exists in database")
            else:
                raise HTTPException(status_code=400, detail=f"Database constraint violation: {error_msg}")
        except Exception as e:
            db.rollback()
            print(f"Error creating admin user: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to create admin user: {str(e)}")
        finally:
            db.close()
        
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
                "redis": {
                    "host": data.redis.host,
                    "port": data.redis.port,
                    "db": data.redis.db,
                    "password": data.redis.password,
                    "enabled": data.redis.enabled
                },
                "first_run": False
            })
            print("Settings saved to file")
        except Exception as e:
            print(f"Failed to save settings: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to save settings: {str(e)}")
        
        # Update module-level database variables
        database.engine = temp_engine
        database.SessionLocal = new_session_local
        
        print("=== Onboarding completed successfully ===")
            
    except HTTPException:
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
        print(f"Error initializing database: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to initialize database: {str(e)}")
    
    return {"message_key": "notifications.admin.onboarding_completed"}

@router.post("/login", response_model=Token)
async def login(credentials: UserLogin, request: Request, response: Response, db: Session = Depends(get_db)):
    """Admin login"""
    from ..auth import authenticate_user
    from ..login_rate_limiter import login_rate_limiter
    
    login_rate_limiter.check_rate_limit(request)
    
    print(f"Login attempt for user: {credentials.username}")
    
    try:
        user = authenticate_user(db, credentials.username, credentials.password)
        
        if not user:
            print(f"Authentication failed for user: {credentials.username}")
            
            login_rate_limiter.record_failed_attempt(request)
            
            remaining = login_rate_limiter.get_remaining_attempts(request)
            if remaining > 0:
                detail = f"Invalid username or password. {remaining} attempt(s) remaining."
            else:
                detail = "Invalid username or password."
            
            raise HTTPException(status_code=401, detail=detail)
        
        print(f"Authentication successful for user: {credentials.username}")
        
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
            samesite="none" if is_secure else "lax",
            secure=is_secure
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
        
        print(f"Password updated for user: {current_user.username}")
        
        return {"message_key": "notifications.admin.password_updated"}
        
    except Exception as e:
        db.rollback()
        print(f"Error updating password: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update password: {str(e)}")

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
    
    # Check if username already exists (and it's not the current user)
    existing_user = db.query(User).filter(User.username == new_username).first()
    if existing_user and existing_user.id != current_user.id:
        raise HTTPException(status_code=400, detail="Username already exists")
    
    try:
        old_username = current_user.username
        
        current_user.username = new_username
        db.commit()
        
        print(f"Username updated from '{old_username}' to '{new_username}'")
        
        # Issue new token with updated username and update cookie
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
            samesite="none" if is_secure else "lax",
            secure=is_secure
        )
        
        return {
            "message_key": "notifications.admin.username_updated",
            "new_username": new_username
        }
        
    except IntegrityError as e:
        db.rollback()
        print(f"Database integrity error: {e}")
        raise HTTPException(status_code=400, detail="Username already exists")
    except Exception as e:
        db.rollback()
        print(f"Error updating username: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update username: {str(e)}")

@router.post("/toggle-admin-mode")
async def toggle_admin_mode(
    enabled: bool,
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_admin_user)
):
    """Toggle admin mode"""
    is_secure = request.url.scheme == "https"
    
    if enabled:
        response.set_cookie(
            key="admin_mode",
            value="true",
            httponly=False,
            max_age=43200 * 60,
            samesite="none" if is_secure else "lax",
            secure=is_secure
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
    if "redis" in safe_settings:
        safe_settings["redis"] = {**safe_settings["redis"], "password": "***"}
    if "shared_tags" in safe_settings:
        safe_settings["shared_tags"] = {**safe_settings["shared_tags"], "password": "***"}
    safe_settings.pop("secret_key", None)
    return safe_settings

@router.post("/test-redis")
async def test_redis(data: dict, current_user: User = Depends(require_admin_mode)):
    """Test Redis connection"""
    import redis
    try:
        host = data.get('host', 'redis')
        port = data.get('port', 6379)
        db = data.get('db', 0)
        password = data.get('password')
        if password == "***": # Don't overwrite with placeholder
            password = settings.REDIS_PASSWORD

        client = redis.Redis(
            host=host,
            port=port,
            db=db,
            password=password,
            decode_responses=True,
            socket_connect_timeout=2
        )
        client.ping()
        return {"success": True, "message_key": "notifications.admin.redis_connection_successful"}
    except Exception as e:
        return {"success": False, "message_key": "notifications.admin.redis_connection_failed", "error": str(e)}

@router.patch("/settings")
async def update_settings(
    updates: SettingsUpdate,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Update settings"""
    update_dict = updates.dict(exclude_unset=True)
    
    # Special handling for Redis and shared tag DB to avoid overwriting password with placeholder
    if "redis" in update_dict and update_dict["redis"].get("password") == "***":
        update_dict["redis"]["password"] = settings.REDIS_PASSWORD
    
    if "shared_tags" in update_dict and update_dict["shared_tags"].get("password") == "***":
        update_dict["shared_tags"]["password"] = settings.SHARED_TAG_DB_PASSWORD

    settings.save_settings(update_dict)
    
    # Reload Redis client if enabled changed or settings updated
    from ..redis_client import redis_cache
    if "redis" in update_dict:
        redis_cache._enabled = settings.REDIS_ENABLED
        redis_cache._client = None # Force reconnect
    
    # Reconnect shared tag database if settings changed
    if "shared_tags" in update_dict:
        from ..database import reconnect_shared_db, init_shared_db
        reconnect_shared_db()
        if settings.SHARED_TAGS_ENABLED:
            init_shared_db()
        
    return {"message_key": "notifications.admin.settings_updated"}

@router.post("/scan-media")
async def scan_media(
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Find untracked media files"""    
    result = find_untracked_media(db)
    
    return {
        'new_files': result['new_files'],
        'files': [f['path'] for f in result['files']]
    }
    
@router.get("/get-untracked-file")
async def get_untracked_file(
    path: str,
    current_user: User = Depends(require_admin_mode)
):
    """Serve an untracked file for importing"""
    from pathlib import Path
    import mimetypes
    from fastapi.responses import FileResponse
    
    file_path = Path(path)
    
    # Security check - ensure file exists and is within allowed directories
    if not file_path.is_absolute():
        raise HTTPException(status_code=400, detail="Invalid file path")
    
    # Check if file is within ORIGINAL_DIR
    try:
        file_path = file_path.resolve()
        settings.ORIGINAL_DIR.resolve()
        file_path.relative_to(settings.ORIGINAL_DIR.resolve())
    except (ValueError, FileNotFoundError):
        raise HTTPException(status_code=403, detail="Access denied")
    
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    
    mime_type, _ = mimetypes.guess_type(str(file_path))
    if not mime_type:
        mime_type = "application/octet-stream"
    
    return FileResponse(
        path=str(file_path),
        media_type=mime_type,
        filename=file_path.name
    )

@router.get("/media-stats")
async def get_media_stats(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Get media statistics"""
    from ..models import Media
    from sqlalchemy import func
    
    total_media = db.query(Media).count()
    total_images = db.query(Media).filter(Media.file_type == 'image').count()
    total_gifs = db.query(Media).filter(Media.file_type == 'gif').count()
    total_videos = db.query(Media).filter(Media.file_type == 'video').count()
    
    return {
        "total_media": total_media,
        "total_images": total_images,
        "total_gifs": total_gifs,
        "total_videos": total_videos,
    }

@router.get("/stats")
async def get_comprehensive_stats(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Get comprehensive statistics for admin dashboard"""
    from ..models import Media, Tag, TagAlias, Album
    from sqlalchemy import func
    from datetime import datetime, timedelta
    
    # Media statistics
    total_media = db.query(Media).count()
    media_by_type = {
        'image': db.query(Media).filter(Media.file_type == 'image').count(),
        'gif': db.query(Media).filter(Media.file_type == 'gif').count(),
        'video': db.query(Media).filter(Media.file_type == 'video').count()
    }
    
    media_by_rating = {
        'safe': db.query(Media).filter(Media.rating == 'safe').count(),
        'questionable': db.query(Media).filter(Media.rating == 'questionable').count(),
        'explicit': db.query(Media).filter(Media.rating == 'explicit').count()
    }
    
    # Upload trends (last 30 days)
    thirty_days_ago = datetime.now() - timedelta(days=30)
    upload_trends = db.query(
        func.date(Media.uploaded_at).label('date'),
        func.count(Media.id).label('count')
    ).filter(
        Media.uploaded_at >= thirty_days_ago
    ).group_by(
        func.date(Media.uploaded_at)
    ).order_by('date').all()
    
    upload_trends_data = [
        {'date': str(trend.date), 'count': trend.count}
        for trend in upload_trends
    ]
    
    # Tag statistics
    total_tags = db.query(Tag).count()
    total_aliases = db.query(TagAlias).count()
    
    # Top 10 tags by usage
    top_tags = db.query(Tag).order_by(Tag.post_count.desc()).limit(10).all()
    top_tags_data = [
        {'name': tag.name, 'count': tag.post_count, 'category': tag.category.value}
        for tag in top_tags
    ]
    
    # Top 10 tags by category
    from ..models import TagCategoryEnum
    top_tags_by_category = {}
    for category in TagCategoryEnum:
        category_tags = db.query(Tag).filter(
            Tag.category == category
        ).order_by(Tag.post_count.desc()).limit(10).all()
        
        top_tags_by_category[category.value] = [
            {'name': tag.name, 'count': tag.post_count}
            for tag in category_tags
        ]
    
    # Tag category distribution
    tag_categories = db.query(
        Tag.category,
        func.count(Tag.id).label('count')
    ).group_by(Tag.category).all()
    
    tag_category_data = {
        cat.category.value: cat.count
        for cat in tag_categories
    }
    
    # Album statistics
    total_albums = db.query(Album).count()
    
    from sqlalchemy import select, func as sql_func
    
    album_media_counts = db.query(
        Album.id,
        sql_func.count(Media.id).label('media_count')
    ).outerjoin(
        Album.media
    ).group_by(Album.id).all()
    
    album_size_distribution = {
        '0': 0,
        '1-10': 0,
        '11-50': 0,
        '51-100': 0,
        '100+': 0
    }
    
    for album_id, count in album_media_counts:
        if count == 0:
            album_size_distribution['0'] += 1
        elif count <= 10:
            album_size_distribution['1-10'] += 1
        elif count <= 50:
            album_size_distribution['11-50'] += 1
        elif count <= 100:
            album_size_distribution['51-100'] += 1
        else:
            album_size_distribution['100+'] += 1
    
    # Storage statistics
    storage_stats = db.query(
        func.sum(Media.file_size).label('total_size'),
        func.avg(Media.file_size).label('avg_size')
    ).first()
    
    total_storage = storage_stats.total_size or 0
    avg_file_size = int(storage_stats.avg_size or 0)
    
    # Media relationship statistics
    from sqlalchemy import exists, select
    from sqlalchemy.orm import aliased
    
    ChildMedia = aliased(Media)
    
    total_parents = db.query(Media).filter(
        exists().where(ChildMedia.parent_id == Media.id)
    ).count()
    
    total_children = db.query(Media).filter(Media.parent_id != None).count()

    return {
        "media": {
            "total": total_media,
            "by_type": media_by_type,
            "by_rating": media_by_rating,
            "relationships": {
                "total_parents": total_parents,
                "total_children": total_children
            }
        },
        "upload_trends": upload_trends_data,
        "tags": {
            "total": total_tags,
            "total_aliases": total_aliases,
            "total_with_aliases": total_tags + total_aliases,
            "top_tags": top_tags_data,
            "top_tags_by_category": top_tags_by_category,
            "by_category": tag_category_data
        },
        "albums": {
            "total": total_albums,
            "size_distribution": album_size_distribution
        },
        "storage": {
            "total_bytes": total_storage,
            "avg_file_size_bytes": avg_file_size
        }
    }


def import_tags_csv_logic(csv_text: str, db: Session):
    """
    Core logic for importing tags from CSV content.
    Returns a dict with import statistics.
    """
    import csv
    import io
    from ..models import Tag, TagAlias
    
    category_map = {
        0: 'general',
        1: 'artist',
        3: 'copyright',
        4: 'character',
        5: 'meta'
    }
    
    MAX_TAG_LENGTH = 255
    MAX_ALIAS_LENGTH = 255
    
    tags_created = 0
    aliases_created = 0
    tags_updated = 0
    errors = []
    skipped_long_tags = 0
    skipped_long_aliases = 0
    
    BATCH_SIZE = 1000
    
    # PASS 1: Import tags only
    print("Pass 1: Importing tags...")
    csv_reader = csv.reader(io.StringIO(csv_text))
    
    tag_data = []
    tags_to_create = []
    rows_processed = 0
    existing_tags = {tag.name: tag for tag in db.query(Tag).all()}
    
    for row_num, row in enumerate(csv_reader, 1):
        try:
            if len(row) < 2:
                continue
            
            tag_name = row[0].strip().lower()
            if not tag_name:
                continue
            
            if len(tag_name) > MAX_TAG_LENGTH:
                skipped_long_tags += 1
                errors.append({"key": "notifications.admin.error_tag_too_long", "row": row_num, "tag": tag_name[:50], "length": len(tag_name)})
                continue
            
            try:
                category_num = int(row[1])
            except (ValueError, IndexError):
                errors.append({"key": "notifications.admin.error_invalid_category", "row": row_num})
                continue
            
            aliases_str = row[3] if len(row) > 3 else ""
            category = category_map.get(category_num, 'general')
            
            tag_data.append((tag_name, category, aliases_str))
            
            if tag_name in existing_tags:
                tag = existing_tags[tag_name]
                if tag.category != category:
                    tag.category = category
                    tags_updated += 1
            else:
                tags_to_create.append({
                    'name': tag_name,
                    'category': category,
                    'post_count': 0
                })
                tags_created += 1
            
            rows_processed += 1
            
            if rows_processed % BATCH_SIZE == 0:
                try:
                    if tags_to_create:
                        db.bulk_insert_mappings(Tag, tags_to_create)
                        tags_to_create = []
                    
                    db.commit()
                    print(f"Pass 1: Processed {rows_processed} tags...")
                    db.expire_all()
                except Exception as e:
                    db.rollback()
                    errors.append({"key": "notifications.admin.error_batch_error", "row": row_num, "error": str(e)})
                    tags_to_create = []
                    existing_tags = {tag.name: tag for tag in db.query(Tag).all()}
        
        except Exception as e:
            errors.append({"key": "notifications.admin.error_row_error", "row": row_num, "error": str(e)})
            continue
    
    # Final commit for pass 1
    try:
        if tags_to_create:
            db.bulk_insert_mappings(Tag, tags_to_create)
        db.commit()
    except Exception as e:
        db.rollback()
        errors.append({"key": "notifications.admin.error_final_batch_pass1", "error": str(e)})
    
    print(f"Pass 1 complete: {tags_created} tags created, {tags_updated} updated, {skipped_long_tags} skipped")
    
    existing_tags = None
    tags_to_create = None
    db.expire_all()
    
    # PASS 2: Import aliases
    print("Pass 2: Importing aliases...")
    print("Building tag mapping...")
    tag_map = {}
    offset = 0
    chunk_size = 10000
    
    while True:
        tags_chunk = db.query(Tag.name, Tag.id).limit(chunk_size).offset(offset).all()
        if not tags_chunk:
            break
        
        for name, tag_id in tags_chunk:
            tag_map[name] = tag_id
        
        offset += chunk_size
        if offset % 50000 == 0:
            print(f"Loaded {offset} tag mappings...")
    
    print(f"Tag mapping complete: {len(tag_map)} tags")
    
    existing_aliases = {alias.alias_name for alias in db.query(TagAlias.alias_name).all()}
    aliases_to_create = []
    rows_processed = 0
    
    for tag_name, category, aliases_str in tag_data:
        try:
            if not aliases_str or tag_name not in tag_map:
                continue
            
            tag_id = tag_map[tag_name]
            
            alias_names = set()
            for a in aliases_str.split(','):
                alias = a.strip().lower()
                if not alias or alias == tag_name:
                    continue
                
                if len(alias) > MAX_ALIAS_LENGTH:
                    skipped_long_aliases += 1
                    continue
                
                alias_names.add(alias)
            
            for alias_name in alias_names:
                if alias_name not in existing_aliases:
                    aliases_to_create.append({
                        'alias_name': alias_name,
                        'target_tag_id': tag_id
                    })
                    existing_aliases.add(alias_name)
                    aliases_created += 1
            
            rows_processed += 1
            
            if rows_processed % BATCH_SIZE == 0:
                try:
                    if aliases_to_create:
                        db.bulk_insert_mappings(TagAlias, aliases_to_create)
                        aliases_to_create = []
                    
                    db.commit()
                    print(f"Pass 2: Processed {rows_processed} tags, created {aliases_created} aliases...")
                    db.expire_all()
                except IntegrityError as e:
                    db.rollback()
                    errors.append({"key": "notifications.admin.error_alias_batch_integrity", "row": rows_processed, "error": str(e)})
                    aliases_to_create = []
                    existing_aliases = {alias.alias_name for alias in db.query(TagAlias.alias_name).all()}
                except Exception as e:
                    db.rollback()
                    errors.append({"key": "notifications.admin.error_alias_batch", "row": rows_processed, "error": str(e)})
                    aliases_to_create = []
                    existing_aliases = {alias.alias_name for alias in db.query(TagAlias.alias_name).all()}
        
        except Exception as e:
            errors.append({"key": "notifications.admin.error_pass2_tag", "tag": tag_name, "error": str(e)})
            continue
    
    # Final commit for pass 2
    try:
        if aliases_to_create:
            db.bulk_insert_mappings(TagAlias, aliases_to_create)
        db.commit()
    except Exception as e:
        db.rollback()
        errors.append({"key": "notifications.admin.error_final_batch_pass2", "error": str(e)})
    
    print(f"Pass 2 complete: {aliases_created} aliases created, {skipped_long_aliases} skipped")
    
    return {
        "message_key": "notifications.admin.tags_imported",
        "tags_created": tags_created,
        "tags_updated": tags_updated,
        "aliases_created": aliases_created,
        "rows_processed": len(tag_data),
        "skipped_long_tags": skipped_long_tags,
        "skipped_long_aliases": skipped_long_aliases,
        "errors": errors[:20] if errors else [],
        "total_errors": len(errors)
    }

@router.post("/import-tags-csv")
async def import_tags_csv(
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Import tags from CSV file (two-pass, non-streaming)"""
    
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
        
    try:
        contents = await file.read()
        csv_text = contents.decode('utf-8')
        
        result = import_tags_csv_logic(csv_text, db)
        return result
    
    except Exception as e:
        db.rollback()
        print(f"Error during import: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error importing CSV: {str(e)}")

@router.get("/tag-stats")
async def get_tag_stats(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Get tag statistics"""
    from ..models import Tag, TagAlias
    
    total_tags = db.query(Tag).count()
    total_aliases = db.query(TagAlias).count()
    
    return {
        "total_tags": total_tags,
        "total_aliases": total_aliases,
    }

@router.get("/search-tags")
async def search_tags(
    q: str,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Search tags"""
    from ..models import Tag
    
    tags = db.query(Tag).filter(
        Tag.name.ilike(f"%{q}%")
    ).order_by(Tag.post_count.desc()).limit(50).all()
    
    return {"tags": tags}

@router.delete("/clear-tags")
async def clear_all_tags(
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Clear all tags"""
    from ..models import Tag, TagAlias
    
    try:
        db.query(TagAlias).delete()
        db.query(Tag).delete()
        
        db.commit()
        
        return {"message_key": "notifications.admin.tags_cleared"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Error clearing tags: {str(e)}")
    
@router.delete("/tags/{tag_id}")
async def delete_tag(
    tag_id: int,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Delete a single tag and its aliases"""
    from ..models import Tag
    
    try:
        tag = db.query(Tag).filter(Tag.id == tag_id).first()
        
        if not tag:
            raise HTTPException(status_code=404, detail="error_tag_not_found")
        
        tag_name = tag.name
        
        # Delete the tag (aliases will be deleted automatically due to CASCADE)
        db.delete(tag)
        db.commit()
        
        # Also delete from shared database if enabled
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
        
        return {"message_key": "notifications.admin.tag_deleted", "tag_name": tag_name}
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Error deleting tag: {str(e)}")
    
@router.get("/themes")
async def get_themes():
    """Get all available themes"""
    themes = theme_registry.get_all_themes()
    return {
        "themes": [theme.to_dict() for theme in themes],
        "current_theme": settings.CURRENT_THEME
    }

@router.get("/current-theme")
async def get_current_theme():
    """Get current theme (public endpoint)"""
    theme = theme_registry.get_theme(settings.CURRENT_THEME)
    if theme:
        return theme.to_dict()
    # Fallback to default dark
    return theme_registry.get_theme("default_dark").to_dict()

@router.get("/languages")
async def get_languages():
    """Get all available languages"""
    from ..translations import language_registry
    languages = language_registry.get_all_languages()
    return {
        "languages": [lang.to_dict() for lang in languages],
        "current_language": settings.CURRENT_LANGUAGE
    }

@router.get("/translations")
async def get_translations(lang: str = None):
    """Get translation strings for the current or specified language"""
    from ..translations import translation_helper
    target_lang = lang or settings.CURRENT_LANGUAGE
    return translation_helper.get_translations(target_lang)

@router.get("/check-alias")
async def check_alias(
    name: str,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Check if a name exists as an alias"""
    alias = db.query(TagAlias).filter(TagAlias.alias_name == name.lower()).first()
    return {"exists": alias is not None}

@router.post("/bulk-create-tags")
async def bulk_create_tags(
    data: dict,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Bulk create tags"""
    tags_to_create = data.get('tags', [])
    
    created = 0
    skipped = 0
    errors = []
    
    for tag_data in tags_to_create:
        try:
            tag_name = tag_data['name'].lower().strip()
            if not tag_name:
                continue

            category = tag_data.get('category', 'general')
            
            existing = db.query(Tag).filter(Tag.name == tag_name).first()
            if existing:
                skipped += 1
                continue
            
            alias = db.query(TagAlias).filter(TagAlias.alias_name == tag_name).first()
            if alias:
                skipped += 1
                continue
            
            tag = Tag(name=tag_name, category=category)
            db.add(tag)
            created += 1
            
        except Exception as e:
            errors.append({"key": "notifications.admin.error_creating_tag", "tag": tag_data.get('name'), "error": str(e)})
            
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
        
    return {
        "message_key": "notifications.admin.bulk_tag_creation_complete",
        "created": created,
        "skipped": skipped,
        "errors": errors
    }

@router.get("/backup/tags")
async def backup_tags(
    current_user: User = Depends(get_current_admin_user)
):
    """
    Export all tags and aliases as a CSV file compatible with the import format.
    """
    from ..database import SessionLocal
    
    def csv_generator():
        db = SessionLocal()
        try:
            csv_stream = generate_tags_csv_stream(db)
            yield from csv_stream
        finally:
            db.close()
            
    return StreamingResponse(
        csv_generator(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=blombooru_tags.csv"}
    )

@router.get("/backup/media")
async def backup_media(
    current_user: User = Depends(get_current_admin_user),
):
    """Download a ZIP backup of all media files"""
    files_gen = get_media_files_generator()
    zip_stream = stream_zip_generator(files_gen)
    
    return StreamingResponse(
        zip_stream,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=blombooru_media_backup.zip"}
    )

@router.get("/backup/full")
async def backup_full_db(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Download a full backup (Media + Database JSON)"""
    
    # 1. Generate Metadata
    dump_data = generate_tags_dump(db)
    
    from sqlalchemy.orm import selectinload
    from ..models import Media, Album
    
    # Export Albums
    album_list = []
    media_list = [] # Initialize media list
    albums_query = db.query(Album).all()
    
    for album in albums_query:
        media_hashes = [m.hash for m in album.media]
        child_ids = [child.id for child in album.children]
        
        album_list.append({
            "id": album.id,
            "name": album.name,
            "created_at": album.created_at.isoformat() if album.created_at else None,
            "last_modified": album.last_modified.isoformat() if album.last_modified else None,
            "media_hashes": media_hashes,
            "child_ids": child_ids
        })
    
    # Prepare Metadata    
    media_query = db.query(Media).options(selectinload(Media.parent)).all()
    
    for m in media_query:
        try:
            media_path = Path(m.path)
            if settings.ORIGINAL_DIR in media_path.parents or str(settings.ORIGINAL_DIR) in str(media_path):
                try:
                    rel_path = media_path.relative_to(settings.ORIGINAL_DIR)
                    archive_path = f"media/{rel_path}"
                except ValueError:
                    archive_path = f"media/{m.filename}"
            else:
                archive_path = f"media/{m.filename}"
        except Exception as e:
            print(f"Warning: Could not construct archive path for {m.filename}: {e}")
            archive_path = f"media/{m.filename}"
        
        media_list.append({
            "filename": m.filename,
            "hash": m.hash,
            "file_type": m.file_type.value,
            "mime_type": m.mime_type,
            "file_size": m.file_size,
            "width": m.width,
            "height": m.height,
            "duration": m.duration,
            "rating": m.rating.value if m.rating else 'safe',
            "tags": [t.name for t in m.tags], 
            "archive_path": archive_path,
            "parent_hash": m.parent.hash if m.parent else None
        })
        
    backup_metadata = {
        "version": 1,
        "type": "full_backup",
        "media": media_list,
        "albums": album_list
    }
    
    # 2. Prepare Generator
    def mixed_generator():
        from ..database import SessionLocal
        stream_db = SessionLocal()
        tmp_csv_path = None
        tmp_json_path = None
        
        try:
            print("Starting full backup generation...")
            
            # A. tags.csv
            print("Generating tags.csv...")
            try:
                with tempfile.NamedTemporaryFile(delete=False, mode='w', encoding='utf-8') as tmp_csv:
                    csv_gen = generate_tags_csv_stream(stream_db)
                    for chunk in csv_gen:
                        tmp_csv.write(chunk)
                    tmp_csv_path = Path(tmp_csv.name)
                print(f"tags.csv generated: {tmp_csv_path}")
            except Exception as e:
                print(f"Error generating tags.csv: {e}")
                import traceback
                traceback.print_exc()
                raise
                
            # B. backup.json (Media metadata)
            print("Generating backup.json...")
            try:
                with tempfile.NamedTemporaryFile(delete=False, mode='wb') as tmp_json:
                    tmp_json.write(json.dumps(backup_metadata, indent=2).encode('utf-8'))
                    tmp_json_path = Path(tmp_json.name)
                print(f"backup.json generated: {tmp_json_path}")
            except Exception as e:
                print(f"Error generating backup.json: {e}")
                import traceback
                traceback.print_exc()
                raise
                
            try:
                print("Yielding tags.csv to ZIP stream...")
                yield ("tags.csv", tmp_csv_path)
                
                print("Yielding backup.json to ZIP stream...")
                yield ("backup.json", tmp_json_path)
                
                # C. Media files
                print("Yielding media files to ZIP stream...")
                media_gen = get_media_files_generator()
                file_count = 0
                for item in media_gen:
                    yield item
                    file_count += 1
                    if file_count % 100 == 0:
                        print(f"Processed {file_count} media files...")
                print(f"All {file_count} media files yielded to ZIP stream")
                
            except Exception as e:
                print(f"Error during ZIP streaming: {e}")
                import traceback
                traceback.print_exc()
                raise
            finally:
                # Cleanup temp files
                if tmp_csv_path and tmp_csv_path.exists():
                    try:
                        os.unlink(tmp_csv_path)
                        print("Cleaned up tags.csv temp file")
                    except Exception as e:
                        print(f"Error cleaning up tags.csv: {e}")
                        
                if tmp_json_path and tmp_json_path.exists():
                    try:
                        os.unlink(tmp_json_path)
                        print("Cleaned up backup.json temp file")
                    except Exception as e:
                        print(f"Error cleaning up backup.json: {e}")
        except Exception as e:
            print(f"Fatal error in mixed_generator: {e}")
            import traceback
            traceback.print_exc()
            raise
        finally:
            stream_db.close()
            print("Backup generation complete, database session closed")
                
    zip_stream = stream_zip_generator(mixed_generator())
    
    return StreamingResponse(
        zip_stream,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=blombooru_full_backup.zip"}
    )

@router.post("/import/full")
async def import_full(
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Import a full backup ZIP"""
    
    # Use the spooled file directly to prevent duplication
    try:
        result = import_full_backup(file.file, db)
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"Import failed: {str(e)}")


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
    # Generate key
    raw_key = generate_api_key()
    key_hash = hash_api_key(raw_key)
    key_prefix = raw_key[:12] # e.g. "blom_abcd12"
    
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
        
        # Return the raw key only this one time
        return {
            "id": new_key.id,
            "key": raw_key,
            "key_prefix": new_key.key_prefix,
            "name": new_key.name,
            "created_at": new_key.created_at
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create API key: {str(e)}")

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
        raise HTTPException(status_code=500, detail=f"Failed to revoke API key: {str(e)}")

@router.post("/test-shared-tag-db")
async def test_shared_tag_db(data: dict, current_user: User = Depends(require_admin_mode)):
    """Test shared tag database connection"""
    from sqlalchemy import create_engine as sqlalchemy_create_engine, text
    
    try:
        host = data.get('host', 'shared-tag-db')
        port = data.get('port', 5432)
        name = data.get('name', 'shared_tags')
        user = data.get('user', 'postgres')
        password = data.get('password', '')
        
        if password == "***":
            password = settings.SHARED_TAG_DB_PASSWORD
        
        test_url = f"postgresql://{user}:{password}@{host}:{port}/{name}"
        
        test_engine = sqlalchemy_create_engine(
            test_url, 
            pool_pre_ping=True,
            connect_args={"connect_timeout": 5}
        )
        with test_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        test_engine.dispose()
        
        return {"success": True, "message": "Connection successful"}
    except Exception as e:
        return {"success": False, "message": str(e)}

@router.get("/shared-tags/status")
async def get_shared_tags_status(
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Get shared tag database status"""
    from ..database import is_shared_db_available, get_shared_db_error, get_shared_db
    from ..models import Tag, TagAlias
    
    status = {
        "enabled": settings.SHARED_TAGS_ENABLED,
        "connected": is_shared_db_available(),
        "error": get_shared_db_error() if not is_shared_db_available() else None,
        "config": {
            "host": settings.SHARED_TAG_DB_HOST,
            "port": settings.SHARED_TAG_DB_PORT,
            "name": settings.SHARED_TAG_DB_NAME,
            "user": settings.SHARED_TAG_DB_USER
        }
    }
    
    # Get local tag counts
    status["local_tags"] = db.query(Tag).count()
    status["local_aliases"] = db.query(TagAlias).count()
    
    # Get shared tag counts if connected
    if is_shared_db_available():
        shared_db_gen = get_shared_db()
        shared_db = next(shared_db_gen, None)
        try:
            if shared_db:
                from ..shared_tag_models import SharedTag, SharedTagAlias
                status["shared_tags"] = shared_db.query(SharedTag).count()
                status["shared_aliases"] = shared_db.query(SharedTagAlias).count()
        finally:
            if shared_db:
                try:
                    next(shared_db_gen, None)
                except StopIteration:
                    pass
    
    return status

@router.post("/shared-tags/sync")
async def sync_shared_tags(
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Trigger manual sync with shared tag database"""
    from ..database import is_shared_db_available, get_shared_db, reconnect_shared_db
    from ..services.shared_tags import SharedTagService
    from ..utils.cache import invalidate_tag_cache
    import asyncio
    
    if not settings.SHARED_TAGS_ENABLED:
        raise HTTPException(status_code=400, detail="Shared tags not enabled")
    
    # Try to reconnect if not available
    if not is_shared_db_available():
        reconnect_shared_db()
        
    if not is_shared_db_available():
        raise HTTPException(status_code=503, detail="Shared tag database not available")
    
    shared_db_gen = get_shared_db()
    shared_db = next(shared_db_gen, None)
    
    try:
        if not shared_db:
            raise HTTPException(status_code=503, detail="Could not get shared database session")
        
        service = SharedTagService(db, shared_db)
        result = await asyncio.to_thread(service.full_sync)
        invalidate_tag_cache()
        
        return {
            "success": len(result.errors) == 0,
            "tags_imported": result.tags_imported,
            "tags_exported": result.tags_exported,
            "aliases_imported": result.aliases_imported,
            "aliases_exported": result.aliases_exported,
            "conflicts_resolved": result.conflicts_resolved,
            "errors": result.errors
        }
    finally:
        if shared_db:
            try:
                next(shared_db_gen, None)
            except StopIteration:
                pass

@router.post("/shared-tags/reconnect")
async def reconnect_shared_tags(
    current_user: User = Depends(require_admin_mode)
):
    """Attempt to reconnect to the shared tag database"""
    from ..database import reconnect_shared_db, is_shared_db_available, get_shared_db_error, init_shared_db
    
    if not settings.SHARED_TAGS_ENABLED:
        raise HTTPException(status_code=400, detail="Shared tags not enabled")
    
    reconnect_shared_db()
    
    if is_shared_db_available():
        init_shared_db()
        return {"success": True, "message": "Reconnected successfully"}
    else:
        return {"success": False, "message": get_shared_db_error()}

