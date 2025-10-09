from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError, IntegrityError
from sqlalchemy import create_engine as sqlalchemy_create_engine, text
from typing import Optional
from datetime import timedelta
import csv
import io
from ..database import get_db, init_db
from ..auth import get_password_hash, create_access_token, get_current_admin_user, require_admin_mode
from ..models import User, Tag, TagAlias
from ..schemas import OnboardingData, SettingsUpdate, UserLogin, Token
from ..config import settings
from ..utils.file_scanner import scan_for_new_media
from ..themes import theme_registry

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
        
        # Create admin user
        print("3. Creating admin user...")
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
            
            # Commit everything
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

@router.get("/media-stats")
async def get_media_stats(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Get media statistics"""
    from ..models import Media
    from sqlalchemy import func
    
    # Get total count
    total_media = db.query(Media).count()
    
    # Get counts by file type
    total_images = db.query(Media).filter(Media.file_type == 'image').count()
    total_gifs = db.query(Media).filter(Media.file_type == 'gif').count()
    total_videos = db.query(Media).filter(Media.file_type == 'video').count()
    
    return {
        "total_media": total_media,
        "total_images": total_images,
        "total_gifs": total_gifs,
        "total_videos": total_videos,
    }

@router.post("/import-tags-csv")
async def import_tags_csv(
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Import tags from CSV file (two-pass, non-streaming)"""
    import csv
    import io
    from ..models import Tag, TagAlias
    
    # Read CSV content
    contents = await file.read()
    csv_text = contents.decode('utf-8')
    
    # Category mapping
    category_map = {
        0: 'general',
        1: 'artist',
        3: 'copyright',
        4: 'character',
        5: 'meta'
    }
    
    # Limits based on database schema
    MAX_TAG_LENGTH = 255
    MAX_ALIAS_LENGTH = 255
    
    tags_created = 0
    aliases_created = 0
    tags_updated = 0
    errors = []
    skipped_long_tags = 0
    skipped_long_aliases = 0
    
    BATCH_SIZE = 1000
    
    try:
        # PASS 1: Import tags only
        print("Pass 1: Importing tags...")
        csv_reader = csv.reader(io.StringIO(csv_text))
        
        tag_data = []  # Store (tag_name, category, aliases_str) for pass 2
        tags_to_create = []
        rows_processed = 0
        
        # Get existing tags
        existing_tags = {tag.name: tag for tag in db.query(Tag).all()}
        
        for row_num, row in enumerate(csv_reader, 1):
            try:
                if len(row) < 2:
                    continue
                
                tag_name = row[0].strip().lower()
                if not tag_name:
                    continue
                
                # Skip tags that are too long
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
                
                # Store for pass 2
                tag_data.append((tag_name, category, aliases_str))
                
                # Check if tag exists
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
                
                # Commit in batches
                if rows_processed % BATCH_SIZE == 0:
                    try:
                        if tags_to_create:
                            db.bulk_insert_mappings(Tag, tags_to_create)
                            tags_to_create = []
                        
                        db.commit()
                        print(f"Pass 1: Processed {rows_processed} tags...")
                        
                        # Clear SQLAlchemy cache
                        db.expire_all()
                    except Exception as e:
                        db.rollback()
                        errors.append(f"Batch error at row {row_num}: {str(e)}")
                        tags_to_create = []
                        # Reload existing tags after rollback
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
        
        print(f"Pass 1 complete: {tags_created} tags created, {tags_updated} updated, {skipped_long_tags} skipped (too long)")
        
        # Clear memory
        existing_tags = None
        tags_to_create = None
        db.expire_all()
        
        # PASS 2: Import aliases
        print("Pass 2: Importing aliases...")
        
        # Build tag name -> ID mapping (load in chunks to avoid memory issues)
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
        
        # Get existing aliases
        existing_aliases = {alias.alias_name for alias in db.query(TagAlias.alias_name).all()}
        
        aliases_to_create = []
        rows_processed = 0
        
        for tag_name, category, aliases_str in tag_data:
            try:
                if not aliases_str or tag_name not in tag_map:
                    continue
                
                tag_id = tag_map[tag_name]
                
                # Parse aliases
                alias_names = set()
                for a in aliases_str.split(','):
                    alias = a.strip().lower()
                    if not alias or alias == tag_name:
                        continue
                    
                    # Skip aliases that are too long
                    if len(alias) > MAX_ALIAS_LENGTH:
                        skipped_long_aliases += 1
                        continue
                    
                    alias_names.add(alias)
                
                # Add to batch
                for alias_name in alias_names:
                    if alias_name not in existing_aliases:
                        aliases_to_create.append({
                            'alias_name': alias_name,
                            'target_tag_id': tag_id
                        })
                        existing_aliases.add(alias_name)
                        aliases_created += 1
                
                rows_processed += 1
                
                # Commit in batches
                if rows_processed % BATCH_SIZE == 0:
                    try:
                        if aliases_to_create:
                            db.bulk_insert_mappings(TagAlias, aliases_to_create)
                            aliases_to_create = []
                        
                        db.commit()
                        print(f"Pass 2: Processed {rows_processed} tags, created {aliases_created} aliases...")
                        
                        # Clear SQLAlchemy cache
                        db.expire_all()
                    except IntegrityError as e:
                        db.rollback()
                        errors.append(f"Alias batch integrity error at row {rows_processed}: {str(e)}")
                        aliases_to_create = []
                        # Reload existing aliases after rollback
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
        
        print(f"Pass 2 complete: {aliases_created} aliases created, {skipped_long_aliases} skipped (too long)")
        
        # Return result
        result = {
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
        # Delete all tag relationships first
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
        # Find the tag
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
