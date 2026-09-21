import asyncio
import threading
import time
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
import scipy.sparse as sp
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..enums import TagCategoryEnum
from ..utils.logger import logger

DEFAULT_CATEGORY_WEIGHTS: Dict[str, float] = {
    TagCategoryEnum.artist.value: 5.0,
    TagCategoryEnum.character.value: 4.0,
    TagCategoryEnum.general.value: 1.0,
    TagCategoryEnum.copyright.value: 0.5,
    TagCategoryEnum.meta.value: 0.05,
}

class SimilarityData:
    """Immutable container holding a snapshot of the TF-IDF similarity index."""

    def __init__(
        self,
        num_media: int,
        media_ids: np.ndarray,
        media_id_to_row: Dict[int, int],
        tag_ids: np.ndarray,
        tag_id_to_col: Dict[int, int],
        tag_categories: Dict[int, str],
        tag_names: Dict[int, str],
        df: np.ndarray,
        m_row_norm: sp.csr_matrix,
        m_col_norm: sp.csc_matrix,
        b_csr: sp.csr_matrix,
        b_csc: sp.csc_matrix,
    ):
        self.num_media = num_media
        self.media_ids = media_ids
        self.media_id_to_row = media_id_to_row
        self.tag_ids = tag_ids
        self.tag_id_to_col = tag_id_to_col
        self.tag_categories = tag_categories
        self.tag_names = tag_names
        self.df = df
        self.m_row_norm = m_row_norm
        self.m_col_norm = m_col_norm
        self.b_csr = b_csr
        self.b_csc = b_csc

SUGGESTED_TAGS_CATEGORY_WEIGHTS: Dict[str, float] = {
    TagCategoryEnum.character.value: 10.0,
    TagCategoryEnum.copyright.value: 8.0,
    TagCategoryEnum.artist.value: 6.0,
    TagCategoryEnum.general.value: 1.0,
    TagCategoryEnum.meta.value: 0.05,
}

class SimilarityIndex:
    """
    In-memory TF-IDF similarity index for fast media and tag recommendations.

    Uses sparse CSR / CSC matrices and cosine similarity via dot product.
    Thread-safe with background atomic rebuilds.
    """

    def __init__(self, category_weights: Optional[Dict[str, float]] = None):
        self.category_weights = category_weights or dict(DEFAULT_CATEGORY_WEIGHTS)
        self._data: Optional[SimilarityData] = None
        self._lock = threading.Lock()
        self._is_building = False
        self._rebuild_pending = False

    @property
    def is_ready(self) -> bool:
        return self._data is not None

    @property
    def is_building(self) -> bool:
        return self._is_building

    @property
    def rebuild_pending(self) -> bool:
        """True when a rebuild is queued (debounce sleep) or actively running."""
        global _pending_rebuild_task
        task_pending = _pending_rebuild_task is not None and not _pending_rebuild_task.done()
        if not task_pending and not self._is_building:
            self._rebuild_pending = False
        return (self._rebuild_pending and task_pending) or self._is_building

    async def wait_for_build(self, timeout: float = 10.0) -> bool:
        """
        Suspend until any pending or in-progress rebuild finishes.

        Returns True when the index is ready, False if the timeout expired
        before the rebuild completed.
        """
        global _pending_rebuild_task
        if not self.rebuild_pending:
            return True

        # Execute rebuild immediately since a request needs it now
        if _pending_rebuild_task is not None and not _pending_rebuild_task.done() and not self._is_building:
            _pending_rebuild_task.cancel()
            _pending_rebuild_task = None
            self._rebuild_pending = True
            try:
                from ..database import SessionLocal
                await asyncio.to_thread(
                    self.rebuild_from_session_factory, SessionLocal
                )
            finally:
                self._rebuild_pending = False
            return True

        if not self._is_building:
            self._rebuild_pending = False
            return True

        loop = asyncio.get_running_loop() if hasattr(asyncio, "get_running_loop") else asyncio.get_event_loop()
        deadline = loop.time() + timeout
        while self.rebuild_pending:
            remaining = deadline - loop.time()
            if remaining <= 0:
                logger.warning("wait_for_build: timed out after %.1fs", timeout)
                return False
            await asyncio.sleep(min(0.1, remaining))
        return True

    def rebuild_from_session_factory(self, session_factory):
        """Rebuild the index creating and closing its own DB session."""
        if session_factory is None:
            return
        db = session_factory()
        try:
            self.rebuild(db)
        finally:
            db.close()

    def update_weights(self, new_weights: Dict[str, float]) -> bool:
        """Replace category weights with ``new_weights``."""
        changed = any(
            abs(new_weights.get(k, v) - v) > 1e-9
            for k, v in self.category_weights.items()
        ) or any(k not in self.category_weights for k in new_weights)
        if changed:
            self.category_weights = dict(new_weights)
        return changed

    def rebuild(self, db: Session):
        """
        Build the TF-IDF matrices from database records.
        Runs under a lock to prevent concurrent builds, then atomically swaps the index.
        """
        with self._lock:
            if self._is_building:
                logger.debug("Similarity index build already in progress, skipping.")
                return
            self._is_building = True

        start_time = time.perf_counter()
        try:
            logger.info("Building TF-IDF similarity index...")

            # 1. Fetch distinct media IDs
            media_rows = db.execute(text("SELECT id FROM blombooru_media ORDER BY id")).fetchall()
            if not media_rows:
                logger.info("No media found. Similarity index cleared.")
                with self._lock:
                    self._data = None
                return

            media_ids = np.array([r[0] for r in media_rows], dtype=np.int32)
            num_media = len(media_ids)
            media_id_to_row = {int(mid): i for i, mid in enumerate(media_ids)}

            # 2. Fetch tags metadata
            tag_rows = db.execute(
                text("SELECT id, name, category, post_count FROM blombooru_tags WHERE post_count > 0 ORDER BY id")
            ).fetchall()

            if not tag_rows:
                logger.info("No tags with post_count > 0 found. Similarity index empty.")
                with self._lock:
                    self._data = None
                return

            tag_ids = np.array([r[0] for r in tag_rows], dtype=np.int32)
            num_tags = len(tag_ids)
            tag_id_to_col = {int(tid): j for j, tid in enumerate(tag_ids)}
            tag_names = {int(r[0]): r[1] for r in tag_rows}
            tag_categories = {int(r[0]): str(r[2]).lower() for r in tag_rows}

            # 3. Fetch all media-tag associations in bulk
            edge_rows = db.execute(
                text("SELECT media_id, tag_id FROM blombooru_media_tags")
            ).fetchall()

            if not edge_rows:
                logger.info("No media-tag associations found. Similarity index empty.")
                with self._lock:
                    self._data = None
                return

            # Map media_id and tag_id to matrix row and col indices
            valid_rows = []
            valid_cols = []
            for mid, tid in edge_rows:
                r = media_id_to_row.get(mid)
                c = tag_id_to_col.get(tid)
                if r is not None and c is not None:
                    valid_rows.append(r)
                    valid_cols.append(c)

            if not valid_rows:
                with self._lock:
                    self._data = None
                return

            row_indices = np.array(valid_rows, dtype=np.int32)
            col_indices = np.array(valid_cols, dtype=np.int32)

            # 4. Compute Document Frequency (df) per tag
            # Binary sparse matrix for exact counts and co-occurrences
            b_csr = sp.csr_matrix(
                (np.ones(len(row_indices), dtype=np.float32), (row_indices, col_indices)),
                shape=(num_media, num_tags),
                dtype=np.float32,
            )
            b_csc = b_csr.tocsc()
            df = np.asarray(b_csr.sum(axis=0)).ravel().astype(np.float32)

            # 5. Compute IDF and category-weighted TF-IDF values
            # Smooth IDF: log((N + 1) / (df + 1)) + 1
            idf = np.log((num_media + 1.0) / (df + 1.0)) + 1.0

            # Apply category weights
            cat_multiplier = np.ones(num_tags, dtype=np.float32)
            for tid, col in tag_id_to_col.items():
                cat = tag_categories.get(tid, "general")
                cat_multiplier[col] = self.category_weights.get(cat, 1.0)

            tag_weights = idf * cat_multiplier  # shape: (num_tags,)

            # Weighted data for entries
            weighted_values = tag_weights[col_indices]

            # Construct weighted matrix
            m_csr = sp.csr_matrix(
                (weighted_values, (row_indices, col_indices)),
                shape=(num_media, num_tags),
                dtype=np.float32,
            )

            # 6. Row normalization (L2 norm per row for media cosine similarity)
            row_norms = np.sqrt(np.asarray(m_csr.multiply(m_csr).sum(axis=1)).ravel())
            row_inv_norms = np.zeros_like(row_norms, dtype=np.float32)
            non_zero_rows = row_norms > 0
            row_inv_norms[non_zero_rows] = 1.0 / row_norms[non_zero_rows]
            m_row_norm = sp.diags(row_inv_norms, dtype=np.float32).dot(m_csr).tocsr()

            # 7. Column normalization (L2 norm per column for tag cosine similarity)
            m_csc = m_csr.tocsc()
            col_norms = np.sqrt(np.asarray(m_csc.multiply(m_csc).sum(axis=0)).ravel())
            col_inv_norms = np.zeros_like(col_norms, dtype=np.float32)
            non_zero_cols = col_norms > 0
            col_inv_norms[non_zero_cols] = 1.0 / col_norms[non_zero_cols]
            m_col_norm = m_csc.dot(sp.diags(col_inv_norms, dtype=np.float32)).tocsc()

            new_data = SimilarityData(
                num_media=num_media,
                media_ids=media_ids,
                media_id_to_row=media_id_to_row,
                tag_ids=tag_ids,
                tag_id_to_col=tag_id_to_col,
                tag_categories=tag_categories,
                tag_names=tag_names,
                df=df,
                m_row_norm=m_row_norm,
                m_col_norm=m_col_norm,
                b_csr=b_csr,
                b_csc=b_csc,
            )

            with self._lock:
                self._data = new_data

            duration = time.perf_counter() - start_time
            logger.info(
                f"TF-IDF similarity index built in {duration:.2f}s "
                f"({num_media} media, {num_tags} tags, {len(valid_rows)} edges)"
            )
        except Exception as e:
            logger.error(f"Failed to build similarity index: {e}", exc_info=True)
        finally:
            with self._lock:
                self._is_building = False
                self._rebuild_pending = False

    def get_similar_media(
        self,
        media_id: int,
        limit: int = 12,
        album_media_ids: Optional[Set[int]] = None,
    ) -> List[Tuple[int, float]]:
        """
        Find top similar media items using cosine similarity of category-weighted TF-IDF vectors.

        Args:
            media_id: ID of the query media.
            limit: Maximum number of results to return.
            album_media_ids: Optional set of media IDs to restrict results to (for album context).

        Returns:
            List of (media_id, similarity_score) sorted descending by score.
        """
        data = self._data
        if data is None or limit <= 0:
            return []

        row_idx = data.media_id_to_row.get(media_id)
        if row_idx is None:
            return []

        # Extract normalized row vector (1 x num_tags)
        query_vec = data.m_row_norm.getrow(row_idx)
        if query_vec.nnz == 0:
            return []

        # Cosine similarity via dot product: (num_media x num_tags) . (num_tags x 1) -> (num_media,)
        scores = data.m_row_norm.dot(query_vec.T).toarray().ravel()

        # Exclude self
        scores[row_idx] = -1.0

        if album_media_ids is not None:
            # Mask out items not in the album
            album_row_indices = [
                data.media_id_to_row[mid]
                for mid in album_media_ids
                if mid in data.media_id_to_row and mid != media_id
            ]
            if not album_row_indices:
                return []
            mask = np.zeros(data.num_media, dtype=bool)
            mask[album_row_indices] = True
            scores[~mask] = -1.0

        # Filter positive scores
        positive_indices = np.where(scores > 1e-6)[0]
        if len(positive_indices) == 0:
            return []

        if len(positive_indices) > limit:
            # Efficient top-K selection
            partition_idx = np.argpartition(scores[positive_indices], -limit)[-limit:]
            top_candidates = positive_indices[partition_idx]
            sorted_top = top_candidates[np.argsort(scores[top_candidates])[::-1]]
        else:
            sorted_top = positive_indices[np.argsort(scores[positive_indices])[::-1]]

        return [(int(data.media_ids[idx]), float(scores[idx])) for idx in sorted_top[:limit]]

    def get_related_tags(
        self,
        tag_id: int,
        limit: int = 25,
        category_filter: Optional[str] = None,
    ) -> Optional[List[dict]]:
        """
        Find related tags for a given tag ID using TF-IDF column cosine similarity
        and return metrics (cosine, jaccard, overlap, frequency, co_count).

        Returns None if index is not ready or tag not found in index.
        """
        data = self._data
        if data is None:
            return None

        col_idx = data.tag_id_to_col.get(tag_id)
        if col_idx is None:
            return None

        # Media items having this tag
        query_media_rows = data.b_csc.getcol(col_idx).indices
        q_count = float(len(query_media_rows))
        if q_count == 0:
            return []

        # Fast co-occurrence counts across all tags: sum binary rows for media having the query tag
        co_counts = np.asarray(data.b_csr[query_media_rows, :].sum(axis=0)).ravel()

        # TF-IDF column cosine similarity: (num_tags x num_media) . (num_media x 1)
        query_col = data.m_col_norm.getcol(col_idx)
        cosine_scores = data.m_col_norm.T.dot(query_col).toarray().ravel()

        # Exclude self
        cosine_scores[col_idx] = -1.0
        co_counts[col_idx] = 0

        # Candidates: co_count > 0
        candidate_indices = np.where(co_counts > 0)[0]
        if len(candidate_indices) == 0:
            return []

        # Apply category filter if requested
        if category_filter:
            cat_lower = category_filter.lower()
            candidate_indices = np.array(
                [
                    idx
                    for idx in candidate_indices
                    if data.tag_categories.get(int(data.tag_ids[idx])) == cat_lower
                ],
                dtype=np.int32,
            )
            if len(candidate_indices) == 0:
                return []

        # Sort candidate tags by TF-IDF cosine score descending
        top_candidates = candidate_indices[np.argsort(cosine_scores[candidate_indices])[::-1]][:limit]

        results = []
        for c in top_candidates:
            target_tid = int(data.tag_ids[c])
            intersection = float(co_counts[c])
            t_count = float(data.df[c])

            frequency = intersection / q_count if q_count > 0 else 0.0
            min_count = min(q_count, t_count)
            overlap_coefficient = intersection / min_count if min_count > 0 else 0.0
            union = q_count + t_count - intersection
            jaccard_similarity = intersection / union if union > 0 else 0.0
            cos_sim = float(cosine_scores[c])

            results.append({
                "id": target_tid,
                "name": data.tag_names.get(target_tid, ""),
                "category": data.tag_categories.get(target_tid, "general"),
                "post_count": int(t_count),
                "co_count": int(intersection),
                "cosine_similarity": cos_sim,
                "jaccard_similarity": jaccard_similarity,
                "overlap_coefficient": overlap_coefficient,
                "frequency": frequency,
            })

        return results

    def get_suggested_tags(
        self,
        tag_names: List[str],
        limit: int = 20,
        category_filter: Optional[str] = None,
    ) -> Optional[List[dict]]:
        """
        Given a list of tag names, return suggested tags ranked by aggregated
        TF-IDF column cosine similarity across all input tags using category weights.

        Returns None if index is not ready, or a list of dicts if ready.
        """
        data = self._data
        if data is None or not tag_names:
            return None if data is None else []

        name_to_tid = {name.lower(): tid for tid, name in data.tag_names.items()}

        resolved_cols = []
        for name in tag_names:
            if not isinstance(name, str):
                continue
            cleaned = name.strip().lower()
            if not cleaned:
                continue
            tid = name_to_tid.get(cleaned)
            if tid is not None:
                col = data.tag_id_to_col.get(tid)
                if col is not None and col not in resolved_cols:
                    resolved_cols.append(col)

        if not resolved_cols:
            return []

        # Weighted combination of input query vectors
        weights_in = np.array([
            SUGGESTED_TAGS_CATEGORY_WEIGHTS.get(data.tag_categories.get(int(data.tag_ids[col]), "general"), 1.0)
            for col in resolved_cols
        ], dtype=np.float32)

        query_cols = data.m_col_norm[:, resolved_cols]
        query_vec = np.asarray(query_cols.dot(weights_in))

        # Dot product against all tags
        raw_cosine = np.asarray(data.m_col_norm.T.dot(query_vec)).ravel()

        # Scale candidate scores by target category weights
        cat_weights_target = np.array([
            SUGGESTED_TAGS_CATEGORY_WEIGHTS.get(data.tag_categories.get(int(tid), "general"), 1.0)
            for tid in data.tag_ids
        ], dtype=np.float32)

        cosine_scores = raw_cosine * cat_weights_target

        for col in resolved_cols:
            cosine_scores[col] = -1.0

        candidate_indices = np.where(cosine_scores > 1e-6)[0]
        if len(candidate_indices) == 0:
            return []

        if category_filter:
            cat_lower = category_filter.lower()
            candidate_indices = np.array(
                [
                    idx
                    for idx in candidate_indices
                    if data.tag_categories.get(int(data.tag_ids[idx])) == cat_lower
                ],
                dtype=np.int32,
            )
            if len(candidate_indices) == 0:
                return []

        if len(candidate_indices) > limit:
            partition_idx = np.argpartition(cosine_scores[candidate_indices], -limit)[-limit:]
            top_candidates = candidate_indices[partition_idx]
            sorted_top = top_candidates[np.argsort(cosine_scores[top_candidates])[::-1]]
        else:
            sorted_top = candidate_indices[np.argsort(cosine_scores[candidate_indices])[::-1]]

        results = []
        for c in sorted_top[:limit]:
            target_tid = int(data.tag_ids[c])
            t_count = float(data.df[c])
            cos_sim = float(cosine_scores[c])

            results.append({
                "id": target_tid,
                "name": data.tag_names.get(target_tid, ""),
                "category": data.tag_categories.get(target_tid, "general"),
                "post_count": int(t_count),
                "cosine_similarity": cos_sim,
            })

        return results

# Global singleton instance
def _make_index() -> SimilarityIndex:
    try:
        from ..config import settings
        return SimilarityIndex(category_weights=settings.SIMILARITY_WEIGHTS)
    except Exception:
        return SimilarityIndex()

similarity_index = _make_index()
_pending_rebuild_task: Optional[asyncio.Task] = None

async def schedule_rebuild(delay_seconds: float = 2.0) -> None:
    """Schedule a debounced similarity index rebuild."""
    global _pending_rebuild_task

    # Cancel any existing debounce timer that hasn't started the actual rebuild.
    if _pending_rebuild_task is not None and not _pending_rebuild_task.done():
        _pending_rebuild_task.cancel()

    similarity_index._rebuild_pending = True

    async def _delayed_rebuild() -> None:
        try:
            await asyncio.sleep(delay_seconds)
        except asyncio.CancelledError:
            return
        try:
            from ..database import SessionLocal
            await asyncio.to_thread(
                similarity_index.rebuild_from_session_factory, SessionLocal
            )
        finally:
            similarity_index._rebuild_pending = False

    _pending_rebuild_task = asyncio.create_task(_delayed_rebuild())
