from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import threading
from typing import Any, Dict, List, Optional, Tuple
import unicodedata
import uuid

import onnxruntime as rt

from ...config import settings
from ...utils.logger import logger
from .registry import ModelInferenceConfig, clamp_model_config, inspect_onnx_session, parse_label_data

CUSTOM_MODEL_PREFIX = "custom:"

ALLOWED_MODEL_EXTS = {".onnx"}
ALLOWED_LABEL_EXTS = {".csv", ".json", ".txt"}
ALLOWED_EXTRA_EXTS = {".data", ".onnx_data", ".pb", ".bin", ".weights"}
CONFIG_JSON_FILENAMES = {"config.json", "preprocessor_config.json", "model_config.json"}

_LABEL_JSON_MARKER_KEYS = {"categories", "tag_map", "idx_to_tag", "tag_mapping"}
_CONFIG_JSON_MARKER_KEYS = {
    "input_size",
    "test_input_size",
    "pretrained_cfg",
    "mean",
    "std",
    "image_mean",
    "image_std",
    "interpolation",
    "crop_mode",
    "architecture",
    "hf_hub_id",
}
_IMAGENET_MEAN = (0.485, 0.456, 0.406)
_IMAGENET_STD = (0.229, 0.224, 0.225)

def is_custom_model_id(model_id: Optional[str]) -> bool:
    return isinstance(model_id, str) and model_id.startswith(CUSTOM_MODEL_PREFIX)

def sanitize_uploaded_filename(raw_name: str) -> str:
    if not raw_name or not isinstance(raw_name, str):
        raise ValueError("Uploaded file is missing a filename")
    if "\x00" in raw_name:
        raise ValueError("Filename contains null bytes")
    base = Path(raw_name.strip().replace("\\", "/")).name.strip()
    if not base or base in (".", "..") or base.startswith("."):
        raise ValueError(f"Invalid filename: '{raw_name}'")
    if len(base) > 200:
        raise ValueError(f"Filename is too long: '{base[:40]}...'")
    if re.search(r"[\x00-\x1f\x7f]", base):
        raise ValueError(f"Filename contains invalid control characters: '{base}'")
    return base

def classify_uploaded_filename(filename: str) -> Tuple[str, str]:
    """Sanitize filename and classify it as 'model', 'config', 'label', or 'extra'."""
    safe_name = sanitize_uploaded_filename(filename)
    lower = safe_name.lower()

    if lower in CONFIG_JSON_FILENAMES:
        return safe_name, "config"
    ext = Path(lower).suffix
    if ext in ALLOWED_MODEL_EXTS:
        return safe_name, "model"
    if ext in ALLOWED_LABEL_EXTS:
        return safe_name, "label"
    if ext in ALLOWED_EXTRA_EXTS:
        return safe_name, "extra"

    raise ValueError(
        f"Unsupported file type '{safe_name}'. Allowed extensions: "
        ".onnx (model), .csv/.json/.txt (labels or config.json), "
        ".data/.onnx_data/.pb/.bin/.weights (external weights)."
    )

def _is_close_vec3(a: Tuple[float, float, float], b: Tuple[float, float, float], tol: float = 1e-3) -> bool:
    return all(abs(x - y) <= tol for x, y in zip(a, b))

def _is_model_config_json(path: Path) -> bool:
    """Return True if a JSON file is a timm/HF model config rather than a tag label file."""
    if path.suffix.lower() != ".json":
        return False
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    if any(k in data for k in _LABEL_JSON_MARKER_KEYS):
        return False
    if isinstance(data.get("dataset_info"), dict) and "tag_mapping" in data["dataset_info"]:
        return False
    return any(k in data for k in _CONFIG_JSON_MARKER_KEYS)

def parse_model_config_json(config_path: Path) -> Dict[str, Any]:
    """Parse timm / animetimm / HuggingFace config.json or preprocessor_config.json into config overrides."""
    try:
        with config_path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as exc:
        raise ValueError(f"Failed to parse config file '{config_path.name}': {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError(f"Config file '{config_path.name}' must be a JSON object.")

    merged: Dict[str, Any] = {}
    if isinstance(raw.get("pretrained_cfg"), dict):
        merged.update(raw["pretrained_cfg"])
    merged.update(raw)

    overrides: Dict[str, Any] = {}

    # 1. Input shape / spatial size
    size_spec = merged.get("test_input_size") or merged.get("input_size")
    if isinstance(size_spec, list) and len(size_spec) in (3, 4) and all(isinstance(v, int) and v > 0 for v in size_spec):
        dims = size_spec[1:] if len(size_spec) == 4 else size_spec
        if dims[0] == 3:
            overrides["input_layout"] = "nchw"
            overrides["input_size"] = dims[1]
        elif dims[2] == 3:
            overrides["input_layout"] = "nhwc"
            overrides["input_size"] = dims[0]
    elif isinstance(size_spec, int) and size_spec > 0:
        overrides["input_size"] = size_spec
    elif isinstance(merged.get("size"), dict):
        hf_size = merged["size"]
        dim = hf_size.get("height") or hf_size.get("width") or hf_size.get("shortest_edge")
        if isinstance(dim, int) and dim > 0:
            overrides["input_size"] = dim

    # 2. Interpolation
    interp = merged.get("interpolation")
    if isinstance(interp, str):
        interp_map = {
            "bicubic": "bicubic",
            "cubic": "bicubic",
            "bilinear": "bilinear",
            "linear": "bilinear",
            "lanczos": "lanczos",
        }
        mapped_interp = interp_map.get(interp.strip().lower())
        if mapped_interp:
            overrides["interpolation"] = mapped_interp
    elif isinstance(merged.get("resample"), int):
        pil_map = {1: "lanczos", 2: "bilinear", 3: "bicubic"}
        if merged["resample"] in pil_map:
            overrides["interpolation"] = pil_map[merged["resample"]]

    # 3. Crop / resize mode
    crop_mode = merged.get("crop_mode")
    if isinstance(crop_mode, str):
        cm = crop_mode.strip().lower()
        if cm == "squash":
            overrides["resize_mode"] = "stretch"
        elif cm in ("border", "pad", "letterbox"):
            fill = merged.get("fill_color")
            if fill == 0 or fill == [0, 0, 0]:
                overrides["resize_mode"] = "pad_black"
            else:
                overrides["resize_mode"] = "pad_white"

    # 4. Mean / Std normalization & color space
    raw_mean = merged.get("mean") if merged.get("mean") is not None else merged.get("image_mean")
    raw_std = merged.get("std") if merged.get("std") is not None else merged.get("image_std")
    if (
        isinstance(raw_mean, list)
        and len(raw_mean) == 3
        and isinstance(raw_std, list)
        and len(raw_std) == 3
        and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in raw_mean + raw_std)
    ):
        m = (float(raw_mean[0]), float(raw_mean[1]), float(raw_mean[2]))
        s = (float(raw_std[0]), float(raw_std[1]), float(raw_std[2]))
        overrides["color_space"] = "rgb"
        overrides["norm_mean"] = list(m)
        overrides["norm_std"] = list(s)
        if _is_close_vec3(m, _IMAGENET_MEAN) and _is_close_vec3(s, _IMAGENET_STD):
            overrides["normalization"] = "imagenet"
        elif _is_close_vec3(m, (0.5, 0.5, 0.5)) and _is_close_vec3(s, (0.5, 0.5, 0.5)):
            overrides["normalization"] = "minus_one_to_one"
        elif _is_close_vec3(m, (0.0, 0.0, 0.0)) and _is_close_vec3(s, (1.0, 1.0, 1.0)):
            overrides["normalization"] = "zero_to_one"
        else:
            overrides["normalization"] = "custom"
    elif merged.get("do_rescale") is False:
        overrides["normalization"] = "none_255"

    suggested_name = None
    hf_hub_id = merged.get("hf_hub_id")
    if isinstance(hf_hub_id, str) and hf_hub_id.strip():
        suggested_name = hf_hub_id.strip().split("/")[-1]
    elif isinstance(merged.get("architecture"), str) and merged["architecture"].strip():
        suggested_name = merged["architecture"].strip()

    num_classes = merged.get("num_classes")
    return {
        "overrides": overrides,
        "suggested_name": suggested_name,
        "num_classes": int(num_classes) if isinstance(num_classes, int) and num_classes > 0 else None,
        "hf_hub_id": hf_hub_id.strip() if isinstance(hf_hub_id, str) and hf_hub_id.strip() else None,
        "architecture": merged.get("architecture") if isinstance(merged.get("architecture"), str) else None,
    }

def _slugify(name: str) -> str:
    norm = unicodedata.normalize("NFKD", name)
    ascii_str = norm.encode("ascii", "ignore").decode("ascii").lower()
    ascii_str = re.sub(r"[^a-z0-9._-]+", "-", ascii_str)
    ascii_str = re.sub(r"[-_]+", "-", ascii_str).strip("-._")
    return (ascii_str[:64].rstrip("-._")) or "model"

def _unique_slug(base_slug: str, existing_slugs: set) -> str:
    if base_slug not in existing_slugs:
        return base_slug
    for idx in range(2, 10000):
        candidate = f"{base_slug}-{idx}"
        if candidate not in existing_slugs:
            return candidate
    raise RuntimeError("Could not generate a unique custom model identifier")

def inspect_onnx_and_labels(
    model_path: Path,
    label_path: Path,
    config_paths: Optional[List[Path]] = None,
) -> Tuple[Dict[str, Any], ModelInferenceConfig, List[str], Optional[str]]:
    """Validate label file, ONNX graph, and optional config JSONs, returning (model_info, detected_config, warnings, suggested_name)."""
    warnings: List[str] = []

    tag_data = parse_label_data(str(label_path))
    num_labels = int(tag_data["num_labels"])
    label_format = str(tag_data.get("label_format", "csv"))
    is_pixai = bool(tag_data.get("is_pixai", False))

    sess_options = rt.SessionOptions()
    sess_options.graph_optimization_level = rt.GraphOptimizationLevel.ORT_DISABLE_ALL
    sess_options.intra_op_num_threads = 2
    sess_options.inter_op_num_threads = 1

    try:
        sess = rt.InferenceSession(
            str(model_path),
            sess_options=sess_options,
            providers=["CPUExecutionProvider"],
        )
    except Exception as exc:
        raise ValueError(f"Failed to load ONNX model '{model_path.name}': {exc}") from exc

    meta = inspect_onnx_session(sess)
    del sess

    detected_layout = meta["detected_layout"]
    detected_size = meta["detected_size"]
    static_spatial_size = meta["static_spatial_size"]
    outputs_summary = meta["outputs"]

    matching_output_indices = [
        out["index"]
        for out in outputs_summary
        if out["shape"] and isinstance(out["shape"][-1], int) and out["shape"][-1] == num_labels
    ]

    if matching_output_indices:
        detected_output_index = min(matching_output_indices[-1], 15)
    else:
        detected_output_index = 0
        first_shape = outputs_summary[0]["shape"]
        if first_shape and isinstance(first_shape[-1], int) and first_shape[-1] > 0 and first_shape[-1] != num_labels:
            warnings.append(
                f"Output tensor '{outputs_summary[0]['name']}' has {first_shape[-1]} classes, "
                f"while label file '{label_path.name}' defines {num_labels} tags."
            )

    if label_format == "camie_json":
        raw_default = ModelInferenceConfig(
            batch_size=1,
            temperature=1.0,
            input_size=detected_size,
            input_layout=detected_layout,
            color_space="rgb",
            resize_mode="pad_white",
            interpolation="bilinear",
            normalization="imagenet",
            norm_mean=_IMAGENET_MEAN,
            norm_std=_IMAGENET_STD,
            output_activation="sigmoid",
            output_index=detected_output_index,
        )
    elif detected_layout == "nchw":
        raw_default = ModelInferenceConfig(
            batch_size=1,
            temperature=1.0,
            input_size=detected_size,
            input_layout="nchw",
            color_space="rgb",
            resize_mode="pad_black",
            interpolation="bilinear",
            normalization="minus_one_to_one",
            norm_mean=(0.5, 0.5, 0.5),
            norm_std=(0.5, 0.5, 0.5),
            output_activation="sigmoid" if is_pixai else "auto",
            output_index=detected_output_index,
        )
    else:
        raw_default = ModelInferenceConfig(
            batch_size=1,
            temperature=1.0,
            input_size=detected_size,
            input_layout="nhwc",
            color_space="bgr",
            resize_mode="pad_white",
            interpolation="bicubic",
            normalization="none_255",
            norm_mean=(0.5, 0.5, 0.5),
            norm_std=(0.5, 0.5, 0.5),
            output_activation="auto",
            output_index=detected_output_index,
        )

    config_overrides: Dict[str, Any] = {}
    suggested_name: Optional[str] = None
    parsed_meta_extra: Dict[str, Any] = {}

    for cfg_path in (config_paths or []):
        parsed = parse_model_config_json(cfg_path)
        config_overrides.update(parsed["overrides"])
        if parsed["suggested_name"] and not suggested_name:
            suggested_name = parsed["suggested_name"]
        if parsed["hf_hub_id"]:
            parsed_meta_extra["hf_hub_id"] = parsed["hf_hub_id"]
        if parsed["architecture"]:
            parsed_meta_extra["architecture"] = parsed["architecture"]
        if parsed["num_classes"] and parsed["num_classes"] != num_labels:
            warnings.append(
                f"Config '{cfg_path.name}' declares num_classes={parsed['num_classes']}, "
                f"while label file '{label_path.name}' defines {num_labels} tags."
            )

    if (
        static_spatial_size
        and "input_size" in config_overrides
        and config_overrides["input_size"] != static_spatial_size
    ):
        warnings.append(
            f"ONNX input tensor requires static size {static_spatial_size}, "
            f"keeping {static_spatial_size} instead of config input_size {config_overrides['input_size']}."
        )
        config_overrides["input_size"] = static_spatial_size

    detected_config = clamp_model_config(config_overrides, base=raw_default)
    model_info = {
        "input_name": meta["input_name"],
        "input_shape": meta["input_shape"],
        "input_dtype": meta["input_dtype"],
        "fixed_batch_one": meta["fixed_batch_one"],
        "outputs": outputs_summary,
        "num_labels": num_labels,
        "label_format": label_format,
        **parsed_meta_extra,
    }
    return model_info, detected_config, warnings, suggested_name

class CustomModelManager:
    """Manages user-uploaded custom ONNX tagger models stored in settings.CUSTOM_MODELS_DIR."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._meta: Dict[str, Dict[str, Any]] = {}
        self._loaded_json_path: Optional[Path] = None
        self._ensure_loaded()

    @property
    def custom_models_dir(self) -> Path:
        p = settings.CUSTOM_MODELS_DIR
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def custom_models_json(self) -> Path:
        return settings.DATA_DIR / "custom_models.json"

    def _ensure_loaded(self) -> None:
        with self._lock:
            if self._loaded_json_path != self.custom_models_json:
                self.reload_from_disk()

    def reload_from_disk(self) -> None:
        with self._lock:
            target = self.custom_models_json
            self._meta = self._read_disk_meta(target)
            self._loaded_json_path = target

    def _read_disk_meta(self, path: Path) -> Dict[str, Dict[str, Any]]:
        if path.exists():
            try:
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
            except Exception as exc:
                logger.warning(f"Could not read custom_models.json: {exc}")
        return {}

    def _save_meta(self) -> None:
        target = self.custom_models_json
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = target.with_suffix(f".tmp.{uuid.uuid4().hex}")
        try:
            with tmp_path.open("w", encoding="utf-8") as f:
                json.dump(self._meta, f, indent=2)
            os.replace(tmp_path, target)
        except Exception:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            raise

    def create_staging_dir(self) -> Path:
        staging_root = self.custom_models_dir / ".staging"
        staging_root.mkdir(parents=True, exist_ok=True)
        stage = staging_root / uuid.uuid4().hex
        stage.mkdir(parents=True, exist_ok=False)
        return stage

    def cleanup_staging_dir(self, staging_dir: Optional[Path]) -> None:
        if staging_dir and staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)

    def cleanup_orphaned_staging(self) -> None:
        try:
            staging_root = self.custom_models_dir / ".staging"
            if staging_root.exists():
                for child in staging_root.iterdir():
                    shutil.rmtree(child, ignore_errors=True)
        except Exception as exc:
            logger.warning(f"Error cleaning custom model staging directory: {exc}")

    def _safe_model_dir(self, slug: str) -> Path:
        if not slug or "/" in slug or "\\" in slug or ".." in slug or slug.startswith("."):
            raise ValueError("Invalid custom model slug")
        root = self.custom_models_dir.resolve()
        candidate = (self.custom_models_dir / slug).resolve()
        if not candidate.is_relative_to(root) or candidate == root:
            raise ValueError("Custom model path escapes storage root")
        return candidate

    def install_from_staging(
        self,
        staging_dir: Path,
        display_name: str = "",
    ) -> Tuple[Dict[str, Any], List[str]]:
        """Validate staged files, move into custom_models/<slug>, and register in custom_models.json."""
        self._ensure_loaded()

        model_files: List[Path] = []
        label_files: List[Path] = []
        config_files: List[Path] = []
        extra_files: List[Path] = []
        total_bytes = 0

        for item in sorted(staging_dir.iterdir()):
            if not item.is_file() or item.is_symlink():
                raise ValueError("Uploaded bundle contains invalid non-regular files")
            _, role = classify_uploaded_filename(item.name)
            total_bytes += item.stat().st_size
            if role == "model":
                model_files.append(item)
            elif role == "config":
                config_files.append(item)
            elif role == "label":
                if _is_model_config_json(item):
                    config_files.append(item)
                else:
                    label_files.append(item)
            else:
                extra_files.append(item)

        if len(model_files) == 0:
            raise ValueError("Exactly one .onnx model file is required (none provided).")
        if len(model_files) > 1:
            raise ValueError(
                f"Exactly one .onnx model file is allowed per custom model (got {len(model_files)})."
            )
        if len(label_files) == 0:
            raise ValueError("A tag label file (.csv, .json, or .txt) is required.")
        if len(label_files) > 1:
            raise ValueError(
                f"Exactly one tag label file is allowed per custom model (got {len(label_files)})."
            )

        model_file = model_files[0]
        label_file = label_files[0]

        model_info, detected_config, warnings, suggested_name = inspect_onnx_and_labels(
            model_file,
            label_file,
            config_paths=config_files,
        )

        clean_name = (display_name or "").strip()
        if not clean_name:
            if suggested_name:
                clean_name = suggested_name
            else:
                stem = model_file.stem.strip()
                clean_name = stem if stem and stem.lower() != "model" else "custom-onnx-model"
        if len(clean_name) > 80:
            clean_name = clean_name[:80].strip()

        with self._lock:
            existing_slugs = {
                entry.get("slug") or mid[len(CUSTOM_MODEL_PREFIX):]
                for mid, entry in self._meta.items()
            }
            for child in self.custom_models_dir.iterdir():
                if child.is_dir() and not child.name.startswith("."):
                    existing_slugs.add(child.name)

            slug = _unique_slug(_slugify(clean_name), existing_slugs)
            model_id = f"{CUSTOM_MODEL_PREFIX}{slug}"
            dest_dir = self._safe_model_dir(slug)

            shutil.move(str(staging_dir), str(dest_dir))

            cfg_dict = detected_config.to_dict()
            entry = {
                "id": model_id,
                "slug": slug,
                "display_name": clean_name,
                "model_file": model_file.name,
                "label_file": label_file.name,
                "config_files": [p.name for p in config_files],
                "extra_files": [p.name for p in extra_files],
                "size_bytes": total_bytes,
                "model_info": model_info,
                "default_config": cfg_dict,
                "config": dict(cfg_dict),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            self._meta[model_id] = entry
            self._save_meta()
            return dict(entry), warnings

    def get_model(self, model_id: str) -> Optional[Dict[str, Any]]:
        self._ensure_loaded()
        with self._lock:
            entry = self._meta.get(model_id)
            return dict(entry) if entry is not None else None

    def exists(self, model_id: str) -> bool:
        if not is_custom_model_id(model_id):
            return False
        self._ensure_loaded()
        with self._lock:
            return model_id in self._meta

    def is_files_present(self, model_id: str) -> bool:
        try:
            model_path, label_path = self.get_model_paths(model_id)
            return model_path.is_file() and label_path.is_file()
        except Exception:
            return False

    def get_model_paths(self, model_id: str) -> Tuple[Path, Path]:
        self._ensure_loaded()
        with self._lock:
            entry = self._meta.get(model_id)
            if not entry:
                raise KeyError(f"Custom model '{model_id}' not found")
            slug = entry["slug"]
            model_fname = sanitize_uploaded_filename(entry["model_file"])
            label_fname = sanitize_uploaded_filename(entry["label_file"])

        model_dir = self._safe_model_dir(slug)
        model_path = (model_dir / model_fname).resolve()
        label_path = (model_dir / label_fname).resolve()
        if not model_path.is_relative_to(model_dir) or not label_path.is_relative_to(model_dir):
            raise ValueError("Custom model file path escapes model directory")
        return model_path, label_path

    def get_default_config(self, model_id: str) -> ModelInferenceConfig:
        entry = self.get_model(model_id)
        if not entry:
            raise KeyError(f"Custom model '{model_id}' not found")
        return clamp_model_config(entry.get("default_config"))

    def get_effective_config(self, model_id: str) -> ModelInferenceConfig:
        entry = self.get_model(model_id)
        if not entry:
            raise KeyError(f"Custom model '{model_id}' not found")
        default_cfg = clamp_model_config(entry.get("default_config"))
        return clamp_model_config(entry.get("config"), base=default_cfg)

    def update_config(self, model_id: str, raw_config: Dict[str, Any]) -> ModelInferenceConfig:
        self._ensure_loaded()
        with self._lock:
            if model_id not in self._meta:
                raise KeyError(f"Custom model '{model_id}' not found")
            entry = self._meta[model_id]
            default_cfg = clamp_model_config(entry.get("default_config"))
            current_cfg = clamp_model_config(entry.get("config"), base=default_cfg)
            merged_raw = {**current_cfg.to_dict(), **(raw_config if isinstance(raw_config, dict) else {})}
            clamped = clamp_model_config(merged_raw, base=default_cfg)
            entry["config"] = clamped.to_dict()
            entry["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._save_meta()
            return clamped

    def get_size_bytes(self, model_id: str) -> int:
        entry = self.get_model(model_id)
        if not entry:
            return 0
        try:
            model_dir = self._safe_model_dir(entry["slug"])
            if model_dir.exists():
                return sum(f.stat().st_size for f in model_dir.iterdir() if f.is_file())
        except Exception:
            pass
        return int(entry.get("size_bytes", 0))

    def list_models(self) -> List[Dict[str, Any]]:
        self._ensure_loaded()
        with self._lock:
            return [dict(v) for v in self._meta.values()]

    def delete_model(self, model_id: str) -> Dict[str, Any]:
        self._ensure_loaded()
        with self._lock:
            if model_id not in self._meta:
                raise KeyError(f"Custom model '{model_id}' not found")
            entry = self._meta.pop(model_id)
            slug = entry.get("slug")
            if slug:
                try:
                    model_dir = self._safe_model_dir(slug)
                    if model_dir.exists():
                        shutil.rmtree(model_dir, ignore_errors=True)
                except Exception as exc:
                    logger.warning(f"Failed removing custom model directory for {model_id}: {exc}")
            self._save_meta()
            return entry

custom_model_manager = CustomModelManager()
