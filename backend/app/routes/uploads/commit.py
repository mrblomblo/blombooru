import shutil
from pathlib import Path
from typing import Dict, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ...auth import require_admin_mode
from ...config import settings
from ...database import get_db
from ...enums import FileTypeEnum, RatingEnum
from ...models import (
    Album,
    Media,
    Tag,
    User,
)
from ...schemas import UploadSessionCommitItemResult, UploadSessionCommitResponse
from ...services import near_duplicates
from ...utils.album_path_resolver import ensure_album_path
from ...utils.album_utils import recalculate_album_metrics, update_album_last_modified
from ...utils.cache import (
    invalidate_album_cache,
    invalidate_media_cache,
    invalidate_media_item_cache,
    invalidate_tag_cache,
)
from ...utils.logger import logger
from ...utils.media_helpers import get_unique_filename
from ...utils.media_processor import calculate_file_hash
from ...utils.media_relations import apply_pending_queue_relations, apply_pending_relations
from ...utils.request_helpers import safe_error_detail
from ...utils.tag_utils import get_escalated_rating, get_newly_added_tags, normalize_tag_rating
from ...utils.thumbnail_generator import THUMBNAIL_EXT, generate_thumbnail
from ...utils.transcoder import transcode_media_if_needed
from ..media import apply_media_tag_implications, get_or_create_tags_with_implications, update_tag_counts
from .session_store import (
    _get_session_dir,
    _get_session_lock,
    _load_session_meta,
    _session_locks,
)

router = APIRouter()

@router.post("/sessions/{session_id}/commit", response_model=UploadSessionCommitResponse)
async def commit_upload_session(
    session_id: str,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db),
):
    """Commit the staged session in a single database transaction."""
    async with _get_session_lock(session_id):
        session_dir = _get_session_dir(session_id)
        meta = _load_session_meta(session_dir)
        items = meta.get("items", {})

        if not items:
            raise HTTPException(status_code=400, detail="No items to commit in this session")

        results: List[UploadSessionCommitItemResult] = []
        total_created = 0
        total_duplicates = 0
        total_failed = 0

        all_tag_ids_to_update: set[int] = set()
        all_affected_album_ids: set[int] = set()
        all_affected_relation_ids: set[int] = set()
        created_media_by_item_id: Dict[str, Media] = {}

        try:
            # Pre-scan for duplicate items (both pre-marked and hash collision against DB)
            duplicate_item_ids: set[str] = set()
            for i_id, item in items.items():
                if item.get("is_duplicate"):
                    duplicate_item_ids.add(i_id)
                    continue
                if item.get("source_path"):
                    file_to_check = Path(item["source_path"])
                else:
                    file_to_check = session_dir / "raw" / item.get("staged_filename", "")
                f_hash = item.get("hash") or (calculate_file_hash(file_to_check) if file_to_check.exists() else None)
                if f_hash and db.query(Media.id).filter(Media.hash == f_hash).first():
                    duplicate_item_ids.add(i_id)

            # Step 1: Gather and bulk create all confirmed new tags (skipping duplicate items)
            pending_tags_to_create: Dict[str, dict] = {}
            for i_id, item in items.items():
                if i_id in duplicate_item_ids:
                    continue
                for t in item.get("tags", []):
                    t_name = t.get("name", "").strip().lower()
                    if not t_name:
                        continue
                    if t.get("is_new", False):
                        cat = t.get("category", "general")
                        rating = t.get("rating", "none")
                        pending_tags_to_create[t_name] = {"category": cat, "rating": rating}

            if pending_tags_to_create:
                existing_db_tags = {
                    t.name: t for t in db.query(Tag).filter(Tag.name.in_(list(pending_tags_to_create.keys()))).all()
                }
                for t_name, info in pending_tags_to_create.items():
                    if t_name not in existing_db_tags:
                        new_tag = Tag(
                            name=t_name,
                            post_count=0,
                            category=info["category"],
                            rating=normalize_tag_rating(info.get("rating"))
                        )
                        db.add(new_tag)
                db.flush()

            # Step 2: Resolve and create any suggested albums (skipping duplicate items)
            album_path_cache: Dict[str, Album] = {}
            for i_id, item in items.items():
                if i_id in duplicate_item_ids:
                    continue
                suggested_path = item.get("suggested_album_path")
                if suggested_path:
                    leaf_album, touched_ids = ensure_album_path(db, suggested_path, album_path_cache)
                    if leaf_album:
                        all_affected_album_ids.update(touched_ids)
                        # Assign leaf album to item's album_ids
                        current_aids = set(item.get("album_ids", []))
                        current_aids.add(leaf_album.id)
                        item["album_ids"] = list(current_aids)

            # Step 3: Commit each media item
            for item_id, item in items.items():
                clean_filename = item.get("filename", "media")
                is_untracked = bool(item.get("is_untracked") or item.get("source_path"))

                if is_untracked:
                    source_path_str = item.get("source_path")
                    source_path = Path(source_path_str) if source_path_str else None
                    if not source_path or not source_path.exists():
                        total_failed += 1
                        results.append(UploadSessionCommitItemResult(
                            item_id=item_id,
                            filename=clean_filename,
                            status="failed",
                            error="Source file not found",
                        ))
                        continue
                    file_to_process = source_path
                else:
                    staged_path = session_dir / "raw" / item.get("staged_filename", "")
                    if not staged_path.exists():
                        total_failed += 1
                        results.append(UploadSessionCommitItemResult(
                            item_id=item_id,
                            filename=clean_filename,
                            status="failed",
                            error="Staged file not found",
                        ))
                        continue
                    file_to_process = staged_path

                file_hash = item.get("hash") or calculate_file_hash(file_to_process)

                # Check duplicate in DB or marked duplicate
                if item_id in duplicate_item_ids:
                    existing = db.query(Media).filter(Media.hash == file_hash).first()
                    total_duplicates += 1
                    dup_filename = existing.filename if existing else (item.get("duplicate_of") or clean_filename)
                    results.append(UploadSessionCommitItemResult(
                        item_id=item_id,
                        filename=clean_filename,
                        media_id=existing.id if existing else None,
                        status="duplicate",
                        error=f"Duplicate of {dup_filename}",
                    ))
                    continue

                if is_untracked:
                    dest_path = file_to_process
                    unique_filename = dest_path.name
                else:
                    # Move staged file to original destination
                    unique_filename = get_unique_filename(settings.ORIGINAL_DIR, clean_filename)
                    dest_path = settings.ORIGINAL_DIR / unique_filename
                    shutil.move(str(staged_path), str(dest_path))

                # Transcode if container/codec requires it
                transcoded_file_path = transcode_media_if_needed(dest_path)
                rel_transcoded = str(transcoded_file_path.relative_to(settings.BASE_DIR)) if transcoded_file_path else None

                # Generate final thumbnail
                thumb_filename = Path(unique_filename).stem + THUMBNAIL_EXT
                thumb_dest_path = settings.THUMBNAIL_DIR / thumb_filename
                file_type_str = item.get("file_type", "image")
                thumb_source = transcoded_file_path if transcoded_file_path else dest_path
                thumb_gen = generate_thumbnail(thumb_source, thumb_dest_path, file_type_str)

                rel_path = dest_path.relative_to(settings.BASE_DIR)
                rel_thumb = thumb_dest_path.relative_to(settings.BASE_DIR) if thumb_gen else None

                item_cdate_str = item.get("custom_date")
                parsed_cdate = None
                if item_cdate_str:
                    from ...utils.date_extractor import parse_explicit_custom_date
                    parsed_cdate = parse_explicit_custom_date(item_cdate_str)

                # Create Media DB record
                media = Media(
                    filename=unique_filename,
                    path=str(rel_path),
                    transcoded_path=rel_transcoded,
                    thumbnail_path=str(rel_thumb) if rel_thumb else None,
                    hash=file_hash,
                    file_type=FileTypeEnum(file_type_str) if file_type_str in FileTypeEnum._value2member_map_ else FileTypeEnum.image,
                    mime_type=item.get("mime_type"),
                    file_size=item.get("file_size", 0),
                    width=item.get("width"),
                    height=item.get("height"),
                    duration=item.get("duration"),
                    phash=near_duplicates.phash_hex_to_db(item.get("phash")),
                    rating=RatingEnum.normalize(item.get("rating")) or RatingEnum.safe,
                    source=item.get("source") or None,
                    description=item.get("description") or None,
                    custom_date=parsed_cdate,
                )

                # Link tags
                item_tag_names = [t.get("name", "").strip().lower() for t in item.get("tags", []) if t.get("name")]
                implied_by_tag_id = {}
                if item_tag_names:
                    pre_implied_map = {
                        t.get("name", "").strip().lower(): (t.get("implied_by") or [])
                        for t in item.get("tags", [])
                        if t.get("name") and t.get("implied")
                    }
                    media.tags, implied_by_tag_id = get_or_create_tags_with_implications(
                        db,
                        item_tag_names,
                        expand=not bool(item.get("tags_reviewed")),
                        pre_implied_map=pre_implied_map,
                    )
                    for t in media.tags:
                        all_tag_ids_to_update.add(t.id)
                    # The staged rating already reflects the staged tags (and any deliberate
                    # manual change), so only tags that first appear at commit time escalate.
                    escalated = get_escalated_rating(
                        media.rating, get_newly_added_tags(item.get("tags", []), media.tags)
                    )
                    if escalated and escalated != media.rating:
                        media.rating = escalated

                # Link albums
                a_ids = item.get("album_ids", [])
                if a_ids:
                    albums = db.query(Album).filter(Album.id.in_(a_ids)).all()
                    media.albums = albums
                    for alb in albums:
                        all_affected_album_ids.add(alb.id)

                db.add(media)
                db.flush()
                if implied_by_tag_id:
                    apply_media_tag_implications(db, media, implied_by_tag_id)

                # Pending parent/child relation to existing posts
                if item.get("parent_media_id") or item.get("child_media_ids"):
                    all_affected_relation_ids.update(apply_pending_relations(
                        db, media, item.get("parent_media_id"), item.get("child_media_ids")
                    ))
                    db.flush()

                created_media_by_item_id[item_id] = media

                total_created += 1
                results.append(UploadSessionCommitItemResult(
                    item_id=item_id,
                    filename=clean_filename,
                    media_id=media.id,
                    status="created",
                ))

            # Apply pending queue-to-queue parent/child relations
            if created_media_by_item_id:
                all_affected_relation_ids.update(
                    apply_pending_queue_relations(db, created_media_by_item_id, items)
                )

            # Commit transaction
            db.commit()
            near_duplicates.near_duplicate_index.invalidate()

            # Update tag counts and album modified times
            if all_tag_ids_to_update:
                update_tag_counts(db, list(all_tag_ids_to_update))
                db.commit()

            if all_affected_album_ids:
                affected_album_ids_list = list(all_affected_album_ids)
                update_album_last_modified(affected_album_ids_list, db)
                recalculate_album_metrics(db, affected_album_ids_list)
                db.commit()
                invalidate_album_cache()

            invalidate_media_cache()
            invalidate_tag_cache()
            for related_id in all_affected_relation_ids:
                invalidate_media_item_cache(related_id)

            # Clean up session directory
            shutil.rmtree(session_dir, ignore_errors=True)
            _session_locks.pop(Path(session_id).name, None)

            return UploadSessionCommitResponse(
                results=results,
                total_created=total_created,
                total_duplicates=total_duplicates,
                total_failed=total_failed,
            )

        except Exception as e:
            db.rollback()
            logger.exception(f"Failed to commit upload session {session_id}")
            raise HTTPException(status_code=500, detail=safe_error_detail("Failed to commit upload session", e))
