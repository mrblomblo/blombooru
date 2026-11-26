from concurrent.futures import ThreadPoolExecutor, as_completed
import gc
import os
from pathlib import Path
import threading
import time
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple

import huggingface_hub
import numpy as np
import onnxruntime as rt
try:
    from huggingface_hub.utils._errors import LocalEntryNotFoundError
except ImportError:
    from huggingface_hub.errors import LocalEntryNotFoundError
from PIL import Image

from ...config import settings
from ...utils import image_plugins
from ...utils.logger import logger
from .custom_models import CUSTOM_MODEL_PREFIX, custom_model_manager, is_custom_model_id
from .downloader import (
    DownloadCancelledException,
    DownloadTask,
    cancellable_hf_download,
)
from .preprocessing import (
    apply_output_postprocessing,
    extract_gif_frame,
    extract_tags_from_scores,
    extract_top_raw_tags,
    extract_video_frame,
    prepare_image,
)
from .registry import (
    AVAILABLE_MODELS,
    BUILTIN_MODEL_CONFIGS,
    LABEL_FILENAME,
    LEGACY_MODEL_VARIANTS,
    MODEL_ACCURACY_RANKING,
    MODEL_CONFIG_BOUNDS,
    MODEL_DOWNLOAD_SIZES_BYTES,
    MODEL_FILENAME,
    MODEL_REPO_SPECS,
    MODEL_SPEED_RANKING,
    OPTIMAL_BATCH_SIZES,
    ModelInferenceConfig,
    clamp_model_config,
    inspect_onnx_session,
    parse_label_data,
)

class WDTagger:
    """
    ONNX AI Tagger supporting built-in HuggingFace models and user-uploaded custom models.
    Optimized for CPU and CUDA batch processing.
    """
    _instance = None
    _initialized = False
    _lock = threading.Lock()
    _downloads_lock = threading.Lock()
    _active_downloads: Dict[str, DownloadTask] = {}

    AVAILABLE_MODELS = AVAILABLE_MODELS
    BUILTIN_MODEL_CONFIGS = BUILTIN_MODEL_CONFIGS
    LEGACY_MODEL_VARIANTS = LEGACY_MODEL_VARIANTS
    MODEL_REPO_SPECS = MODEL_REPO_SPECS
    MODEL_SPEED_RANKING = MODEL_SPEED_RANKING
    MODEL_ACCURACY_RANKING = MODEL_ACCURACY_RANKING
    MODEL_FILENAME = MODEL_FILENAME
    LABEL_FILENAME = LABEL_FILENAME
    OPTIMAL_BATCH_SIZES = OPTIMAL_BATCH_SIZES
    MODEL_DOWNLOAD_SIZES_BYTES = MODEL_DOWNLOAD_SIZES_BYTES
    CUSTOM_MODEL_PREFIX = CUSTOM_MODEL_PREFIX

    @classmethod
    def is_valid_model(cls, model_name: Optional[str]) -> bool:
        if not model_name or not isinstance(model_name, str):
            return False
        if is_custom_model_id(model_name):
            return custom_model_manager.exists(model_name)
        return model_name in cls.AVAILABLE_MODELS

    @classmethod
    def get_all_model_ids(cls) -> List[str]:
        builtin_ids = list(cls.AVAILABLE_MODELS.keys())
        custom_ids = [m["id"] for m in custom_model_manager.list_models()]
        return builtin_ids + custom_ids

    @classmethod
    def get_display_name(cls, model_name: str) -> str:
        if is_custom_model_id(model_name):
            entry = custom_model_manager.get_model(model_name)
            if entry:
                return entry.get("display_name") or model_name
        return model_name

    @classmethod
    def get_default_config(cls, model_name: str) -> ModelInferenceConfig:
        if is_custom_model_id(model_name):
            return custom_model_manager.get_default_config(model_name)
        if model_name in cls.BUILTIN_MODEL_CONFIGS:
            return cls.BUILTIN_MODEL_CONFIGS[model_name]
        raise ValueError(f"Unknown model: {model_name}")

    @classmethod
    def get_effective_config(cls, model_name: str) -> ModelInferenceConfig:
        if is_custom_model_id(model_name):
            return custom_model_manager.get_effective_config(model_name)
        if model_name in cls.AVAILABLE_MODELS:
            default_cfg = cls.get_default_config(model_name)
            saved_map = settings.WD_TAGGER_SETTINGS.get("model_settings") or {}
            overrides = saved_map.get(model_name) if isinstance(saved_map, dict) else None
            return clamp_model_config(overrides, base=default_cfg)
        raise ValueError(f"Unknown model: {model_name}")

    @classmethod
    def is_downloading(cls, model_name: str) -> bool:
        """Check if a model is currently being downloaded."""
        if is_custom_model_id(model_name):
            return False
        with cls._downloads_lock:
            return model_name in cls._active_downloads

    @classmethod
    def get_repo_files(cls, repo_id: Optional[str]) -> Tuple[List[str], str, str]:
        """Return (required_files, model_filename, label_filename) for a given repo."""
        if repo_id and repo_id in cls.MODEL_REPO_SPECS:
            spec = cls.MODEL_REPO_SPECS[repo_id]
            return spec["required_files"], spec["model_file"], spec["label_file"]
        return ["model.onnx", "selected_tags.csv"], "model.onnx", "selected_tags.csv"

    @classmethod
    def is_repo_downloaded(cls, repo_id: str) -> bool:
        """Check if all required files for a repository are present in local cache."""
        try:
            required_files, _, _ = cls.get_repo_files(repo_id)
            for fname in required_files:
                cached = huggingface_hub.try_to_load_from_cache(
                    repo_id, fname, cache_dir=settings.MODELS_DIR
                )
                if not (isinstance(cached, str) and os.path.exists(cached)):
                    return False
            return True
        except Exception:
            return False

    @classmethod
    def get_active_repo_id(cls, model_name: str) -> str:
        """Primary repo if downloaded, or installed legacy variant, or primary if none."""
        if model_name not in cls.AVAILABLE_MODELS:
            raise ValueError(f"Unknown model: {model_name}. Available: {list(cls.AVAILABLE_MODELS.keys())}")
        primary_repo = cls.AVAILABLE_MODELS[model_name]
        if cls.is_repo_downloaded(primary_repo):
            return primary_repo
        for legacy_repo in cls.LEGACY_MODEL_VARIANTS.get(model_name, []):
            if cls.is_repo_downloaded(legacy_repo):
                return legacy_repo
        return primary_repo

    @classmethod
    def get_model_filenames(cls, model_name: str) -> Tuple[str, str]:
        """Return (model_filename, label_filename) for a given model."""
        if is_custom_model_id(model_name):
            entry = custom_model_manager.get_model(model_name)
            if not entry:
                raise ValueError(f"Unknown custom model: {model_name}")
            return entry["model_file"], entry["label_file"]
        repo_id = cls.get_active_repo_id(model_name) if model_name in cls.AVAILABLE_MODELS else None
        _, model_file, label_file = cls.get_repo_files(repo_id)
        return model_file, label_file

    @classmethod
    def is_model_downloaded(cls, model_name: str) -> bool:
        """Check if a model is ready on local disk without acquiring file locks."""
        if is_custom_model_id(model_name):
            return custom_model_manager.exists(model_name) and custom_model_manager.is_files_present(model_name)
        if model_name not in cls.AVAILABLE_MODELS:
            return False
        if cls.is_downloading(model_name):
            return False
        primary_repo = cls.AVAILABLE_MODELS[model_name]
        if cls.is_repo_downloaded(primary_repo):
            return True
        for legacy_repo in cls.LEGACY_MODEL_VARIANTS.get(model_name, []):
            if cls.is_repo_downloaded(legacy_repo):
                return True
        return False

    @classmethod
    def get_active_download(cls, model_name: str) -> Optional[DownloadTask]:
        """Get the active download task for a model if one exists."""
        with cls._downloads_lock:
            return cls._active_downloads.get(model_name)

    @classmethod
    def register_download(cls, model_name: str) -> Tuple[DownloadTask, bool]:
        """Register a new download task or get an existing one. Returns (task, is_new)."""
        with cls._downloads_lock:
            if model_name in cls._active_downloads:
                return cls._active_downloads[model_name], False
            task = DownloadTask(model_name)
            cls._active_downloads[model_name] = task
            return task, True

    @classmethod
    def unregister_download(cls, model_name: str):
        """Unregister a download task."""
        with cls._downloads_lock:
            cls._active_downloads.pop(model_name, None)

    @classmethod
    def cancel_download(cls, model_name: str):
        """Cancel an active model download."""
        with cls._downloads_lock:
            task = cls._active_downloads.get(model_name)
            if task:
                task.cancel()

    @classmethod
    def cancel_all_downloads(cls):
        """Cancel all active downloads."""
        with cls._downloads_lock:
            for task in list(cls._active_downloads.values()):
                task.cancel()

    @classmethod
    def get_download_size_bytes(cls, model_name: str, repo_id: Optional[str] = None) -> int:
        if is_custom_model_id(model_name):
            return custom_model_manager.get_size_bytes(model_name)
        target_repo = repo_id or (cls.get_active_repo_id(model_name) if model_name in cls.AVAILABLE_MODELS else None)
        if target_repo and target_repo in cls.MODEL_REPO_SPECS:
            return cls.MODEL_REPO_SPECS[target_repo]["download_size_bytes"]
        return cls.MODEL_DOWNLOAD_SIZES_BYTES.get(model_name, int(500 * 1024 * 1024))

    @classmethod
    def get_download_size_mb(cls, model_name: str) -> float:
        size_bytes = cls.get_download_size_bytes(model_name)
        if is_custom_model_id(model_name):
            return round(size_bytes / (1024 * 1024), 1)
        return int(round(size_bytes / (1024 * 1024)))

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
            self._static_spatial_size = None
            self._current_model_name = None
            self._input_name = None
            self._input_shape = []
            self._input_dtype = np.float32
            self._is_nchw = False
            self._fixed_batch_one = False
            self._outputs_meta = []
            self._active_providers = []
            self._inference_lock = threading.Lock()
            self._unload_lock = threading.Lock()
            # Preprocessing can be parallelized
            self._num_preprocess_workers = min(4, (os.cpu_count() or 4))
            self._preprocess_executor = ThreadPoolExecutor(
                max_workers=self._num_preprocess_workers,
                thread_name_prefix="wd_preprocess"
            )
            self._dynamic_batch_size = 1
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
                self._clear_loaded_state()
                gc.collect()
                logger.info("WD Tagger model unloaded successfully.")
        finally:
            self._inference_lock.release()

    def _clear_loaded_state(self):
        self._model = None
        self._tag_data = None
        self._current_model_name = None
        self._target_size = None
        self._static_spatial_size = None
        self._input_name = None
        self._input_shape = []
        self._input_dtype = np.float32
        self._is_nchw = False
        self._fixed_batch_one = False
        self._outputs_meta = []
        self._active_providers = []
        self._dynamic_batch_size = 1
        self._oom_encountered = False

    def unload_model(self, model_name: Optional[str] = None) -> bool:
        """Explicitly unload the active model (or only if matching model_name) without stopping thread pools."""
        with self._lock:
            with self._unload_lock:
                if self._unload_timer:
                    self._unload_timer.cancel()
                    self._unload_timer = None
            with self._inference_lock:
                if self._model is None:
                    return False
                if model_name is not None and self._current_model_name != model_name:
                    return False
                self._clear_loaded_state()
                gc.collect()
                return True

    def _get_session_options(self, providers: list) -> rt.SessionOptions:
        sess_options = rt.SessionOptions()
        sess_options.graph_optimization_level = rt.GraphOptimizationLevel.ORT_ENABLE_ALL

        cpu_count = os.cpu_count() or 4
        sess_options.intra_op_num_threads = cpu_count
        sess_options.inter_op_num_threads = max(1, cpu_count // 2)
        sess_options.execution_mode = rt.ExecutionMode.ORT_SEQUENTIAL
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

    def _resolve_loaded_config(
        self,
        config_override: Optional[ModelInferenceConfig] = None,
    ) -> ModelInferenceConfig:
        if config_override is not None:
            return config_override
        name = self._current_model_name or "wd-eva02-large-tagger-v3"
        cfg = self.get_effective_config(name)

        # Preserve legacy variant spatial dimension when built-in input_size was not explicitly overridden
        if (
            not is_custom_model_id(name)
            and self._static_spatial_size
            and self._static_spatial_size != cfg.input_size
        ):
            saved_overrides = (settings.WD_TAGGER_SETTINGS.get("model_settings") or {}).get(name)
            if not isinstance(saved_overrides, dict) or "input_size" not in saved_overrides:
                cfg = clamp_model_config({"input_size": self._static_spatial_size}, base=cfg)
        return cfg

    def _execute_raw_session(
        self,
        batch_images: np.ndarray,
        output_index: int = 0,
    ) -> np.ndarray:
        out_names = None
        if self._outputs_meta:
            clamped_idx = min(max(0, int(output_index)), len(self._outputs_meta) - 1)
            out_names = [self._outputs_meta[clamped_idx]["name"]]

        if getattr(self, "_fixed_batch_one", False):
            with self._inference_lock:
                if batch_images.shape[0] == 1:
                    raw_preds = self._model.run(out_names, {self._input_name: batch_images})[0]
                else:
                    outs = []
                    for i in range(batch_images.shape[0]):
                        out = self._model.run(out_names, {self._input_name: batch_images[i:i + 1]})[0]
                        outs.append(out[0])
                    raw_preds = np.stack(outs, axis=0)
            return raw_preds

        try:
            with self._inference_lock:
                return self._model.run(out_names, {self._input_name: batch_images})[0]
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
                first = self._execute_raw_session(batch_images[:mid], output_index=output_index)
                second = self._execute_raw_session(batch_images[mid:], output_index=output_index)
                return np.concatenate([first, second], axis=0)
            raise

    def _run_with_oom_retry(
        self,
        batch_images: np.ndarray,
        config: Optional[ModelInferenceConfig] = None,
    ) -> np.ndarray:
        cfg = self._resolve_loaded_config(config)
        raw_preds = self._execute_raw_session(batch_images, output_index=cfg.output_index)
        probs, _ = apply_output_postprocessing(
            raw_preds,
            output_activation=cfg.output_activation,
            temperature=cfg.temperature,
        )
        return probs

    def _process_chunk_oom_protected(
        self,
        file_paths: List[str],
        general_threshold: float,
        character_threshold: float,
        hide_rating_tags: bool,
        character_tags_first: bool,
        is_cancelled: Optional[Callable[[], bool]] = None,
        config: Optional[ModelInferenceConfig] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        if is_cancelled and is_cancelled():
            return {}
        cfg = self._resolve_loaded_config(config)
        try:
            prepared = self._prepare_images_parallel(
                file_paths,
                is_cancelled=is_cancelled,
                config=cfg,
            )
            if is_cancelled and is_cancelled():
                return {}
            valid_items = [(fp, img) for fp, img in prepared if img is not None]
            failed_paths = [fp for fp, img in prepared if img is None]

            results = {fp: [] for fp in failed_paths}

            if valid_items:
                if is_cancelled and is_cancelled():
                    return {}
                batch_images = np.stack([img for _, img in valid_items], axis=0)

                preds = self._run_with_oom_retry(batch_images, config=cfg)

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
                max_batch = cfg.batch_size
                if getattr(self, '_fixed_batch_one', False) or max_batch <= 1:
                    self._dynamic_batch_size = 1
                else:
                    exp = 1
                    while exp * 2 < current_size:
                        exp *= 2
                    self._dynamic_batch_size = max(1, min(exp, max_batch))

                mid = len(file_paths) // 2
                first_half = self._process_chunk_oom_protected(
                    file_paths[:mid], general_threshold, character_threshold,
                    hide_rating_tags, character_tags_first,
                    is_cancelled=is_cancelled,
                    config=cfg,
                )
                second_half = self._process_chunk_oom_protected(
                    file_paths[mid:], general_threshold, character_threshold,
                    hide_rating_tags, character_tags_first,
                    is_cancelled=is_cancelled,
                    config=cfg,
                )
                first_half.update(second_half)
                return first_half
            raise

    def _parse_label_data(self, label_path: str) -> dict:
        """Parse tag labels from CSV, JSON, or TXT."""
        return parse_label_data(label_path)

    def _open_session(self, model_path: str, label_path: str):
        """Parse labels and initialize an ONNX InferenceSession with resolved providers."""
        self._tag_data = self._parse_label_data(label_path)
        providers = self._resolve_providers()
        sess_options = self._get_session_options(providers)
        try:
            self._model = rt.InferenceSession(
                model_path,
                sess_options=sess_options,
                providers=providers,
            )
        except Exception as exc:
            logger.error(f"Failed to load ONNX model with providers {providers}: {exc}")
            raise

    def _record_loaded_session_metadata(self, model_name: str):
        meta = inspect_onnx_session(self._model)
        self._input_name = meta["input_name"]
        self._input_shape = meta["raw_input_shape"]
        self._input_dtype = np.float16 if meta["input_dtype"] == "float16" else np.float32
        self._is_nchw = meta["is_nchw"]
        self._static_spatial_size = meta["static_spatial_size"]
        self._target_size = meta["detected_size"]
        self._fixed_batch_one = meta["fixed_batch_one"]
        self._outputs_meta = meta["outputs"]
        self._active_providers = list(self._model.get_providers())
        self._dynamic_batch_size = 1
        self._oom_encountered = False
        self._current_model_name = model_name

    def _load_model(
        self,
        model_name: str = "wd-eva02-large-tagger-v3",
        is_cancelled: Optional[Callable[[], bool]] = None,
        progress_callback: Optional[Callable[[dict], None]] = None
    ):
        """Load the specified built-in or custom model with optimizations."""
        if not self.is_valid_model(model_name):
            raise ValueError(f"Unknown model: {model_name}. Available: {self.get_all_model_ids()}")

        if self._current_model_name == model_name and self._model is not None:
            return

        if is_cancelled and is_cancelled():
            raise DownloadCancelledException("Operation cancelled")

        # Custom models live in settings.CUSTOM_MODELS_DIR and never touch HuggingFace
        if is_custom_model_id(model_name):
            try:
                model_path_obj, label_path_obj = custom_model_manager.get_model_paths(model_name)
            except KeyError as exc:
                raise ValueError(f"Unknown custom model: {model_name}") from exc

            if not model_path_obj.is_file() or not label_path_obj.is_file():
                raise FileNotFoundError(
                    f"Files for custom model '{model_name}' are missing on disk."
                )

            self._open_session(str(model_path_obj), str(label_path_obj))
            self._record_loaded_session_metadata(model_name)
            return

        model_repo = self.get_active_repo_id(model_name)

        def _fetch_paths(force_download: bool = False):
            if is_cancelled and is_cancelled():
                raise DownloadCancelledException("Operation cancelled")

            repo_to_fetch = self.AVAILABLE_MODELS[model_name] if force_download else model_repo
            req_files, model_fname, label_fname = self.get_repo_files(repo_to_fetch)
            expected_total = self.get_download_size_bytes(model_name, repo_id=repo_to_fetch)

            if force_download:
                logger.info(f"Verifying hashes and re-downloading '{model_name}' ({repo_to_fetch}) if necessary...")
                with cancellable_hf_download(is_cancelled, progress_callback, expected_total_bytes=expected_total):
                    paths = {}
                    for fname in req_files:
                        paths[fname] = huggingface_hub.hf_hub_download(
                            repo_to_fetch,
                            fname,
                            force_download=True,
                            cache_dir=settings.MODELS_DIR
                        )
                    return paths[label_fname], paths[model_fname]

            try:
                # Try to load from local cache first to avoid network requests
                paths = {}
                for fname in req_files:
                    paths[fname] = huggingface_hub.hf_hub_download(
                        repo_to_fetch,
                        fname,
                        local_files_only=True,
                        cache_dir=settings.MODELS_DIR
                    )
                return paths[label_fname], paths[model_fname]
            except LocalEntryNotFoundError:
                logger.info(f"Model '{model_name}' not found in cache. Downloading from HuggingFace...")
                return _fetch_paths(force_download=True)

        label_path, model_path = _fetch_paths()

        if is_cancelled and is_cancelled():
            raise DownloadCancelledException("Operation cancelled")

        try:
            self._open_session(model_path, label_path)
        except Exception as e:
            if isinstance(e, DownloadCancelledException):
                raise
            # If loading fails (e.g. corrupted file), force network check and re-download
            logger.warning(f"Failed to load model from cache: {e}. Verifying hashes and re-downloading...")
            label_path, model_path = _fetch_paths(force_download=True)

            if is_cancelled and is_cancelled():
                raise DownloadCancelledException("Operation cancelled")

            self._open_session(model_path, label_path)

        self._record_loaded_session_metadata(model_name)

    def ensure_loaded(
        self,
        model_name: str = "wd-eva02-large-tagger-v3",
        is_cancelled: Optional[Callable[[], bool]] = None,
        progress_callback: Optional[Callable[[dict], None]] = None
    ):
        """Ensure the model is loaded."""
        if is_cancelled and is_cancelled():
            raise DownloadCancelledException("Operation cancelled")
        if self._model is None or self._current_model_name != model_name:
            with self._lock:
                if is_cancelled and is_cancelled():
                    raise DownloadCancelledException("Operation cancelled")
                if self._model is None or self._current_model_name != model_name:
                    self._load_model(
                        model_name,
                        is_cancelled=is_cancelled,
                        progress_callback=progress_callback
                    )

        with self._unload_lock:
            if self._unload_timer:
                self._unload_timer.cancel()

    def get_loaded_model_info(self) -> Dict[str, Any]:
        return {
            "input_name": self._input_name,
            "input_shape": [d if isinstance(d, int) else str(d) for d in (self._input_shape or [])],
            "input_dtype": "float16" if self._input_dtype == np.float16 else "float32",
            "fixed_batch_one": bool(self._fixed_batch_one),
            "outputs": list(self._outputs_meta or []),
            "num_labels": int(self._tag_data.get("num_labels", len(self._tag_data.get("names", [])))) if self._tag_data else 0,
            "label_format": self._tag_data.get("label_format", "csv") if self._tag_data else "",
        }

    def _prepare_image(
        self,
        image: Image.Image,
        config: Optional[ModelInferenceConfig] = None,
    ) -> np.ndarray:
        """Preprocess a single image for the model."""
        cfg = self._resolve_loaded_config(config)
        return prepare_image(
            image,
            target_size=cfg.input_size,
            is_nchw=getattr(self, "_is_nchw", False),
            config=cfg,
            detected_nchw=getattr(self, "_is_nchw", False),
            target_dtype=getattr(self, "_input_dtype", np.float32),
        )

    def _prepare_image_from_path(
        self,
        file_path: str,
        config: Optional[ModelInferenceConfig] = None,
    ) -> Tuple[str, Optional[np.ndarray]]:
        """Load and prepare an image from file path."""
        try:
            from ...utils.format_registry import format_registry
            ext = Path(file_path).suffix.lower()

            if ext == '.gif':
                image = self._extract_gif_frame(file_path)
            elif format_registry.is_video(file_path):
                image = self._extract_video_frame(file_path)
            else:
                image = Image.open(file_path)

            prepared = self._prepare_image(image, config=config)

            # Close image to free memory
            if hasattr(image, 'close'):
                image.close()

            return (file_path, prepared)
        except Exception:
            return (file_path, None)

    def _prepare_images_parallel(
        self,
        file_paths: List[str],
        max_workers: Optional[int] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
        config: Optional[ModelInferenceConfig] = None,
    ) -> List[Tuple[str, Optional[np.ndarray]]]:
        """Prepare multiple images in parallel."""
        if max_workers is None:
            max_workers = self._num_preprocess_workers
        
        # Submit all tasks
        futures = {
            self._preprocess_executor.submit(self._prepare_image_from_path, fp, config): fp
            for fp in file_paths
        }

        # Collect results in submission order
        path_to_result = {}
        for future in as_completed(futures):
            if is_cancelled and is_cancelled():
                break
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
        return extract_tags_from_scores(
            self._tag_data,
            scores,
            general_threshold,
            character_threshold,
            hide_rating_tags,
            character_tags_first,
        )

    def predict_image(
        self,
        image: Image.Image,
        general_threshold: float = 0.35,
        character_threshold: float = 0.85,
        hide_rating_tags: bool = True,
        character_tags_first: bool = True,
        model_name: str = "wd-eva02-large-tagger-v3",
        config_override: Optional[ModelInferenceConfig] = None,
    ) -> List[Dict[str, Any]]:
        """Predict tags for a single image."""
        self.ensure_loaded(model_name)
        try:
            cfg = self._resolve_loaded_config(config_override)
            processed_image = self._prepare_image(image, config=cfg)
            processed_batch = np.expand_dims(processed_image, axis=0)

            preds = self._run_with_oom_retry(processed_batch, config=cfg)

            scores = preds[0]  # First (and only) batch item

            results = self._extract_tags_from_scores(
                scores, general_threshold, character_threshold,
                hide_rating_tags, character_tags_first
            )
            return results
        finally:
            self._reset_idle_timer()

    predict = predict_image

    def predict_image_test(
        self,
        image: Image.Image,
        model_name: str,
        config_override: ModelInferenceConfig,
        general_threshold: float = 0.35,
        character_threshold: float = 0.85,
        hide_rating_tags: bool = True,
        character_tags_first: bool = True,
    ) -> Dict[str, Any]:
        """Run a diagnostic single-image prediction using transient, unsaved config overrides."""
        self.ensure_loaded(model_name)
        warnings: List[str] = []
        try:
            if self._fixed_batch_one and config_override.batch_size > 1:
                warnings.append(
                    "Model has a static batch dimension of 1; batch_size is capped at 1 during inference."
                )
            if self._outputs_meta and config_override.output_index >= len(self._outputs_meta):
                warnings.append(
                    f"Model defines {len(self._outputs_meta)} output tensor(s); "
                    f"output_index {config_override.output_index} was clamped to {len(self._outputs_meta) - 1}."
                )

            t0 = time.perf_counter()
            processed_image = self._prepare_image(image, config=config_override)
            processed_batch = np.expand_dims(processed_image, axis=0)

            raw_preds = self._execute_raw_session(
                processed_batch,
                output_index=config_override.output_index,
            )
            raw_min = float(np.min(raw_preds)) if raw_preds.size > 0 else 0.0
            raw_max = float(np.max(raw_preds)) if raw_preds.size > 0 else 0.0

            if config_override.output_activation == "none" and (raw_min < -0.01 or raw_max > 1.01):
                warnings.append(
                    f"Raw model outputs ranged from {raw_min:.3f} to {raw_max:.3f} (outside [0, 1]) "
                    "while output_activation is 'none'. Consider using 'sigmoid' or 'auto'."
                )

            probs, resolved_activation = apply_output_postprocessing(
                raw_preds,
                output_activation=config_override.output_activation,
                temperature=config_override.temperature,
            )
            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)

            scores = probs[0]
            tags = self._extract_tags_from_scores(
                scores,
                general_threshold,
                character_threshold,
                hide_rating_tags,
                character_tags_first,
            )
            top_raw_tags = extract_top_raw_tags(self._tag_data, scores, limit=10)
            active_provider = self._active_providers[0] if self._active_providers else "CPUExecutionProvider"

            return {
                "tags": tags,
                "top_raw_tags": top_raw_tags,
                "inference_time_ms": elapsed_ms,
                "provider": active_provider,
                "resolved_activation": resolved_activation,
                "model_info": self.get_loaded_model_info(),
                "warnings": warnings,
            }
        finally:
            self._reset_idle_timer()

    def predict_batch(
        self,
        images: List[np.ndarray],
        general_threshold: float = 0.35,
        character_threshold: float = 0.85,
        hide_rating_tags: bool = True,
        character_tags_first: bool = True,
        model_name: str = "wd-eva02-large-tagger-v3"
    ) -> List[List[Dict[str, Any]]]:
        """Predict tags for a batch of preprocessed images."""
        if not images:
            return []

        self.ensure_loaded(model_name)
        try:
            cfg = self._resolve_loaded_config()
            batch = np.stack(images, axis=0)
            preds = self._run_with_oom_retry(batch, config=cfg)

            results = []
            for scores in preds:
                tags = self._extract_tags_from_scores(
                    scores, general_threshold, character_threshold,
                    hide_rating_tags, character_tags_first
                )
                results.append(tags)
            return results
        finally:
            self._reset_idle_timer()

    def predict_from_file(
        self,
        file_path: str,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """Predict tags from a single file path."""
        model_name = kwargs.get('model_name', 'wd-eva02-large-tagger-v3')
        self.ensure_loaded(model_name)
        try:
            cfg = self._resolve_loaded_config(kwargs.get('config_override'))
            _, prepared = self._prepare_image_from_path(file_path, config=cfg)
            if prepared is None:
                return []

            batch = np.expand_dims(prepared, axis=0)
            preds = self._run_with_oom_retry(batch, config=cfg)

            results = self._extract_tags_from_scores(
                preds[0],
                kwargs.get('general_threshold', 0.35),
                kwargs.get('character_threshold', 0.85),
                kwargs.get('hide_rating_tags', True),
                kwargs.get('character_tags_first', True)
            )
            return results
        finally:
            self._reset_idle_timer()

    def next_batch_size(self, current_size: int, max_batch: int) -> int:
        """Compute next adaptive batch size while respecting fixed-batch-1 and OOM backoff."""
        if getattr(self, "_fixed_batch_one", False) or max_batch <= 1:
            return 1
        if self._oom_encountered:
            return min(current_size + 1, max_batch)
        return min(current_size * 2, max_batch)

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
        """Predict tags for multiple files efficiently using batch processing."""
        if not file_paths:
            return []

        self.ensure_loaded(model_name)
        cfg = self._resolve_loaded_config()

        if batch_size is None:
            max_batch = cfg.batch_size
            if getattr(self, '_fixed_batch_one', False) or max_batch <= 1:
                self._dynamic_batch_size = 1
            else:
                self._dynamic_batch_size = min(self._dynamic_batch_size, max_batch)
            target_size = self._dynamic_batch_size
        else:
            target_size = 1 if getattr(self, '_fixed_batch_one', False) else max(1, int(batch_size))

        total = len(file_paths)
        results = {}
        processed_count = 0

        try:
            i = 0
            while i < total:
                actual_chunk_size = min(target_size, total - i)
                batch_paths = file_paths[i:i + actual_chunk_size]

                chunk_results = self._process_chunk_oom_protected(
                    batch_paths, general_threshold, character_threshold,
                    hide_rating_tags, character_tags_first,
                    config=cfg,
                )
                results.update(chunk_results)

                processed_count += len(batch_paths)

                if progress_callback:
                    progress_callback(processed_count, total)

                i += actual_chunk_size

                if batch_size is None:
                    self._dynamic_batch_size = self.next_batch_size(self._dynamic_batch_size, cfg.batch_size)
                    target_size = self._dynamic_batch_size
        finally:
            self._reset_idle_timer()

        # Return in original order
        return [(fp, results.get(fp, [])) for fp in file_paths]

    def predict_from_files_streaming(
        self,
        file_paths: List[str],
        general_threshold: float = 0.35,
        character_threshold: float = 0.85,
        hide_rating_tags: bool = True,
        character_tags_first: bool = True,
        model_name: str = "wd-eva02-large-tagger-v3",
        batch_size: Optional[int] = None,
        is_cancelled: Optional[Callable[[], bool]] = None
    ) -> Generator[Tuple[str, List[Dict[str, Any]]], None, None]:
        """Stream prediction results as they complete."""
        if not file_paths:
            return

        self.ensure_loaded(model_name)
        cfg = self._resolve_loaded_config()

        if batch_size is None:
            target_size = 1
        else:
            target_size = 1 if getattr(self, '_fixed_batch_one', False) else max(1, int(batch_size))

        i = 0
        total = len(file_paths)
        try:
            while i < total:
                if is_cancelled and is_cancelled():
                    break
                actual_chunk_size = min(target_size, total - i)
                batch_paths = file_paths[i:i + actual_chunk_size]

                chunk_results = self._process_chunk_oom_protected(
                    batch_paths, general_threshold, character_threshold,
                    hide_rating_tags, character_tags_first,
                    is_cancelled=is_cancelled,
                    config=cfg,
                )

                if is_cancelled and is_cancelled():
                    break

                for fp in batch_paths:
                    yield (fp, chunk_results.get(fp, []))

                i += actual_chunk_size

                if batch_size is None:
                    target_size = self.next_batch_size(target_size, cfg.batch_size)
        finally:
            self._reset_idle_timer()

    def _extract_gif_frame(self, file_path: str, frame_index: int = 0) -> Image.Image:
        """Extract a frame from a GIF."""
        return extract_gif_frame(file_path, frame_index=frame_index)

    def _extract_video_frame(self, file_path: str, frame_index: int = 0) -> Image.Image:
        """Extract a frame from a video file using ffmpeg."""
        return extract_video_frame(file_path, frame_index=frame_index)

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @property
    def current_model(self) -> Optional[str]:
        return self._current_model_name

    def get_optimal_batch_size(self, model_name: Optional[str] = None) -> int:
        """Get configured/optimal batch size for the specified or current model."""
        name = model_name or self._current_model_name or "wd-eva02-large-tagger-v3"
        if not self.is_valid_model(name):
            return 4
        if self._current_model_name == name and getattr(self, "_fixed_batch_one", False):
            return 1
        return self.get_effective_config(name).batch_size

    def shutdown(self):
        """Clean up resources on application shutdown."""
        self.unload_model()
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
