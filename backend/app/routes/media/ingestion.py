import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Union
from fastapi import HTTPException
from sqlalchemy.orm import Session
from ...config import settings
from ...models import Media
from ...schemas import MediaCreatedResponse
from ...services import near_duplicates
from ...utils.album_utils import set_media_albums
from ...utils.cache import invalidate_media_cache, invalidate_tag_cache
from ...utils.logger import logger
from ...utils.media_processor import calculate_file_hash, process_media_file
from ...utils.perceptual_hash import phash_to_hex
from ...utils.tag_utils import get_escalated_rating
from ...utils.thumbnail_generator import THUMBNAIL_EXT, generate_thumbnail
from .tags import apply_media_tag_implications, get_or_create_tags_with_implications, update_tag_counts

def sync_description_enlarged(media: Media) -> None:
    """Ensure media cannot be marked as enlarged if it has no description."""
    if not media.description:
        media.description_enlarged = False

def process_and_save_media(
    db: Session,
    file_path: Path,
    unique_filename: str,
    rating,
    tags: str,
    album_ids: Optional[str],
    source: Optional[str],
    category_hints: Optional[str],
    description: Optional[str] = None,
    explicit_date: Optional[Union[datetime, str]] = None,
    booru_date: Optional[Union[datetime, str]] = None,
    sidecar_date: Optional[Union[datetime, str]] = None,
    client_date: Optional[Union[datetime, str]] = None,
) -> "MediaCreatedResponse":
    """Hash-check, thumbnail generation, DB insert, tag/album linking, and cache
    invalidation for a media file that is already on disk at *file_path*.

    Raises HTTPException 409 on duplicate hash.  Does NOT delete file_path on
    error. Callers are responsible for cleanup of files they created.
    """
    if explicit_date is not None:
        from ...utils.date_extractor import parse_explicit_custom_date
        if parse_explicit_custom_date(explicit_date) is None:
            raise HTTPException(status_code=422, detail="Invalid custom_date format")

    file_hash = calculate_file_hash(file_path)

    existing = db.query(Media).filter(Media.hash == file_hash).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Media already exists (duplicate of {existing.filename})",
        )

    metadata = process_media_file(file_path, precalculated_hash=file_hash)
    logger.debug(f"Media processed: {metadata}")

    new_phash = near_duplicates.compute_phash_for_new_file(
        file_path, metadata["file_type"], metadata.get("transcoded_path")
    )
    near_duplicate_matches = near_duplicates.find_existing_matches(db, new_phash)

    thumbnail_filename = Path(unique_filename).stem + THUMBNAIL_EXT
    thumbnail_path = settings.THUMBNAIL_DIR / thumbnail_filename

    logger.debug(f"Generating thumbnail: {thumbnail_filename}")
    thumb_source = (settings.BASE_DIR / metadata["transcoded_path"]) if metadata.get("transcoded_path") else file_path
    thumbnail_generated = generate_thumbnail(thumb_source, thumbnail_path, metadata["file_type"])

    if thumbnail_generated:
        logger.debug(f"Thumbnail generated: {thumbnail_path}")
    else:
        logger.warning("Thumbnail generation failed")

    relative_path = file_path.relative_to(settings.BASE_DIR)
    relative_thumb = thumbnail_path.relative_to(settings.BASE_DIR) if thumbnail_generated else None

    committed = False
    try:
        from ...utils.date_extractor import resolve_custom_date
        resolved_custom_date, _origin = resolve_custom_date(
            file_path=file_path,
            explicit_date=explicit_date,
            booru_date=booru_date,
            sidecar_date=sidecar_date,
            client_date=client_date,
        )

        media = Media(
            filename=unique_filename,
            path=str(relative_path),
            transcoded_path=metadata.get("transcoded_path"),
            thumbnail_path=str(relative_thumb) if relative_thumb else None,
            hash=file_hash,
            file_type=metadata["file_type"],
            mime_type=metadata["mime_type"],
            file_size=metadata["file_size"],
            width=metadata["width"],
            height=metadata["height"],
            duration=metadata["duration"],
            phash=phash_to_hex(new_phash) if new_phash is not None else None,
            rating=rating,
            source=source if source else None,
            description=description if description else None,
            custom_date=resolved_custom_date,
        )

        tag_ids_to_update = []
        implied_by_tag_id = {}
        if tags:
            tag_list = [t.strip() for t in tags.split() if t.strip()]
            parsed_hints = None
            if category_hints:
                try:
                    parsed_hints = json.loads(category_hints)
                except (json.JSONDecodeError, TypeError):
                    pass
            media.tags, implied_by_tag_id = get_or_create_tags_with_implications(
                db, tag_list, category_hints=parsed_hints, expand=True
            )
            tag_ids_to_update = [tag.id for tag in media.tags]
            escalated = get_escalated_rating(media.rating, media.tags)
            if escalated and media.rating != escalated:
                media.rating = escalated
            logger.debug(f"Tags added: {tag_list}")

        a_ids = []
        if album_ids:
            try:
                a_ids = [
                    int(id_str.strip())
                    for id_str in album_ids.split(",")
                    if id_str.strip().isdigit()
                ]
            except Exception as e:
                logger.error(f"Error parsing album_ids: {e}")

        db.add(media)
        db.flush()
        if implied_by_tag_id:
            apply_media_tag_implications(db, media, implied_by_tag_id)
        db.commit()
        committed = True
        db.refresh(media)

        if tag_ids_to_update:
            update_tag_counts(db, tag_ids_to_update)
            db.commit()

        if a_ids:
            set_media_albums(db, media.id, a_ids)

        db.refresh(media)
    except Exception:
        if not committed:
            db.rollback()
            if thumbnail_generated and thumbnail_path.exists():
                thumbnail_path.unlink(missing_ok=True)
            if metadata.get("transcoded_path"):
                t_path = settings.BASE_DIR / metadata["transcoded_path"]
                if t_path.exists():
                    t_path.unlink(missing_ok=True)
        raise

    logger.info(f"Media saved: ID={media.id}, filename={unique_filename}")

    invalidate_media_cache()
    invalidate_tag_cache()
    near_duplicates.near_duplicate_index.invalidate()

    response = MediaCreatedResponse.model_validate(media)
    response.near_duplicates = near_duplicate_matches
    return response
