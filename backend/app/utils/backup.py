import csv
import io
import json
import os
import shutil
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Set, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from ..config import settings
from ..enums import FileTypeEnum, RatingEnum, TagCategoryEnum
from ..models import (Album, Media, Tag, TagAlias, TagImplication,
                      blombooru_album_hierarchy, blombooru_album_media,
                      blombooru_media_tags)
from ..routes.media import update_tag_counts
from ..services.booru import normalize_domain, upsert_booru_config
from ..utils.cache import (invalidate_album_cache, invalidate_media_cache,
                           invalidate_tag_cache)
from ..utils.logger import logger
from ..utils.thumbnail_generator import generate_thumbnail, THUMBNAIL_EXT
from ..utils.transcoder import transcode_media_if_needed

# Constants for batch processing
DB_BATCH_SIZE = 5000

CATEGORY_REVERSE_MAP = {
    'general': 0,
    'artist': 1,
    'copyright': 3,
    'character': 4,
    'meta': 5
}

CATEGORY_MAP = {
    0: 'general',
    1: 'artist',
    3: 'copyright',
    4: 'character',
    5: 'meta'
}

def generate_tags_csv_stream(db: Session) -> Generator[str, None, None]:
    """Generates a CSV stream of tags and their aliases."""
    aliases_map: Dict[int, List[str]] = {}
    aliases = db.query(TagAlias).options(joinedload(TagAlias.target_tag)).all()
    for alias in aliases:
        if alias.target_tag_id not in aliases_map:
            aliases_map[alias.target_tag_id] = []
        aliases_map[alias.target_tag_id].append(alias.alias_name)

    tags_query = db.query(Tag).order_by(Tag.id).yield_per(1000)

    for tag in tags_query:
        alias_list = aliases_map.get(tag.id, [])
        alias_str = ",".join(alias_list) if alias_list else ""

        tag_cat_str = tag.category.value if hasattr(tag.category, 'value') else str(tag.category)
        cat_val = CATEGORY_REVERSE_MAP.get(tag_cat_str, 0)

        out = io.StringIO()
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow([tag.name, cat_val, tag.post_count, alias_str])
        yield out.getvalue()

def generate_tags_dump(db: Session) -> dict:
    """
    Generates a dictionary containing all tags and aliases.
    """
    # Fetch tags
    tags_query = db.query(Tag).order_by(Tag.id).yield_per(1000)
    tags_list = []
    for tag in tags_query:
        cat = tag.category.value if hasattr(tag.category, 'value') else str(tag.category)
        tags_list.append({
            "name": tag.name,
            "category": cat,
            "post_count": tag.post_count
        })

    aliases_query = db.query(TagAlias).options(joinedload(TagAlias.target_tag)).yield_per(1000)
    aliases_list = []
    for alias in aliases_query:
        if alias.target_tag:
            aliases_list.append({
                "alias_name": alias.alias_name,
                "target_tag": alias.target_tag.name
            })

    return {
        "version": 1,
        "type": "tags_dump",
        "tags": tags_list,
        "aliases": aliases_list
    }

class ZipStream:
    """
    A helper to stream a ZIP file without creating a temporary file on disk.
    Only supports STORE method (no compression) for simplicity and speed with large files.
    """
    def __init__(self):
        self.queue = io.BytesIO()
        self.offset = 0

    def write(self, data: bytes) -> int:
        self.queue.write(data)
        self.offset += len(data)
        return len(data)

    def tell(self) -> int:
        return self.offset

    def flush(self):
        pass

    def get_data(self) -> bytes:
        data = self.queue.getvalue()
        self.queue.truncate(0)
        self.queue.seek(0)
        return data

def stream_zip_generator(files_to_zip: Generator[Tuple[str, Path], None, None]) -> Generator[bytes, None, None]:
    """
    Generates a ZIP stream.
    files_to_zip: Generator yielding (arcname, absolute_path)
    """
    mem_file = ZipStream()
    with zipfile.ZipFile(mem_file, 'w', zipfile.ZIP_STORED) as zf:
        for arcname, path in files_to_zip:
            try:
                if not path.exists() or not path.is_file():
                    continue

                z_info = zipfile.ZipInfo.from_file(path, arcname)
                z_info.compress_type = zipfile.ZIP_STORED

                with zf.open(z_info, 'w') as dest:
                    with open(path, 'rb') as src:
                        while chunk := src.read(1024 * 1024):  # 1MB chunks
                            dest.write(chunk)
                            yield mem_file.get_data()
                yield mem_file.get_data()
            except Exception as e:
                logger.warning(f"Error streaming file {path} to ZIP: {e}")
                continue
    yield mem_file.get_data()

def get_media_files_generator() -> Generator[Tuple[str, Path], None, None]:
    """Yields all media files for backup, skipping hidden/temporary files."""
    media_dir = settings.ORIGINAL_DIR
    if not media_dir.exists():
        return
    for root, _, files in os.walk(media_dir):
        for name in files:
            if name.startswith(".") or name.endswith(".tmp") or name == ".gitkeep":
                continue
            abs_path = Path(root) / name
            try:
                rel_path = abs_path.relative_to(media_dir)
                yield (f"media/{rel_path}", abs_path)
            except ValueError:
                continue

def get_custom_theme_files_generator() -> Generator[Tuple[str, Path], None, None]:
    """Yields all custom theme CSS files for backup."""
    from ..custom_themes import custom_theme_manager
    themes_dir = custom_theme_manager.custom_themes_dir
    if not themes_dir.exists():
        return
    for css_file in themes_dir.glob("*.css"):
        if css_file.is_file():
            yield (f"custom_themes/{css_file.name}", css_file)

def _safe_extract_media_file(zf: zipfile.ZipFile, zip_entry_name: str, rel_dest_path: str) -> Path:
    """Extracts a media file into ORIGINAL_DIR with path traversal protection."""
    base_dir = settings.ORIGINAL_DIR.resolve()
    target_path = (base_dir / rel_dest_path).resolve()

    # Path traversal / Zip Slip protection
    if not (target_path == base_dir or base_dir in target_path.parents):
        raise ValueError(f"Illegal path in zip archive: {zip_entry_name}")

    target_path.parent.mkdir(parents=True, exist_ok=True)

    if target_path.exists():
        stem = target_path.stem
        suffix = target_path.suffix
        target_path = target_path.with_name(f"{stem}_{uuid.uuid4().hex[:8]}{suffix}")

    with zf.open(zip_entry_name) as source, open(target_path, "wb") as target:
        shutil.copyfileobj(source, target)

    return target_path

def import_full_backup(zip_source, db: Session) -> dict:
    """Imports a full backup ZIP archive containing tags.csv, backup.json,
    custom themes, media files, albums, implications, booru config, and UI settings.
    """
    if not zipfile.is_zipfile(zip_source):
        raise HTTPException(status_code=400, detail="Invalid ZIP file")

    with zipfile.ZipFile(zip_source, 'r') as zf:
        namelist = zf.namelist()
        backup_data: Dict[str, Any] = {}
        tag_import_stats: Dict[str, Any] = {}

        # 1. Handle tags.csv using existing CSV import logic
        if 'tags.csv' in namelist:
            from ..routes.admin.tags import import_tags_csv_logic
            with zf.open('tags.csv') as f:
                content = f.read().decode('utf-8')
                tag_import_stats = import_tags_csv_logic(content, db)

        # 2. Check for backup.json
        if 'backup.json' in namelist:
            try:
                with zf.open('backup.json') as f:
                    backup_data = json.load(f)
            except Exception as e:
                logger.error(f"Error reading backup.json: {e}", exc_info=True)
                raise HTTPException(status_code=400, detail=f"Error parsing backup.json: {e}")

        # If neither tags.csv nor backup.json exists, invalid backup
        if 'tags.csv' not in namelist and not backup_data:
            raise HTTPException(status_code=400, detail="No valid backup data found in archive")

        # If backup.json has tags/aliases but tags.csv wasn't present, import from JSON
        if 'tags.csv' not in namelist and ('tags' in backup_data or 'aliases' in backup_data):
            import_tags_logical(db, backup_data.get('tags', []), backup_data.get('aliases', []))

        # 3. Import Media
        media_list = backup_data.get('media', [])
        media_stats = {"imported": 0, "skipped": 0, "total": len(media_list)}
        if media_list:
            media_stats = import_media_logical(db, zf, media_list)
            
        # 4. Import Albums
        albums_list = backup_data.get('albums', [])
        album_stats = {"albums_created": 0, "albums_existing": 0, "links_created": 0}
        if albums_list:
            album_stats = import_albums_logical(db, albums_list)

        # 5. Import Tag Implications
        implications_list = backup_data.get('tag_implications', [])
        implications_stats = {"imported": 0, "skipped": 0}
        if implications_list:
            implications_stats = import_tag_implications_logical(db, implications_list)

        # 6. Import Booru Config
        booru_configs_list = backup_data.get('booru_config', [])
        booru_stats = {"imported": 0}
        if booru_configs_list:
            booru_stats = import_booru_config_logical(db, booru_configs_list)

        # 7. Import Custom Themes
        custom_themes_list = backup_data.get('custom_themes', [])
        theme_stats = import_custom_themes_logical(db, zf, custom_themes_list)

        # 8. Import Settings
        settings_data = backup_data.get('settings')
        settings_stats = {"imported": False}
        if settings_data and isinstance(settings_data, dict):
            settings_stats = import_settings_logical(db, settings_data)

    # Invalidate all caches
    invalidate_media_cache()
    invalidate_tag_cache()
    invalidate_album_cache()

    return {
        "message": "Import completed successfully",
        "stats": {
            "tags": tag_import_stats,
            "media": media_stats,
            "albums": album_stats,
            "tag_implications": implications_stats,
            "booru_config": booru_stats,
            "custom_themes": theme_stats,
            "settings": settings_stats
        }
    }

def import_tags_logical(db: Session, tags: List[dict], aliases: List[dict]):
    """Imports tags and aliases from JSON format."""
    existing_tags = {t.name: t for t in db.query(Tag).all()}
    tags_to_create = []

    for tag_data in tags:
        name = tag_data.get('name', '').strip().lower()
        if name and name not in existing_tags:
            cat = tag_data.get('category', 'general')
            tags_to_create.append({
                'name': name,
                'category': cat,
                'post_count': tag_data.get('post_count', 0)
            })

    if tags_to_create:
        for i in range(0, len(tags_to_create), DB_BATCH_SIZE):
            chunk = tags_to_create[i:i+DB_BATCH_SIZE]
            db.bulk_insert_mappings(Tag, chunk)
            db.commit()
  
    db.expire_all()
    existing_tags = {t.name: t for t in db.query(Tag).all()}
    existing_aliases = {a.alias_name for a in db.query(TagAlias.alias_name).all()}
    aliases_to_create = []

    for alias_data in aliases:
        name = alias_data.get('alias_name', '').strip().lower()
        target_name = alias_data.get('target_tag', '').strip().lower()

        if name and name not in existing_aliases and name not in existing_tags and target_name in existing_tags and name != target_name:
            aliases_to_create.append({
                'alias_name': name,
                'target_tag_id': existing_tags[target_name].id
            })
            existing_aliases.add(name)

    if aliases_to_create:
        for i in range(0, len(aliases_to_create), DB_BATCH_SIZE):
            chunk = aliases_to_create[i:i+DB_BATCH_SIZE]
            db.bulk_insert_mappings(TagAlias, chunk)
            db.commit()

def import_media_logical(db: Session, zf: zipfile.ZipFile, media_list: List[dict]) -> dict:
    """Imports media files and metadata with all database fields preserved."""
    logger.info(f"Starting logical media import for {len(media_list)} items...")
    
    existing_hashes = {m.hash for m in db.query(Media.hash).all()}
    logger.info(f"Found {len(existing_hashes)} existing media hashes in DB.")
    
    all_tags = {t.name: t.id for t in db.query(Tag.name, Tag.id).all()}
    all_aliases = {a.alias_name: a.target_tag_id for a in db.query(TagAlias.alias_name, TagAlias.target_tag_id).all()}
    namelist = zf.namelist()
    namelist_set = set(namelist)
    
    imported_count = 0
    skipped_count = 0
    parent_links: List[Tuple[int, str]] = []
    affected_tag_ids: Set[int] = set()
    
    for media_data in media_list:
        file_hash = media_data.get('hash')
        if not file_hash:
            continue

        if file_hash in existing_hashes:
            skipped_count += 1
            continue

        original_filename = media_data.get('filename') or f"{file_hash}"
        archive_path = media_data.get('archive_path')

        # Find entry in zip
        zip_entry_name = None
        if archive_path and archive_path in namelist_set:
            zip_entry_name = archive_path
        else:
            # Fallback by filename in media folder
            candidates = [n for n in namelist if n.startswith('media/') and Path(n).name == original_filename]
            if candidates:
                zip_entry_name = candidates[0]
            elif f"media/{original_filename}" in namelist_set:
                zip_entry_name = f"media/{original_filename}"

        if not zip_entry_name:
            logger.warning(f"Media file not found in archive: {archive_path or original_filename}")
            continue

        # Determine relative extraction path inside ORIGINAL_DIR
        if zip_entry_name.startswith("media/"):
            rel_dest_path = zip_entry_name[len("media/"):]
        else:
            rel_dest_path = Path(zip_entry_name).name

        try:
            target_path = _safe_extract_media_file(zf, zip_entry_name, rel_dest_path)
        except Exception as e:
            logger.error(f"Failed to extract {zip_entry_name}: {e}")
            continue

        # File type resolution
        file_type_str = media_data.get('file_type', 'image')
        file_type_enum = FileTypeEnum.image
        if file_type_str == 'video':
            file_type_enum = FileTypeEnum.video
        elif file_type_str == 'gif':
            file_type_enum = FileTypeEnum.gif
            
        # Transcode if needed
        transcoded_file = transcode_media_if_needed(target_path)
        transcoded_rel_path = str(transcoded_file.relative_to(settings.BASE_DIR)) if transcoded_file else None

        # Generate thumbnail
        thumb_filename = f"{target_path.stem}{THUMBNAIL_EXT}"
        thumb_path = settings.THUMBNAIL_DIR / thumb_filename
        thumb_source = transcoded_file if transcoded_file else target_path
        try:
            generate_thumbnail(thumb_source, thumb_path, file_type_enum)
        except Exception as e:
            logger.error(f"Failed to generate thumbnail for {thumb_source}: {e}")

        # Parse rating
        rating_str = media_data.get('rating', 'safe')
        rating_enum = RatingEnum.safe
        if rating_str == 'questionable':
            rating_enum = RatingEnum.questionable
        elif rating_str == 'explicit':
            rating_enum = RatingEnum.explicit

        # Parse uploaded_at
        uploaded_at_val = None
        if media_data.get('uploaded_at'):
            try:
                uploaded_at_val = datetime.fromisoformat(media_data['uploaded_at'])
            except Exception:
                uploaded_at_val = None
        if uploaded_at_val is None:
            uploaded_at_val = datetime.now(timezone.utc)

        new_media = Media(
            filename=target_path.name,
            path=str(target_path.relative_to(settings.BASE_DIR)),
            transcoded_path=transcoded_rel_path,
            thumbnail_path=str(thumb_path.relative_to(settings.BASE_DIR)) if thumb_path.exists() else None,
            hash=file_hash,
            file_type=file_type_enum,
            mime_type=media_data.get('mime_type'),
            file_size=media_data.get('file_size') or (target_path.stat().st_size if target_path.exists() else 0),
            width=media_data.get('width'),
            height=media_data.get('height'),
            duration=media_data.get('duration'),
            rating=rating_enum,
            source=media_data.get('source'),
            description=media_data.get('description'),
            description_enlarged=bool(media_data.get('description_enlarged', False)),
            uploaded_at=uploaded_at_val,
            is_shared=bool(media_data.get('is_shared', False)),
            share_uuid=media_data.get('share_uuid'),
            share_ai_metadata=bool(media_data.get('share_ai_metadata', False)),
            share_language=media_data.get('share_language'),
        )
        db.add(new_media)
        db.flush() # Get ID
        
        # Track parent for linking
        parent_hash = media_data.get('parent_hash')
        if parent_hash:
            parent_links.append((new_media.id, parent_hash))

        tag_names = media_data.get('tags', [])
        tag_ids_to_link = []
        for tname in tag_names:
            normalized_name = tname.strip().lower()
            if normalized_name in all_tags:
                tid = all_tags[normalized_name]
                tag_ids_to_link.append(tid)
                affected_tag_ids.add(tid)
            elif normalized_name in all_aliases:
                tid = all_aliases[normalized_name]
                tag_ids_to_link.append(tid)
                affected_tag_ids.add(tid)
            else:
                # Auto-create missing tag
                new_tag = Tag(name=normalized_name, category=TagCategoryEnum.general, post_count=0)
                db.add(new_tag)
                db.flush()
                all_tags[normalized_name] = new_tag.id
                tag_ids_to_link.append(new_tag.id)
                affected_tag_ids.add(new_tag.id)

        unique_tag_ids = list(dict.fromkeys(tag_ids_to_link))
        if unique_tag_ids:
            stmt = blombooru_media_tags.insert().values([
                {'media_id': new_media.id, 'tag_id': tid} for tid in unique_tag_ids
            ])
            db.execute(stmt)
            
        existing_hashes.add(file_hash)
        imported_count += 1
        if imported_count % 100 == 0:
            db.commit()
            logger.info(f"Imported {imported_count} media files...")

    db.commit()
    
    # Post-process parent links
    if parent_links:
        logger.info(f"Linking {len(parent_links)} parent/child relationships...")
        all_media_map = {m.hash: m.id for m in db.query(Media.hash, Media.id).all()}
        updates = []
        for child_id, parent_h in parent_links:
            if parent_h in all_media_map:
                parent_id = all_media_map[parent_h]
                if child_id != parent_id:
                    updates.append({'id': child_id, 'parent_id': parent_id})
        if updates:
            db.bulk_update_mappings(Media, updates)
            db.commit()

    # Post-process tag counts
    if affected_tag_ids:
        update_tag_counts(db, list(affected_tag_ids))
        db.commit()

    logger.info(f"Media import complete. Imported: {imported_count}, Skipped: {skipped_count}")
    return {"imported": imported_count, "skipped": skipped_count, "total": len(media_list)}

def import_albums_logical(db: Session, albums_list: List[dict]) -> dict:
    """Imports albums, album media associations, and album hierarchy."""
    logger.info(f"Starting album import for {len(albums_list)} albums...")
    
    id_map: Dict[Any, int] = {}
    existing_albums = {a.name: a for a in db.query(Album).all()}
    albums_created = 0
    albums_existing = 0

    # PASS 1: Create Albums and build ID mapping
    for alb_data in albums_list:
        name = alb_data.get('name')
        if not name:
            continue
        json_id = alb_data.get('id')
        
        created_at = None
        if alb_data.get('created_at'):
            try:
                created_at = datetime.fromisoformat(alb_data['created_at'])
            except Exception:
                created_at = None

        updated_at = None
        if alb_data.get('updated_at'):
            try:
                updated_at = datetime.fromisoformat(alb_data['updated_at'])
            except Exception:
                updated_at = None

        last_modified = None
        if alb_data.get('last_modified'):
            try:
                last_modified = datetime.fromisoformat(alb_data['last_modified'])
            except Exception:
                last_modified = None
        
        if name in existing_albums:
            id_map[json_id] = existing_albums[name].id
            albums_existing += 1
        else:
            new_album = Album(
                name=name,
                created_at=created_at or datetime.now(timezone.utc),
                updated_at=updated_at or datetime.now(timezone.utc),
                last_modified=last_modified or datetime.now(timezone.utc)
            )
            db.add(new_album)
            db.flush()
            id_map[json_id] = new_album.id
            existing_albums[name] = new_album
            albums_created += 1
            
    db.commit()
    
    # PASS 2: Link Media
    media_map = {m.hash: m.id for m in db.query(Media.hash, Media.id).all()}
    album_media_inserts = []
    links_created = 0
    
    for alb_data in albums_list:
        json_id = alb_data.get('id')
        if json_id not in id_map:
            continue
            
        db_id = id_map[json_id]
        
        existing_links = set(
            r[0] for r in db.query(blombooru_album_media.c.media_id)
            .filter(blombooru_album_media.c.album_id == db_id).all()
        )
        
        # Support both new 'media' object list and legacy 'media_hashes' string list
        media_items = alb_data.get('media', [])
        if not media_items and 'media_hashes' in alb_data:
            media_items = [{'hash': h, 'added_at': None} for h in alb_data['media_hashes']]

        for item in media_items:
            m_hash = item.get('hash') if isinstance(item, dict) else item
            if not m_hash or m_hash not in media_map:
                continue

            media_id = media_map[m_hash]
            if media_id not in existing_links:
                added_at_val = None
                if isinstance(item, dict) and item.get('added_at'):
                    try:
                        added_at_val = datetime.fromisoformat(item['added_at'])
                    except Exception:
                        added_at_val = None

                album_media_inserts.append({
                    'album_id': db_id,
                    'media_id': media_id,
                    'added_at': added_at_val or datetime.now(timezone.utc)
                })
                existing_links.add(media_id)
                links_created += 1

    if album_media_inserts:
        for i in range(0, len(album_media_inserts), DB_BATCH_SIZE):
            chunk = album_media_inserts[i:i+DB_BATCH_SIZE]
            db.execute(blombooru_album_media.insert(), chunk)
            db.commit()

    # PASS 3: Hierarchy
    hierarchy_inserts = []
    for alb_data in albums_list:
        parent_json_id = alb_data.get('id')
        if parent_json_id not in id_map:
            continue
            
        parent_db_id = id_map[parent_json_id]
        child_json_ids = alb_data.get('child_ids', [])
        
        existing_children = set(
            r[0] for r in db.query(blombooru_album_hierarchy.c.child_album_id)
            .filter(blombooru_album_hierarchy.c.parent_album_id == parent_db_id).all()
        )
        
        for child_json_id in child_json_ids:
            if child_json_id in id_map:
                child_db_id = id_map[child_json_id]
                if child_db_id != parent_db_id and child_db_id not in existing_children:
                    hierarchy_inserts.append({
                        'parent_album_id': parent_db_id,
                        'child_album_id': child_db_id
                    })
                    existing_children.add(child_db_id)

    if hierarchy_inserts:
        for i in range(0, len(hierarchy_inserts), DB_BATCH_SIZE):
            chunk = hierarchy_inserts[i:i+DB_BATCH_SIZE]
            db.execute(blombooru_album_hierarchy.insert(), chunk)
            db.commit()
            
    return {
        "albums_created": albums_created,
        "albums_existing": albums_existing,
        "links_created": links_created
    }

def import_tag_implications_logical(db: Session, implications_list: List[dict]) -> dict:
    """Imports tag implications without creating duplicate rules."""
    logger.info(f"Starting tag implications import for {len(implications_list)} items...")
    existing_implications = db.query(TagImplication).options(
        joinedload(TagImplication.target_tags),
        joinedload(TagImplication.implied_tags)
    ).all()
    # Build signature for deduplication
    existing_signatures = set()
    for imp in existing_implications:
        targets = tuple(sorted(t.name for t in imp.target_tags))
        patterns = tuple(sorted(imp.target_tag_patterns or []))
        implied = tuple(sorted(t.name for t in imp.implied_tags))
        existing_signatures.add((targets, patterns, implied))

    db.expunge_all()
    all_tags = {t.name: t for t in db.query(Tag).all()}
    imported_count = 0
    skipped_count = 0

    for imp_data in implications_list:
        target_tag_names = [t.strip().lower() for t in imp_data.get('target_tags', []) if t.strip()]
        patterns = [p.strip().lower() for p in imp_data.get('target_tag_patterns', []) if p.strip()]
        implied_tag_names = [t.strip().lower() for t in imp_data.get('implied_tags', []) if t.strip()]

        if not target_tag_names and not patterns:
            skipped_count += 1
            continue
        if not implied_tag_names:
            skipped_count += 1
            continue

        sig = (tuple(sorted(target_tag_names)), tuple(sorted(patterns)), tuple(sorted(implied_tag_names)))
        if sig in existing_signatures:
            skipped_count += 1
            continue

        # Resolve or create target and implied tags
        target_tags = []
        for tname in target_tag_names:
            if tname not in all_tags:
                new_t = Tag(name=tname, category=TagCategoryEnum.general, post_count=0)
                db.add(new_t)
                db.flush()
                all_tags[tname] = new_t
            target_tags.append(all_tags[tname])

        implied_tags = []
        for tname in implied_tag_names:
            if tname not in all_tags:
                new_t = Tag(name=tname, category=TagCategoryEnum.general, post_count=0)
                db.add(new_t)
                db.flush()
                all_tags[tname] = new_t
            implied_tags.append(all_tags[tname])

        new_imp = TagImplication()
        new_imp.target_tags = target_tags
        new_imp.target_tag_patterns = patterns if patterns else None
        new_imp.implied_tags = implied_tags

        db.add(new_imp)
        existing_signatures.add(sig)
        imported_count += 1

    db.commit()
    logger.info(f"Tag implications import complete. Imported: {imported_count}, Skipped: {skipped_count}")
    return {"imported": imported_count, "skipped": skipped_count}

def import_booru_config_logical(db: Session, booru_config_list: List[dict]) -> dict:
    """Imports booru scraping and importing configurations."""
    logger.info(f"Starting booru config import for {len(booru_config_list)} items...")
    imported_count = 0

    for cfg in booru_config_list:
        domain = normalize_domain(cfg.get('domain'))
        if not domain:
            continue

        username = cfg.get('username')
        api_key = cfg.get('api_key')

        upsert_booru_config(
            db,
            domain=domain,
            username=username,
            api_key=api_key,
        )
        imported_count += 1

    db.commit()
    return {"imported": imported_count}

def import_custom_themes_logical(db: Session, zf: zipfile.ZipFile, themes_list: List[dict]) -> dict:
    """Extracts custom theme CSS files and updates custom themes registry."""
    from ..custom_themes import custom_theme_manager

    themes_dir = custom_theme_manager.custom_themes_dir
    themes_dir.mkdir(parents=True, exist_ok=True)
    imported_count = 0
    namelist = zf.namelist()

    # Extract all .css files under custom_themes/
    for name in namelist:
        if name.startswith("custom_themes/") and name.endswith(".css"):
            filename = Path(name).name
            target_css = (themes_dir / filename).resolve()
            if target_css.parent == themes_dir.resolve():
                with zf.open(name) as src, open(target_css, "wb") as dst:
                    shutil.copyfileobj(src, dst)

    # Register themes in custom_theme_manager
    if themes_list:
        for theme_meta in themes_list:
            theme_id = theme_meta.get("id")
            if not theme_id:
                continue
            custom_theme_manager._meta[theme_id] = {
                "name": theme_meta.get("name", theme_id),
                "is_dark": bool(theme_meta.get("is_dark", True)),
                "primary_color": theme_meta.get("primary_color", "#3b82f6"),
                "background_color": theme_meta.get("background_color", "#0f172a"),
                "backup_theme_id": theme_meta.get("backup_theme_id", "default_dark"),
                "created_at": theme_meta.get("created_at") or datetime.now(timezone.utc).isoformat(),
            }
            imported_count += 1
        custom_theme_manager._save_meta()
        custom_theme_manager.load_from_disk()

    return {"imported": imported_count}

def import_settings_logical(db: Session, settings_dict: dict) -> dict:
    """Restores non-sensitive UI and application settings and resolves custom background media ID."""
    safe_settings = dict(settings_dict)

    # Blacklist sensitive host infrastructure parameters and initial state
    sensitive_keys = ["secret_key", "database", "redis", "shared_tags", "first_run"]
    for key in sensitive_keys:
        safe_settings.pop(key, None)

    # Handle custom_background and map media_hash -> media_id
    if "custom_background" in safe_settings and isinstance(safe_settings["custom_background"], dict):
        bg = dict(safe_settings["custom_background"])
        media_hash = bg.pop("media_hash", None)
        if media_hash:
            media_record = db.query(Media).filter(Media.hash == media_hash).first()
            if media_record:
                bg["media_id"] = media_record.id
            else:
                bg["media_id"] = None
        safe_settings["custom_background"] = bg

    if safe_settings:
        settings.save_settings(safe_settings)
        return {"imported": True, "keys": list(safe_settings.keys())}

    return {"imported": False}
