import re
import threading
import time
from pathlib import Path
from typing import Callable, Dict, Iterable, List, NamedTuple, Optional, Tuple

import numpy as np
from sqlalchemy import false, func, true
from sqlalchemy.orm import Session

from ..config import settings
from ..enums import FileTypeEnum
from ..models import Media
from ..utils.logger import logger
from ..utils.perceptual_hash import (PHASH_BITS, PHASH_HEX_LENGTH,
                                     compute_media_phash, mirror_phash,
                                     phash_from_hex, phash_to_hex,
                                     phash_to_words, similarity_percent)

_POPCOUNT_TABLE = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint8)

def popcount64(values: np.ndarray) -> np.ndarray:
    """Per-element population count of an arbitrary-shaped uint64 array."""
    if hasattr(np, "bitwise_count"):
        return np.bitwise_count(values).astype(np.uint8, copy=False)
    contiguous = np.ascontiguousarray(values, dtype=np.uint64)
    as_bytes = contiguous.view(np.uint8).reshape(contiguous.shape + (8,))
    return _POPCOUNT_TABLE[as_bytes].sum(axis=-1, dtype=np.uint8)

def popcount256(words: np.ndarray) -> np.ndarray:
    """Population count across the four uint64 words of each 256-bit PDQ hash (shape (N, 4))."""
    return popcount64(words).sum(axis=-1, dtype=np.uint16)

def describe_match_confidence(distance: int) -> str:
    """Coarse confidence label for a 256-bit PDQ Hamming distance (used by the UI)."""
    if distance <= 8:
        return "identical"
    if distance <= 20:
        return "very_similar"
    return "similar"

class _Snapshot:
    __slots__ = ("ids", "hashes", "built_at", "bind_key", "generation")

    def __init__(self, ids: np.ndarray, hashes: np.ndarray, bind_key: int, generation: int):
        self.ids = ids
        self.hashes = hashes
        self.built_at = time.monotonic()
        self.bind_key = bind_key
        self.generation = generation

class NearDuplicateIndex:
    """Process-local, lazily rebuilt snapshot of every media PDQ hash."""

    MAX_AGE_SECONDS = 60.0

    def __init__(self):
        self._lock = threading.Lock()
        self._snapshot: Optional[_Snapshot] = None
        self._generation = 0

    def invalidate(self) -> None:
        """Mark the snapshot stale (call after hashes were added, changed, or removed)."""
        self._generation += 1

    def _is_fresh(self, snap: Optional[_Snapshot], bind_key: int) -> bool:
        return (
            snap is not None
            and snap.generation == self._generation
            and snap.bind_key == bind_key
            and (time.monotonic() - snap.built_at) < self.MAX_AGE_SECONDS
        )

    def _get_snapshot(self, db: Session) -> _Snapshot:
        bind_key = id(db.get_bind())
        snap = self._snapshot
        if self._is_fresh(snap, bind_key):
            return snap

        with self._lock:
            snap = self._snapshot
            if self._is_fresh(snap, bind_key):
                return snap

            generation = self._generation
            rows = db.query(Media.id, Media.phash).filter(Media.phash.isnot(None)).all()
            valid_ids: List[int] = []
            valid_hex: List[str] = []
            for mid, raw_phash in rows:
                parsed = phash_from_hex(raw_phash)
                if parsed is not None:
                    valid_ids.append(mid)
                    valid_hex.append(phash_to_hex(parsed))

            ids = np.array(valid_ids, dtype=np.int64)
            if valid_hex:
                raw_bytes = bytes.fromhex("".join(valid_hex))
                hashes = np.frombuffer(raw_bytes, dtype=">u8").reshape(len(valid_hex), 4).astype(np.uint64)
            else:
                hashes = np.empty((0, 4), dtype=np.uint64)

            snap = _Snapshot(ids, hashes, bind_key, generation)
            self._snapshot = snap
            return snap

    def search(
        self,
        db: Session,
        phash: int,
        max_distance: int,
        exclude_ids: Iterable[int] = (),
        limit: Optional[int] = 25,
    ) -> List[Tuple[int, int]]:
        """Return ``[(media_id, distance), ...]`` closest first, within ``max_distance`` bits."""
        snap = self._get_snapshot(db)
        if snap.ids.size == 0:
            return []

        target = phash_to_words(phash)
        mirrored = phash_to_words(mirror_phash(phash))
        distances = np.minimum(
            popcount256(snap.hashes ^ target),
            popcount256(snap.hashes ^ mirrored),
        )
        hit_idx = np.nonzero(distances <= max_distance)[0]
        if hit_idx.size == 0:
            return []

        excluded = set(exclude_ids)
        hits = [
            (int(snap.ids[i]), int(distances[i]))
            for i in hit_idx
            if int(snap.ids[i]) not in excluded
        ]
        hits.sort(key=lambda pair: (pair[1], pair[0]))
        return hits[:limit] if limit else hits

near_duplicate_index = NearDuplicateIndex()

def is_enabled() -> bool:
    return bool(settings.NEAR_DUPLICATE_SETTINGS["enabled"])

def get_max_distance() -> int:
    return int(settings.NEAR_DUPLICATE_SETTINGS["max_distance"])

_HASH_TOKEN = re.compile(rf"^[0-9a-fA-F]{{{PHASH_HEX_LENGTH}}}$")
_ID_TOKEN = re.compile(r"^[0-9]{1,15}$")

class SimilarToTargets(NamedTuple):
    phashes: List[int]
    media_ids: List[int]
    unresolved_media_ids: List[int]
    invalid_tokens: List[str]

def parse_similar_to_value(value: str) -> Tuple[List[int], List[int], List[str]]:
    """Split a ``similar_to`` value into ``(post_ids, phashes, invalid_tokens)``."""
    post_ids: List[int] = []
    phashes: List[int] = []
    invalid: List[str] = []
    for token in re.split(r"[,\s\[\]]+", value or ""):
        if not token:
            continue
        if _HASH_TOKEN.match(token):
            phashes.append(int(token, 16))
        elif _ID_TOKEN.match(token):
            post_ids.append(int(token))
        else:
            invalid.append(token)
    return post_ids, phashes, invalid

def media_phash_hex(media: Media) -> Optional[str]:
    """The post's PDQ hash in the 64-hex-digit form accepted by :func:`parse_similar_to_value`."""
    parsed = phash_from_hex(media.phash)
    if parsed is None:
        return None
    return phash_to_hex(parsed)

def resolve_similar_to_targets(db: Session, values: Iterable[str]) -> SimilarToTargets:
    """Turn raw ``similar_to`` values (post IDs and/or PDQ hashes) into hashes to search for."""
    post_ids: List[int] = []
    phashes: List[int] = []
    invalid: List[str] = []
    for value in values:
        ids, hashes, bad = parse_similar_to_value(value)
        post_ids.extend(ids)
        phashes.extend(hashes)
        invalid.extend(bad)

    post_ids = list(dict.fromkeys(post_ids))
    unresolved: List[int] = []
    if post_ids:
        found = {
            mid: phash for mid, phash in
            db.query(Media.id, Media.phash).filter(Media.id.in_(post_ids)).all()
        }
        for mid in post_ids:
            parsed = phash_from_hex(found.get(mid))
            if parsed is None:
                unresolved.append(mid)
            else:
                phashes.append(parsed)

    return SimilarToTargets(list(dict.fromkeys(phashes)), post_ids, unresolved, invalid)

def find_similar_media(
    db: Session,
    phashes: Iterable[int],
    max_distance: Optional[int] = None,
    exclude_ids: Iterable[int] = (),
    limit: Optional[int] = None,
) -> List[Tuple[int, int]]:
    """Posts similar to *any* of ``phashes`` as ``[(media_id, closest_distance), ...]``.

    When multiple targets are given, posts matching more targets closely rank first,
    with ties broken by closest single-target distance and then ``media_id``.
    """
    target_phashes = list(dict.fromkeys(phashes))
    if not target_phashes:
        return []
    max_distance = get_max_distance() if max_distance is None else max_distance
    exclude = set(exclude_ids)
    per_target: List[Dict[int, int]] = []
    for value in target_phashes:
        hits = dict(near_duplicate_index.search(
            db, value, max_distance, exclude_ids=exclude, limit=None
        ))
        per_target.append(hits)

    candidates = set().union(*per_target)
    if not candidates:
        return []

    cap = max_distance + 1
    scored: List[Tuple[int, int, int]] = []
    for media_id in candidates:
        best_dist = min(hits[media_id] for hits in per_target if media_id in hits)
        if len(per_target) == 1:
            score = best_dist
        else:
            score = sum(hits.get(media_id, cap) for hits in per_target)
        scored.append((score, best_dist, media_id))

    scored.sort()
    ordered = [(media_id, best_dist) for _, best_dist, media_id in scored]
    return ordered[:limit] if limit else ordered

def similar_to_condition(
    db: Session,
    values: Iterable[str],
    negated: bool = False,
    max_distance: Optional[int] = None,
    exclude_given_posts: bool = True,
):
    """Condition for ``similar_to:<values>`` plus ``{media_id: distance}`` for sorting.

    When ``negated=False`` and ``max_distance`` is ``None``, no similarity cutoff is applied so
    that all posts can be ranked by distance (excluding ``targets.media_ids`` if requested).
    When ``negated=True``, ``max_distance`` defaults to the configured near-duplicate threshold
    so only near-duplicates are excluded.
    """
    targets = resolve_similar_to_targets(db, values)
    exclude = targets.media_ids if exclude_given_posts else ()
    if not targets.phashes:
        return (true() if negated else false()), {}

    effective_max = (
        max_distance
        if max_distance is not None
        else (get_max_distance() if negated else PHASH_BITS)
    )
    matches = find_similar_media(db, targets.phashes, effective_max, exclude_ids=exclude)
    distances = dict(matches)
    if negated:
        if not distances:
            return true(), distances
        return ~Media.id.in_(list(distances.keys())), distances

    if max_distance is not None:
        if not distances:
            return false(), distances
        return Media.id.in_(list(distances.keys())), distances

    if exclude_given_posts and targets.media_ids:
        return ~Media.id.in_(targets.media_ids), distances
    return true(), distances

def _enum_value(value):
    return getattr(value, "value", value)

def describe_media(media: Media) -> dict:
    return {
        "media_id": media.id,
        "filename": media.filename,
        "file_type": _enum_value(media.file_type),
        "mime_type": media.mime_type,
        "file_size": media.file_size,
        "width": media.width,
        "height": media.height,
        "duration": media.duration,
        "rating": _enum_value(media.rating),
        "thumbnail_url": f"/api/media/{media.id}/thumbnail",
        "file_url": f"/api/media/{media.id}/file",
        "page_url": f"/media/{media.id}",
    }

def find_existing_matches(
    db: Session,
    phash: Optional[int],
    max_distance: Optional[int] = None,
    exclude_ids: Iterable[int] = (),
    limit: int = 25,
) -> List[dict]:
    """Near-duplicates of ``phash`` among posts already in the library (closest first)."""
    if phash is None or not is_enabled():
        return []
    max_distance = get_max_distance() if max_distance is None else max_distance

    hits = near_duplicate_index.search(db, phash, max_distance, exclude_ids=exclude_ids, limit=limit)
    if not hits:
        return []

    hit_ids = [mid for mid, _ in hits]
    media_by_id = {m.id: m for m in db.query(Media).filter(Media.id.in_(hit_ids)).all()}
    # How many children each post has (one query for all of them)
    children_counts = dict(
        db.query(Media.parent_id, func.count(Media.id))
        .filter(Media.parent_id.in_(hit_ids))
        .group_by(Media.parent_id)
        .all()
    )
    results = []
    for media_id, distance in hits:
        media = media_by_id.get(media_id)
        if media is None:
            continue  # deleted since the snapshot was taken
        entry = describe_media(media)
        entry["parent_id"] = media.parent_id
        entry["children_count"] = int(children_counts.get(media_id, 0))
        entry["distance"] = distance
        entry["similarity"] = similarity_percent(distance)
        entry["confidence"] = describe_match_confidence(distance)
        results.append(entry)
    return results

def find_queue_matches(
    items: Dict[str, dict],
    max_distance: Optional[int] = None,
) -> Dict[str, List[dict]]:
    """Pairwise near-duplicates between the items of an upload session."""
    if not is_enabled():
        return {}
    max_distance = get_max_distance() if max_distance is None else max_distance

    hashed = []
    for item_id, item in items.items():
        value = phash_from_hex(item.get("phash"))
        if value is not None:
            hashed.append((item_id, value))
    if len(hashed) < 2:
        return {}

    keys = [k for k, _ in hashed]
    values = np.vstack([phash_to_words(v) for _, v in hashed])

    matches: Dict[str, List[dict]] = {}
    for row, (item_id, value) in enumerate(hashed):
        target = phash_to_words(value)
        mirrored = phash_to_words(mirror_phash(value))
        distances = np.minimum(
            popcount256(values ^ target),
            popcount256(values ^ mirrored),
        )
        hit_idx = [int(i) for i in np.nonzero(distances <= max_distance)[0] if int(i) != row]
        if not hit_idx:
            continue
        hit_idx.sort(key=lambda i: (int(distances[i]), i))
        entries = []
        for i in hit_idx:
            other = items[keys[i]]
            distance = int(distances[i])
            entries.append({
                "item_id": keys[i],
                "filename": other.get("filename"),
                "file_type": other.get("file_type"),
                "mime_type": other.get("mime_type"),
                "file_size": other.get("file_size"),
                "width": other.get("width"),
                "height": other.get("height"),
                "duration": other.get("duration"),
                "distance": distance,
                "similarity": similarity_percent(distance),
                "confidence": describe_match_confidence(distance),
            })
        matches[item_id] = entries
    return matches

def compute_item_phash_hex(file_path: Path, file_type) -> Optional[str]:
    """Hash a staged/uploaded file; ``None`` when the file cannot be fingerprinted."""
    value = compute_media_phash(file_path, file_type)
    return phash_to_hex(value) if value is not None else None

def compute_phash_for_new_file(file_path: Path, file_type, transcoded_path: Optional[str] = None) -> Optional[int]:
    """Hash a file that is about to become a post (``None`` when unhashable)."""
    fallback = (settings.BASE_DIR / transcoded_path) if transcoded_path else None
    return compute_media_phash(file_path, file_type, fallback_path=fallback)

def phash_hex_to_db(value: Optional[str]) -> Optional[str]:
    """Normalize the 64-character hex PDQ hash stored in session/backup metadata for the DB column."""
    parsed = phash_from_hex(value)
    return phash_to_hex(parsed) if parsed is not None else None

_HASHABLE_TYPES = (FileTypeEnum.image, FileTypeEnum.gif, FileTypeEnum.video)

_backfill_lock = threading.Lock()
_backfill_state: Dict[str, object] = {
    "running": False,
    "total": 0,
    "processed": 0,
    "hashed": 0,
    "failed": 0,
    "current_file": None,
    "error": None,
    "started_at": None,
    "finished_at": None,
}

def count_unhashed(db: Session) -> int:
    """Number of hashable posts still waiting for a perceptual hash."""
    return db.query(Media.id).filter(Media.phash.is_(None), Media.file_type.in_(_HASHABLE_TYPES)).count()

def get_backfill_status() -> dict:
    return dict(_backfill_state)

def mark_backfill_queued() -> None:
    """Flag the backfill as running before its worker thread starts.

    Lets clients that poll right after requesting a backfill see ``running`` immediately instead
    of the previous run's stale result. The worker overwrites these values as soon as it begins.
    """
    _backfill_state.update(
        running=True, total=0, processed=0, hashed=0, failed=0,
        current_file=None, error=None, started_at=time.time(), finished_at=None,
    )

def _media_file_paths(media: Media) -> Tuple[Optional[Path], Optional[Path]]:
    primary = (settings.BASE_DIR / media.path) if media.path else None
    fallback = (settings.BASE_DIR / media.transcoded_path) if media.transcoded_path else None
    return primary, fallback

def compute_phash_for_media(media: Media) -> Optional[int]:
    """Fingerprint the stored file of an existing post (``None`` if it cannot be read)."""
    primary, fallback = _media_file_paths(media)
    if primary is None:
        return None
    return compute_media_phash(primary, media.file_type, fallback_path=fallback)

def refresh_media_phash(media: Media) -> None:
    """Recompute and assign the PDQ hash of a post whose file just changed (caller commits)."""
    value = compute_phash_for_media(media)
    media.phash = phash_to_hex(value) if value is not None else None
    near_duplicate_index.invalidate()

def backfill_missing_phashes(
    session_factory: Callable[[], Session],
    batch_size: int = 100,
    should_stop: Optional[Callable[[], bool]] = None,
    throttle_seconds: float = 0.005,
    missing_only: bool = False,
) -> dict:
    """Hash hashable posts (all by default, or only unhashed when ``missing_only=True``). Safe to call repeatedly / concurrently."""
    if not _backfill_lock.acquire(blocking=False):
        return get_backfill_status()

    try:
        db = session_factory()
        try:
            filters = [Media.file_type.in_(_HASHABLE_TYPES)]
            if missing_only:
                filters.append(Media.phash.is_(None))
            total = db.query(Media.id).filter(*filters).count()
            _backfill_state.update(
                running=True, total=total, processed=0, hashed=0, failed=0,
                current_file=None, error=None, started_at=time.time(), finished_at=None,
            )
            if total:
                logger.info(f"Near-duplicate backfill: hashing {total} existing post(s)...")

            last_id = 0
            while True:
                if should_stop and should_stop():
                    break
                batch = (
                    db.query(Media)
                    .filter(*filters, Media.id > last_id)
                    .order_by(Media.id)
                    .limit(batch_size)
                    .all()
                )
                if not batch:
                    break

                for media in batch:
                    last_id = media.id
                    _backfill_state["current_file"] = media.filename
                    value = compute_phash_for_media(media)
                    if value is None:
                        _backfill_state["failed"] += 1
                    else:
                        media.phash = phash_to_hex(value)
                        _backfill_state["hashed"] += 1
                    _backfill_state["processed"] += 1
                    if throttle_seconds:
                        time.sleep(throttle_seconds)

                db.commit()
                near_duplicate_index.invalidate()
        finally:
            db.close()
    except Exception as e:
        _backfill_state["error"] = str(e)
        logger.error(f"Near-duplicate backfill failed: {e}", exc_info=True)
    finally:
        _backfill_state["running"] = False
        _backfill_state["current_file"] = None
        _backfill_state["finished_at"] = time.time()
        _backfill_lock.release()

    if _backfill_state["total"]:
        logger.info(
            f"Near-duplicate backfill finished: {_backfill_state['hashed']} hashed, "
            f"{_backfill_state['failed']} could not be fingerprinted."
        )
    return get_backfill_status()
