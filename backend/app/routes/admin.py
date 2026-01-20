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
        
        temp_db_url = f"postgresql://{data.database.user}:{data.database.password}@{data.database.host}:{data.database.port}/{data.database.name}"
        temp_engine = sqlalchemy_create_engine(temp_db_url, pool_pre_ping=True)
        new_session_local = sessionmaker(autocommit=False, autoflush=False, bind=temp_engine)
        
        database.Base.metadata.create_all(bind=temp_engine)
        print("✓ Database schema created")
        
        print("3. Creating admin user...")
        db = new_session_local()
        try:
            try:
                password_hash = get_password_hash(data.admin_password)
                print(f"✓ Password hashed successfully")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to hash password: {str(e)}")
            
            admin = User(
                username=data.admin_username,
                password_hash=password_hash
            )
            db.add(admin)
            
            db.commit()
            print("✓ Admin user created")
            
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
        print(f"✗ Error initializing database: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to initialize database: {str(e)}")
    
    return {"message": "Onboarding completed successfully"}

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
        
        return {"message": "Password updated successfully"}
        
    except Exception as e:
        db.rollback()
        print(f"Error updating password: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update password: {str(e)}")

@router.post("/update-admin-username")
async def update_admin_username(
    data: dict,
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
        
        response.set_cookie(
            key="admin_token",
            value=access_token,
            httponly=True,
            max_age=43200 * 60,
            samesite="lax"
        )
        
        return {
            "message": "Username updated successfully",
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
                errors.append(f"Row {row_num}: Tag '{tag_name[:50]}...' too long ({len(tag_name)} chars)")
                continue
            
            try:
                category_num = int(row[1])
            except (ValueError, IndexError):
                errors.append(f"Row {row_num}: Invalid category")
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
                    errors.append(f"Batch error at row {row_num}: {str(e)}")
                    tags_to_create = []
                    existing_tags = {tag.name: tag for tag in db.query(Tag).all()}
        
        except Exception as e:
            errors.append(f"Row {row_num}: {str(e)}")
            continue
    
    # Final commit for pass 1
    try:
        if tags_to_create:
            db.bulk_insert_mappings(Tag, tags_to_create)
        db.commit()
    except Exception as e:
        db.rollback()
        errors.append(f"Final batch error in pass 1: {str(e)}")
    
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
                    errors.append(f"Alias batch integrity error at row {rows_processed}: {str(e)}")
                    aliases_to_create = []
                    existing_aliases = {alias.alias_name for alias in db.query(TagAlias.alias_name).all()}
                except Exception as e:
                    db.rollback()
                    errors.append(f"Alias batch error at row {rows_processed}: {str(e)}")
                    aliases_to_create = []
                    existing_aliases = {alias.alias_name for alias in db.query(TagAlias.alias_name).all()}
        
        except Exception as e:
            errors.append(f"Pass 2, tag '{tag_name}': {str(e)}")
            continue
    
    # Final commit for pass 2
    try:
        if aliases_to_create:
            db.bulk_insert_mappings(TagAlias, aliases_to_create)
        db.commit()
    except Exception as e:
        db.rollback()
        errors.append(f"Final batch error in pass 2: {str(e)}")
    
    print(f"Pass 2 complete: {aliases_created} aliases created, {skipped_long_aliases} skipped")
    
    return {
        "message": "Tags imported successfully",
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
        
        return {"message": "All tags cleared successfully"}
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
            raise HTTPException(status_code=404, detail="Tag not found")
        
        tag_name = tag.name
        
        # Delete the tag (aliases will be deleted automatically due to CASCADE)
        db.delete(tag)
        db.commit()
        
        return {"message": f"Tag '{tag_name}' deleted successfully"}
    
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
            errors.append(f"Error creating tag '{tag_data.get('name')}': {str(e)}")
            
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
        
    return {
        "message": "Bulk tag creation complete",
        "created": created,
        "skipped": skipped,
        "errors": errors
    }

@router.get("/backup/tags")
async def backup_tags(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    Export all tags and aliases as a CSV file compatible with the import format.
    """
    csv_stream = generate_tags_csv_stream(db)
    
    return StreamingResponse(
        csv_stream,
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
    media_query = db.query(Media).options(selectinload(Media.children)).yield_per(1000)
    
    for m in media_query:
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
            "archive_path": str(Path("media") / Path(m.path).relative_to("media/original")) if "media/original" in m.path else f"media/{m.filename}",
            "parent_hash": m.children.hash if m.children else None
        })
        
    backup_metadata = {
        "version": 1,
        "type": "full_backup",
        "media": media_list,
        "albums": album_list
    }
    
    # 2. Prepare Generator
    def mixed_generator():
        # A. tags.csv
        with tempfile.NamedTemporaryFile(delete=False, mode='w', encoding='utf-8') as tmp_csv:
            csv_gen = generate_tags_csv_stream(db)
            for chunk in csv_gen:
                tmp_csv.write(chunk)
            tmp_csv_path = Path(tmp_csv.name)
            
        # B. backup.json (Media metadata)
        with tempfile.NamedTemporaryFile(delete=False, mode='wb') as tmp_json:
            tmp_json.write(json.dumps(backup_metadata, indent=2).encode('utf-8'))
            tmp_json_path = Path(tmp_json.name)
            
        try:
            yield ("tags.csv", tmp_csv_path)
            yield ("backup.json", tmp_json_path)
            
            # C. Media files
            media_gen = get_media_files_generator()
            yield from media_gen
            
        finally:
            if tmp_csv_path.exists():
                os.unlink(tmp_csv_path)
            if tmp_json_path.exists():
                os.unlink(tmp_json_path)
                
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
        return {"message": "API key revoked successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to revoke API key: {str(e)}")
