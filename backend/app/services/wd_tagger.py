import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

import huggingface_hub
import numpy as np
import onnxruntime as rt
import pandas as pd
from PIL import Image

from ..utils.logger import logger

class WDTagger:
    """
    WD Tagger using ONNX models from SmilingWolf's collection.
    Optimized for CPU batch processing.
    """
    _instance = None
    _initialized = False
    _lock = threading.Lock()
    
    AVAILABLE_MODELS = {
        "wd-eva02-large-tagger-v3": "SmilingWolf/wd-eva02-large-tagger-v3",
        "wd-vit-tagger-v3": "SmilingWolf/wd-vit-tagger-v3",
        "wd-swinv2-tagger-v3": "SmilingWolf/wd-swinv2-tagger-v3",
        "wd-convnext-tagger-v3": "SmilingWolf/wd-convnext-tagger-v3",
        "wd-vit-large-tagger-v3": "SmilingWolf/wd-vit-large-tagger-v3",
    }
    
    # Speed ranking (relative, lower is faster)
    MODEL_SPEED_RANKING = {
        "wd-vit-tagger-v3": 1,        # Fastest
        "wd-convnext-tagger-v3": 2,
        "wd-swinv2-tagger-v3": 3,
        "wd-eva02-large-tagger-v3": 4,
        "wd-vit-large-tagger-v3": 5,  # Slowest
    }
    
    MODEL_FILENAME = "model.onnx"
    LABEL_FILENAME = "selected_tags.csv"
    
    # Optimal batch sizes per model (tuned for ~16GB RAM systems)
    OPTIMAL_BATCH_SIZES = {
        "wd-eva02-large-tagger-v3": 4,
        "wd-vit-tagger-v3": 16,
        "wd-swinv2-tagger-v3": 8,
        "wd-convnext-tagger-v3": 12,
        "wd-vit-large-tagger-v3": 2,
    }
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self._model = None
            self._tag_data = None
            self._target_size = None
            self._current_model_name = None
            self._input_name = None
            self._inference_lock = threading.Lock()
            self._unload_lock = threading.Lock()
            # Preprocessing can be parallelized
            self._num_preprocess_workers = min(4, (os.cpu_count() or 4))
            self._preprocess_executor = ThreadPoolExecutor(
                max_workers=self._num_preprocess_workers,
                thread_name_prefix="wd_preprocess"
            )
            self._dynamic_batch_size = 4
            self._oom_encountered = False
            
            self._idle_timeout = int(os.getenv("BLOMBOORU_WD_TAGGER_IDLE_TIMEOUT", 60))  # 1 min default
            self._unload_timer = None
            
            WDTagger._initialized = True

    def _reset_idle_timer(self):
        """Start or reset the countdown to unload the model."""
        with self._unload_lock:
            if self._unload_timer:
                self._unload_timer.cancel()
            
            if self._idle_timeout > 0:
                self._unload_timer = threading.Timer(self._idle_timeout, self._unload_model)
                self._unload_timer.daemon = True
                self._unload_timer.start()

    def _unload_model(self):
        """Unload the model and free RAM/VRAM if idle."""
        # Prevent unloading if an inference is currently running
        if not self._inference_lock.acquire(blocking=False):
            logger.info("Unload deferred: inference is currently running. Rescheduling...")
            self._reset_idle_timer()
            return
        
        try:
            if self._model is not None:
                logger.info(f"Idle for {self._idle_timeout}s, unloading WD Tagger to free RAM/VRAM...")
                self._model = None
                self._current_model_name = None
                
                import gc
                gc.collect()
                logger.info("WD Tagger model unloaded successfully.")
        finally:
            self._inference_lock.release()
    
    def _get_session_options(self, providers: list) -> rt.SessionOptions:
        sess_options = rt.SessionOptions()
        sess_options.graph_optimization_level = rt.GraphOptimizationLevel.ORT_ENABLE_ALL

        cpu_count = os.cpu_count() or 4
        sess_options.intra_op_num_threads = cpu_count
        sess_options.inter_op_num_threads = max(1, cpu_count // 2)
        sess_options.execution_mode = rt.ExecutionMode.ORT_PARALLEL
        sess_options.enable_mem_pattern = True

        if any(p == "CPUExecutionProvider" or (isinstance(p, tuple) and p[0] == "CPUExecutionProvider") for p in providers):
            sess_options.enable_cpu_mem_arena = True
        else:
            sess_options.enable_cpu_mem_arena = False

        return sess_options

    def _resolve_providers(self) -> list:
        forced = os.getenv("BLOMBOORU_WD_TAGGER_DEVICE", "auto").lower()  # auto | cuda | cpu
        available = rt.get_available_providers()

        if forced == "cpu":
            return ["CPUExecutionProvider"]

        if forced == "cuda":
            if "CUDAExecutionProvider" not in available:
                raise RuntimeError(
                    "BLOMBOORU_WD_TAGGER_DEVICE=cuda was set, but this onnxruntime "
                    "build has no CUDAExecutionProvider. Are you running the -cuda "
                    "image / installed onnxruntime-gpu?"
                )
            return [("CUDAExecutionProvider", self._cuda_provider_options()), "CPUExecutionProvider"]

        # auto (default): use CUDA if it's there, otherwise fall back silently
        if "CUDAExecutionProvider" in available:
            return [("CUDAExecutionProvider", self._cuda_provider_options()), "CPUExecutionProvider"]
        return ["CPUExecutionProvider"]

    def _cuda_provider_options(self) -> dict:
        return {
            "device_id": 0,
            "arena_extend_strategy": "kSameAsRequested",
            "cudnn_conv_algo_search": "HEURISTIC",
            "do_copy_in_default_stream": True,
        }

    def _run_with_oom_retry(self, batch_images: np.ndarray) -> np.ndarray:
        try:
            with self._inference_lock:
                return self._model.run(None, {self._input_name: batch_images})[0]
        except Exception as e:
            msg = str(e)
            is_oom = (
                "CUDA" in msg
                and ("memory" in msg.lower() or "alloc" in msg.lower())
                and batch_images.shape[0] > 1
            )
            if is_oom:
                logger.warning(f"CUDA OOM at batch size {batch_images.shape[0]}, retrying at half size")
                mid = batch_images.shape[0] // 2
                first = self._run_with_oom_retry(batch_images[:mid])
                second = self._run_with_oom_retry(batch_images[mid:])
                return np.concatenate([first, second], axis=0)
            raise
    
    def _process_chunk_oom_protected(
        self,
        file_paths: List[str],
        general_threshold: float,
        character_threshold: float,
        hide_rating_tags: bool,
        character_tags_first: bool
    ) -> Dict[str, List[Dict[str, Any]]]:
        try:
            prepared = self._prepare_images_parallel(file_paths)
            valid_items = [(fp, img) for fp, img in prepared if img is not None]
            failed_paths = [fp for fp, img in prepared if img is None]
            
            results = {fp: [] for fp in failed_paths}
            
            if valid_items:
                batch_images = np.stack([img for _, img in valid_items], axis=0)
                
                with self._inference_lock:
                    preds = self._model.run(None, {self._input_name: batch_images})[0]
                
                for (fp, _), scores in zip(valid_items, preds):
                    tags = self._extract_tags_from_scores(
                        scores, general_threshold, character_threshold,
                        hide_rating_tags, character_tags_first
                    )
                    results[fp] = tags
            
            return results
        except Exception as e:
            msg = str(e).lower()
            is_oom = (
                "memory" in msg or "alloc" in msg
            ) and len(file_paths) > 1
            
            if is_oom:
                logger.warning(f"OOM at chunk size {len(file_paths)}, halving and retrying...")
                self._oom_encountered = True
                
                current_size = len(file_paths)
                exp = 4
                while exp * 2 < current_size:
                    exp *= 2
                self._dynamic_batch_size = max(4, exp)
                
                mid = len(file_paths) // 2
                first_half = self._process_chunk_oom_protected(
                    file_paths[:mid], general_threshold, character_threshold,
                    hide_rating_tags, character_tags_first
                )
                second_half = self._process_chunk_oom_protected(
                    file_paths[mid:], general_threshold, character_threshold,
                    hide_rating_tags, character_tags_first
                )
                first_half.update(second_half)
                return first_half
            raise

    def _load_model(self, model_name: str = "wd-eva02-large-tagger-v3"):
        """Load the specified model with optimizations."""
        if model_name not in self.AVAILABLE_MODELS:
            raise ValueError(f"Unknown model: {model_name}. Available: {list(self.AVAILABLE_MODELS.keys())}")
        
        if self._current_model_name == model_name and self._model is not None:
            return
        
        model_repo = self.AVAILABLE_MODELS[model_name]
        
        def _fetch_paths(force_download: bool = False):
            if force_download:
                logger.info(f"Verifying hashes and re-downloading '{model_name}' if necessary...")
                return (
                    huggingface_hub.hf_hub_download(model_repo, self.LABEL_FILENAME, force_download=True),
                    huggingface_hub.hf_hub_download(model_repo, self.MODEL_FILENAME, force_download=True)
                )
            
            try:
                # Try to load from local cache first to avoid network requests
                return (
                    huggingface_hub.hf_hub_download(model_repo, self.LABEL_FILENAME, local_files_only=True),
                    huggingface_hub.hf_hub_download(model_repo, self.MODEL_FILENAME, local_files_only=True)
                )
            except huggingface_hub.LocalEntryNotFoundError:
                logger.info(f"Model '{model_name}' not found in cache. Downloading from HuggingFace...")
                return _fetch_paths(force_download=True)

        csv_path, model_path = _fetch_paths()
        
        try:
            # Attempt to load the model and labels
            df = pd.read_csv(csv_path)
            self._tag_data = {
                'names': df["name"].tolist(),
                'rating': np.where(df["category"] == 9)[0],
                'general': np.where(df["category"] == 0)[0],
                'character': np.where(df["category"] == 4)[0],
            }
            
            providers = self._resolve_providers()
            sess_options = self._get_session_options(providers)
            
            self._model = rt.InferenceSession(
                model_path, 
                sess_options=sess_options,
                providers=providers
            )
        except Exception as e:
            # If loading fails (e.g. corrupted file), force network check and re-download
            logger.warning(f"Failed to load model from cache: {e}. Verifying hashes and re-downloading...")
            csv_path, model_path = _fetch_paths(force_download=True)
            
            # Retry loading
            df = pd.read_csv(csv_path)
            self._tag_data = {
                'names': df["name"].tolist(),
                'rating': np.where(df["category"] == 9)[0],
                'general': np.where(df["category"] == 0)[0],
                'character': np.where(df["category"] == 4)[0],
            }
            
            providers = self._resolve_providers()
            sess_options = self._get_session_options(providers)
            
            try:
                self._model = rt.InferenceSession(
                    model_path, 
                    sess_options=sess_options,
                    providers=providers
                )
            except Exception as inner_e:
                logger.error(f"Failed to load ONNX model with providers {providers}: {inner_e}")
                raise

        input_info = self._model.get_inputs()[0]
        self._target_size = input_info.shape[2]
        self._input_name = input_info.name
        self._current_model_name = model_name

    def ensure_loaded(self, model_name: str = "wd-eva02-large-tagger-v3"):
        """Ensure the model is loaded."""
        if self._model is None or self._current_model_name != model_name:
            with self._lock:
                if self._model is None or self._current_model_name != model_name:
                    self._load_model(model_name)
        
        with self._unload_lock:
            if self._unload_timer:
                self._unload_timer.cancel()
    
    def _prepare_image(self, image: Image.Image) -> np.ndarray:
        """
        Preprocess a single image for the model.
        Optimized version with minimal allocations.
        """
        width, height = image.size
        
        # Handle transparency
        if image.mode == 'RGBA':
            # Create white background and composite
            background = Image.new("RGB", image.size, (255, 255, 255))
            background.paste(image, mask=image.split()[3])
            image = background
        elif image.mode != 'RGB':
            image = image.convert("RGB")
        
        # Pad to square
        max_dim = max(width, height)
        if width != height:
            pad_left = (max_dim - width) // 2
            pad_top = (max_dim - height) // 2
            padded_image = Image.new("RGB", (max_dim, max_dim), (255, 255, 255))
            padded_image.paste(image, (pad_left, pad_top))
            image = padded_image
        
        # Resize to target size
        if image.size[0] != self._target_size:
            image = image.resize(
                (self._target_size, self._target_size), 
                Image.BICUBIC
            )
        
        # Convert to numpy array in BGR format (model expects BGR)
        # Using np.asarray is faster than np.array as it doesn't copy if not needed
        image_array = np.asarray(image, dtype=np.float32)
        
        # RGB to BGR conversion using fancy indexing
        image_array = image_array[:, :, ::-1].copy()
        
        return image_array
    
    def _prepare_image_from_path(self, file_path: str) -> Tuple[str, Optional[np.ndarray]]:
        """Load and prepare an image from file path."""
        try:
            ext = Path(file_path).suffix.lower()
            
            if ext == '.gif':
                image = self._extract_gif_frame(file_path)
            elif ext in ['.mp4', '.webm', '.mov', '.avi', '.mkv']:
                image = self._extract_video_frame(file_path)
            else:
                image = Image.open(file_path)
            
            prepared = self._prepare_image(image)
            
            # Close image to free memory
            if hasattr(image, 'close'):
                image.close()
            
            return (file_path, prepared)
        except Exception as e:
            return (file_path, None)
    
    def _prepare_images_parallel(
        self, 
        file_paths: List[str],
        max_workers: Optional[int] = None
    ) -> List[Tuple[str, Optional[np.ndarray]]]:
        """Prepare multiple images in parallel."""
        if max_workers is None:
            max_workers = self._num_preprocess_workers
        
        results = []
        
        # Submit all tasks
        futures = {
            self._preprocess_executor.submit(self._prepare_image_from_path, fp): fp 
            for fp in file_paths
        }
        
        # Collect results in submission order
        path_to_result = {}
        for future in as_completed(futures):
            file_path, prepared = future.result()
            path_to_result[file_path] = prepared
        
        # Return in original order
        return [(fp, path_to_result.get(fp)) for fp in file_paths]
    
    def _extract_tags_from_scores(
        self,
        scores: np.ndarray,
        general_threshold: float,
        character_threshold: float,
        hide_rating_tags: bool,
        character_tags_first: bool
    ) -> List[Dict[str, Any]]:
        """Extract tags from model output scores using vectorized operations."""
        results = []
        names = self._tag_data['names']
        
        # Character tags - vectorized threshold check
        char_indices = self._tag_data['character']
        char_scores = scores[char_indices]
        char_mask = char_scores >= character_threshold
        
        for idx, score in zip(char_indices[char_mask], char_scores[char_mask]):
            results.append({
                'name': names[idx],
                'category': 'character',
                'confidence': float(score)
            })
        
        # General tags
        gen_indices = self._tag_data['general']
        gen_scores = scores[gen_indices]
        gen_mask = gen_scores >= general_threshold
        
        for idx, score in zip(gen_indices[gen_mask], gen_scores[gen_mask]):
            results.append({
                'name': names[idx],
                'category': 'general',
                'confidence': float(score)
            })
        
        # Rating tags
        if not hide_rating_tags:
            rating_indices = self._tag_data['rating']
            rating_scores = scores[rating_indices]
            rating_mask = rating_scores > 0.5
            
            for idx, score in zip(rating_indices[rating_mask], rating_scores[rating_mask]):
                results.append({
                    'name': names[idx],
                    'category': 'rating',
                    'confidence': float(score)
                })
        
        # Sort results
        if character_tags_first:
            # Group by category then sort by confidence
            char_tags = sorted(
                [r for r in results if r['category'] == 'character'],
                key=lambda x: x['confidence'], 
                reverse=True
            )
            general_tags = sorted(
                [r for r in results if r['category'] == 'general'],
                key=lambda x: x['confidence'], 
                reverse=True
            )
            rating_tags = sorted(
                [r for r in results if r['category'] == 'rating'],
                key=lambda x: x['confidence'], 
                reverse=True
            )
            results = char_tags + general_tags + rating_tags
        else:
            results.sort(key=lambda x: x['confidence'], reverse=True)
        
        return results
    
    def predict(
        self,
        image: Image.Image,
        general_threshold: float = 0.35,
        character_threshold: float = 0.85,
        hide_rating_tags: bool = True,
        character_tags_first: bool = True,
        model_name: str = "wd-eva02-large-tagger-v3"
    ) -> List[Dict[str, Any]]:
        """Predict tags for a single image."""
        self.ensure_loaded(model_name)
        
        processed_image = self._prepare_image(image)
        processed_batch = np.expand_dims(processed_image, axis=0)
        
        preds = self._run_with_oom_retry(processed_batch)
        
        scores = preds[0]  # First (and only) batch item
        
        results = self._extract_tags_from_scores(
            scores, general_threshold, character_threshold,
            hide_rating_tags, character_tags_first
        )
        
        self._reset_idle_timer()
        return results
    
    def predict_batch(
        self,
        images: List[np.ndarray],
        general_threshold: float = 0.35,
        character_threshold: float = 0.85,
        hide_rating_tags: bool = True,
        character_tags_first: bool = True,
        model_name: str = "wd-eva02-large-tagger-v3"
    ) -> List[List[Dict[str, Any]]]:
        """
        Predict tags for a batch of preprocessed images.
        
        Args:
            images: List of preprocessed image arrays (from _prepare_image)
        """
        if not images:
            return []
        
        self.ensure_loaded(model_name)
        
        # Stack into batch
        batch = np.stack(images, axis=0)
        
        # Run inference
        preds = self._run_with_oom_retry(batch)
        
        # Extract tags for each image
        results = []
        for scores in preds:
            tags = self._extract_tags_from_scores(
                scores, general_threshold, character_threshold,
                hide_rating_tags, character_tags_first
            )
            results.append(tags)
        
        self._reset_idle_timer()
        return results
    
    def predict_from_file(
        self,
        file_path: str,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """Predict tags from a single file path."""
        _, prepared = self._prepare_image_from_path(file_path)
        
        if prepared is None:
            return []
        
        model_name = kwargs.get('model_name', 'wd-eva02-large-tagger-v3')
        self.ensure_loaded(model_name)
        
        batch = np.expand_dims(prepared, axis=0)
        
        preds = self._run_with_oom_retry(batch)
        
        results = self._extract_tags_from_scores(
            preds[0],
            kwargs.get('general_threshold', 0.35),
            kwargs.get('character_threshold', 0.85),
            kwargs.get('hide_rating_tags', True),
            kwargs.get('character_tags_first', True)
        )
        
        self._reset_idle_timer()
        return results
    
    def predict_from_files_batch(
        self,
        file_paths: List[str],
        general_threshold: float = 0.35,
        character_threshold: float = 0.85,
        hide_rating_tags: bool = True,
        character_tags_first: bool = True,
        model_name: str = "wd-eva02-large-tagger-v3",
        batch_size: Optional[int] = None,
        progress_callback: Optional[callable] = None
    ) -> List[Tuple[str, List[Dict[str, Any]]]]:
        """
        Predict tags for multiple files efficiently using batch processing.
        
        Args:
            file_paths: List of file paths to process
            progress_callback: Optional callback(processed, total) for progress updates
            
        Returns:
            List of (file_path, tags) tuples in the same order as input
        """
        if not file_paths:
            return []
        
        self.ensure_loaded(model_name)
        
        if batch_size is None:
            target_size = self._dynamic_batch_size
        else:
            target_size = batch_size
        
        total = len(file_paths)
        results = {}
        processed_count = 0
        
        i = 0
        while i < total:
            actual_chunk_size = min(target_size, total - i)
            batch_paths = file_paths[i:i + actual_chunk_size]
            
            chunk_results = self._process_chunk_oom_protected(
                batch_paths, general_threshold, character_threshold,
                hide_rating_tags, character_tags_first
            )
            results.update(chunk_results)
            
            processed_count += len(batch_paths)
            
            if progress_callback:
                progress_callback(processed_count, total)
                
            i += actual_chunk_size
            
            if batch_size is None:
                if self._oom_encountered:
                    self._dynamic_batch_size = min(self._dynamic_batch_size + 1, 64)
                else:
                    self._dynamic_batch_size = min(self._dynamic_batch_size * 2, 64)
                target_size = self._dynamic_batch_size
        
        # Return in original order
        self._reset_idle_timer()
        return [(fp, results.get(fp, [])) for fp in file_paths]
    
    def predict_from_files_streaming(
        self,
        file_paths: List[str],
        general_threshold: float = 0.35,
        character_threshold: float = 0.85,
        hide_rating_tags: bool = True,
        character_tags_first: bool = True,
        model_name: str = "wd-eva02-large-tagger-v3",
        batch_size: Optional[int] = None
    ) -> Generator[Tuple[str, List[Dict[str, Any]]], None, None]:
        """
        Stream prediction results as they complete.
        
        Yields (file_path, tags) tuples as each batch completes.
        """
        if not file_paths:
            return
        
        self.ensure_loaded(model_name)
        
        if batch_size is None:
            target_size = self._dynamic_batch_size
        else:
            target_size = batch_size
            
        i = 0
        total = len(file_paths)
        try:
            while i < total:
                actual_chunk_size = min(target_size, total - i)
                batch_paths = file_paths[i:i + actual_chunk_size]
                
                chunk_results = self._process_chunk_oom_protected(
                    batch_paths, general_threshold, character_threshold,
                    hide_rating_tags, character_tags_first
                )
                
                for fp in batch_paths:
                    yield (fp, chunk_results.get(fp, []))
                
                i += actual_chunk_size
                
                if batch_size is None:
                    if self._oom_encountered:
                        self._dynamic_batch_size = min(self._dynamic_batch_size + 1, 64)
                    else:
                        self._dynamic_batch_size = min(self._dynamic_batch_size * 2, 64)
                    target_size = self._dynamic_batch_size
        finally:
            self._reset_idle_timer()
    
    def _extract_gif_frame(self, file_path: str, frame_index: int = 0) -> Image.Image:
        """Extract a frame from a GIF."""
        with Image.open(file_path) as gif:
            gif.seek(frame_index)
            return gif.convert('RGB')
    
    def _extract_video_frame(self, file_path: str, frame_index: int = 0) -> Image.Image:
        """Extract a frame from a video file using ffmpeg."""
        import subprocess
        import tempfile
        
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            tmp_path = tmp.name
        
        try:
            cmd = [
                'ffmpeg', '-i', file_path,
                '-vf', f'select=eq(n\\,{frame_index})',
                '-vframes', '1',
                '-y', '-loglevel', 'error',
                tmp_path
            ]
            subprocess.run(cmd, capture_output=True, check=True, timeout=30)
            
            image = Image.open(tmp_path).convert('RGB')
            return image
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
    
    @property
    def is_loaded(self) -> bool:
        return self._model is not None
    
    @property
    def current_model(self) -> Optional[str]:
        return self._current_model_name
    
    def get_optimal_batch_size(self, model_name: Optional[str] = None) -> int:
        """Get optimal batch size for the specified or current model."""
        name = model_name or self._current_model_name or "wd-eva02-large-tagger-v3"
        return self.OPTIMAL_BATCH_SIZES.get(name, 4)
    
    def shutdown(self):
        """Clean up resources."""
        if hasattr(self, '_preprocess_executor'):
            self._preprocess_executor.shutdown(wait=False)

# Global singleton instance
_tagger_instance: Optional[WDTagger] = None
_tagger_lock = threading.Lock()

def get_wd_tagger() -> WDTagger:
    """Get the singleton WD Tagger instance."""
    global _tagger_instance
    if _tagger_instance is None:
        with _tagger_lock:
            if _tagger_instance is None:
                _tagger_instance = WDTagger()
    return _tagger_instance
