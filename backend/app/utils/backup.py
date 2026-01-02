import os
import zipfile
import json
import io
import shutil
from typing import Generator, BinaryIO, List
from pathlib import Path
from sqlalchemy.orm import Session, joinedload
from ..models import Tag, TagAlias, Media, blombooru_media_tags
from ..config import settings
from fastapi import HTTPException

# Constants for batch processing
DB_BATCH_SIZE = 10000

def generate_tags_csv_stream(db: Session) -> Generator[str, None, None]:
    """Generates a CSV stream of tags"""
    aliases_map = {}
    aliases = db.query(TagAlias).options(joinedload(TagAlias.target_tag)).all()
    for alias in aliases:
        if alias.target_tag_id not in aliases_map:
            aliases_map[alias.target_tag_id] = []
        aliases_map[alias.target_tag_id].append(alias.alias_name)

    query = db.query(Tag).yield_per(1000)

    # Reverse mapping for category export
    # 'general' -> 0, etc.
    category_reverse_map = {
        'general': 0,
        'artist': 1,
        'copyright': 3,
        'character': 4,
        'meta': 5
    }

    for tag in query:
        alias_str = ""
        if tag.id in aliases_map:
            # Quote if contains comma
            alias_list = aliases_map[tag.id]
            if alias_list:
                joined = ",".join(alias_list)
                if "," in joined:
                    alias_str = f'"{joined}"'
                else:
                    alias_str = joined

        # Category handling
        cat_val = 0
        tag_cat_str = 'general'
        
        if hasattr(tag.category, 'value'):
            tag_cat_str = tag.category.value
        elif isinstance(tag.category, str):
            tag_cat_str = tag.category
            
        cat_val = category_reverse_map.get(tag_cat_str, 0)

        yield f"{tag.name},{cat_val},{tag.post_count},{alias_str}\n"

def generate_tags_dump(db: Session) -> dict:
    """
    Generates a dictionary containing all tags and aliases.
    """
    # Fetch tags
    tags_query = db.query(Tag).yield_per(DB_BATCH_SIZE)
    tags_list = []
    for tag in tags_query:
        tags_list.append({
            "name": tag.name,
            "category": tag.category.value if hasattr(tag.category, 'value') else tag.category,
            "post_count": tag.post_count
        })

    # Fetch aliases
    aliases_query = db.query(TagAlias).yield_per(DB_BATCH_SIZE)
    aliases_list = []
    for alias in aliases_query:
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

    def write(self, data):
        self.queue.write(data)
        self.offset += len(data)
        return len(data)

    def tell(self):
        return self.offset

    def flush(self):
        pass

    def get_data(self):
        data = self.queue.getvalue()
        self.queue.truncate(0)
        self.queue.seek(0)
        return data

def stream_zip_generator(files_to_zip: Generator[tuple[str, Path], None, None]) -> Generator[bytes, None, None]:
    """
    Generates a ZIP stream.
    files_to_zip: Generator yielding (arcname, absolute_path)
    """
    mem_file = ZipStream()
    with zipfile.ZipFile(mem_file, 'w', zipfile.ZIP_STORED) as zf:
        for arcname, path in files_to_zip:
            if not path.exists():
                continue

            # Hacky but works
            z_info = zipfile.ZipInfo.from_file(path, arcname)
            z_info.compress_type = zipfile.ZIP_STORED

            with zf.open(z_info, 'w') as dest:
                with open(path, 'rb') as src:
                    while chunk := src.read(1024 * 1024):  # 1MB chunks
                        dest.write(chunk)
                        yield mem_file.get_data()
            yield mem_file.get_data()
    yield mem_file.get_data()

def get_media_files_generator() -> Generator[tuple[str, Path], None, None]:
    """Yields all media files for backup"""
    media_dir = settings.ORIGINAL_DIR
    for root, _, files in os.walk(media_dir):
        for name in files:
            abs_path = Path(root) / name
            rel_path = abs_path.relative_to(media_dir)
            yield (f"media/{rel_path}", abs_path)

def import_full_backup(zip_source, db: Session):
    """
    Imports a full backup ZIP.
    zip_source: Path or file-like object.
    1. Extract tags.csv and process using standard CSV import logic.
    2. Extract media files if they don't exist.
    """
    if not zipfile.is_zipfile(zip_source):
        raise HTTPException(status_code=400, detail="Invalid ZIP file")

    with zipfile.ZipFile(zip_source, 'r') as zf:
        media_list = []
        
        # 1. Handle tags.csv using existing CSV import logic
        if 'tags.csv' in zf.namelist():
            # Import tags using the existing admin CSV import logic
            # This ensures DRY - single source of truth
            from ..routes.admin import import_tags_csv_logic
            
            with zf.open('tags.csv') as f:
                content = f.read().decode('utf-8')
                import_tags_csv_logic(content, db)
        
        # 2. Check for backup.json for media metadata
        if 'backup.json' in zf.namelist():
            try:
                with zf.open('backup.json') as f:
                    backup_data = json.load(f)
                    media_list = backup_data.get('media', [])
            except Exception as e:
                print(f"Error reading backup.json: {e}")
                
        if not media_list:
            # If only tags were imported, that's okay
            if 'tags.csv' not in zf.namelist():
                raise HTTPException(status_code=400, detail="No valid backup data found")

        if media_list:
            import_media_logical(db, zf, media_list)
            
        # 3. Import Albums
        albums_list = backup_data.get('albums', [])
        if albums_list:
            import_albums_logical(db, albums_list)

    return {"message": "Import completed successfully"}

def import_tags_logical(db: Session, tags: List[dict], aliases: List[dict]):
    existing_tags = {t.name: t for t in db.query(Tag).all()}
    tags_to_create = []

    for tag_data in tags:
        name = tag_data['name']
        if name not in existing_tags:
            tags_to_create.append({
                'name': name,
                'category': tag_data.get('category', 'general'),
                'post_count': 0
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
        name = alias_data['alias_name']
        target_name = alias_data.get('target_tag')

        if name not in existing_aliases and target_name in existing_tags:
            aliases_to_create.append({
                'alias_name': name,
                'target_tag_id': existing_tags[target_name].id
            })

    if aliases_to_create:
        for i in range(0, len(aliases_to_create), DB_BATCH_SIZE):
            chunk = aliases_to_create[i:i+DB_BATCH_SIZE]
            db.bulk_insert_mappings(TagAlias, chunk)
            db.commit()

def import_media_logical(db: Session, zf: zipfile.ZipFile, media_list: List[dict]):
    from ..utils.thumbnail_generator import generate_thumbnail
    from ..schemas import FileTypeEnum
    
    print(f"Starting logical media import for {len(media_list)} items...")
    
    existing_hashes = {m.hash for m in db.query(Media.hash).all()}
    print(f"Found {len(existing_hashes)} existing media hashes in DB.")
    
    all_tags = {t.name: t.id for t in db.query(Tag.name, Tag.id).all()}
    
    imported_count = 0
    skipped_count = 0
    parent_links = []
    
    for media_data in media_list:
        file_hash = media_data.get('hash')
        if file_hash in existing_hashes:
            skipped_count += 1
            if skipped_count % 1000 == 0:
                print(f"Skipped {skipped_count} existing files...")
            continue # Skip existing

        original_filename = media_data.get('filename')
        zip_entry_name = media_data.get('archive_path')

        if not zip_entry_name or zip_entry_name not in zf.namelist():
            # Fallback: Try to find by filename in media folder
            print(f"File not found at {zip_entry_name}, attempting fallback search for {original_filename}")
            candidates = [n for n in zf.namelist() if n.startswith('media/') and Path(n).name == original_filename]
            
            if candidates:
                zip_entry_name = candidates[0]
                print(f"Fallback: Found {zip_entry_name}")
            else:
                print(f"File not found in archive: {zip_entry_name} or plain {original_filename}")
                continue

        target_path = settings.ORIGINAL_DIR / Path(zip_entry_name).name

        if target_path.exists():
            stem = target_path.stem
            suffix = target_path.suffix
            import uuid
            target_path = target_path.with_name(f"{stem}_{uuid.uuid4().hex[:8]}{suffix}")

        with zf.open(zip_entry_name) as source, open(target_path, "wb") as target:
            shutil.copyfileobj(source, target)
            
        # Generate Thumbnail
        thumb_filename = target_path.stem + ".jpg" # Always JPEG
        thumb_path = settings.THUMBNAIL_DIR / thumb_filename
        
        file_type_str = media_data.get('file_type', 'image')
        # Map string to Enum (generate_thumbnail expects Enum)
        # Note: models.py uses 'image', 'video', 'gif' strings in enum.
        file_type_enum = FileTypeEnum.image
        if file_type_str == 'video':
            file_type_enum = FileTypeEnum.video
        elif file_type_str == 'gif':
            file_type_enum = FileTypeEnum.gif
            
        try:
            generate_thumbnail(target_path, thumb_path, file_type_enum)
        except Exception as e:
            print(f"Failed to generate thumbnail for {target_path}: {e}")

        new_media = Media(
            filename=target_path.name,
            path=str(target_path),
            thumbnail_path=str(thumb_path) if thumb_path.exists() else None,
            hash=file_hash,
            file_type=media_data.get('file_type'),
            mime_type=media_data.get('mime_type'),
            file_size=media_data.get('file_size'),
            width=media_data.get('width'),
            height=media_data.get('height'),
            duration=media_data.get('duration'),
            rating=media_data.get('rating', 'safe')
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
            if tname in all_tags:
                tag_ids_to_link.append(all_tags[tname])

        if tag_ids_to_link:
            stmt = blombooru_media_tags.insert().values([
                {'media_id': new_media.id, 'tag_id': tid} for tid in tag_ids_to_link
            ])
            db.execute(stmt)
            
        imported_count += 1
        if imported_count % 100 == 0:
            print(f"Imported {imported_count} media files...")

    db.commit()
    
    # Post-process parent links
    if parent_links:
        print(f"Linking {len(parent_links)} parent/child relationships...")
        # Refresh hash map to include newly imported items
        all_media_map = {m.hash: m.id for m in db.query(Media.hash, Media.id).all()}
        
        updates = []
        for child_id, parent_hash in parent_links:
            if parent_hash in all_media_map:
                parent_id = all_media_map[parent_hash]
                # Avoid self-ref
                if child_id != parent_id:
                    updates.append({'id': child_id, 'parent_id': parent_id})
        
        if updates:
             db.bulk_update_mappings(Media, updates)
             db.commit()
             print(f"Linked {len(updates)} parent relationships.")
    
    print(f"Media import complete. Imported: {imported_count}, Skipped: {skipped_count}")

def import_albums_logical(db: Session, albums_list: List[dict]):
    from ..models import Album, blombooru_album_media, blombooru_album_hierarchy, Media
    from datetime import datetime
    
    print(f"Starting album import for {len(albums_list)} albums...")
    
    # PASS 1: Create Albums and build ID mapping
    # json_id -> db_id
    id_map = {}
    existing_albums = {a.name: a for a in db.query(Album).all()}
    
    albums_to_create = []
    
    # Pre-process to create mapping for existing ones and prepare new ones
    for alb_data in albums_list:
        name = alb_data.get('name')
        json_id = alb_data.get('id')
        
        if name in existing_albums:
            # Album exists -> Map JSON ID to existing DB ID
            id_map[json_id] = existing_albums[name].id
        else:
            new_album = Album(
                name=name,
                created_at=datetime.fromisoformat(alb_data['created_at']) if alb_data.get('created_at') else None,
                last_modified=datetime.fromisoformat(alb_data['last_modified']) if alb_data.get('last_modified') else None
            )
            db.add(new_album)
            db.flush()
            id_map[json_id] = new_album.id
            
    db.commit()
    print(f"Pass 1: consistent album IDs mapped.")
    
    # PASS 2: Link Media
    print("Pass 2: Linking media...")
    
    # Cache all media hashes -> IDs
    # Might be heavy, but should be manageable
    media_map = {m.hash: m.id for m in db.query(Media.hash, Media.id).all()}
    
    album_media_inserts = []
    
    for alb_data in albums_list:
        json_id = alb_data.get('id')
        if json_id not in id_map: 
            continue
            
        db_id = id_map[json_id]
        media_hashes = alb_data.get('media_hashes', [])
        
        # Determine which are already linked to avoid dupes
        existing_links = set(
             r[0] for r in db.query(blombooru_album_media.c.media_id)
             .filter(blombooru_album_media.c.album_id == db_id).all()
        )
        
        for mh in media_hashes:
            if mh in media_map:
                media_id = media_map[mh]
                if media_id not in existing_links:
                    album_media_inserts.append({
                        'album_id': db_id,
                        'media_id': media_id
                    })
                    existing_links.add(media_id) # prevent dupes in same batch

    if album_media_inserts:
        # Bulk insert in chunks
        for i in range(0, len(album_media_inserts), DB_BATCH_SIZE):
            chunk = album_media_inserts[i:i+DB_BATCH_SIZE]
            db.execute(blombooru_album_media.insert(), chunk)
            db.commit()
            
    print(f"Pass 2: Linked {len(album_media_inserts)} media items.")

    # PASS 3: Hierarchy
    print("Pass 3: Reconstructing hierarchy...")
    
    hierarchy_inserts = []
    
    for alb_data in albums_list:
        parent_json_id = alb_data.get('id')
        if parent_json_id not in id_map:
            continue
            
        parent_db_id = id_map[parent_json_id]
        child_json_ids = alb_data.get('child_ids', [])
        
        # Get existing children
        existing_children = set(
            r[0] for r in db.query(blombooru_album_hierarchy.c.child_album_id)
            .filter(blombooru_album_hierarchy.c.parent_album_id == parent_db_id).all()
        )
        
        for child_json_id in child_json_ids:
            if child_json_id in id_map:
                child_db_id = id_map[child_json_id]
                
                # prevent self-ref if corrupted
                if child_db_id == parent_db_id:
                    continue
                    
                if child_db_id not in existing_children:
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
            
    print("Pass 3: Hierarchy reconstructed.")
