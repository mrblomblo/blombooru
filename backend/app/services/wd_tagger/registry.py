from dataclasses import dataclass
import json
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

AVAILABLE_MODELS = {
    "pixai-tagger-v1.0": "noaione/pixai-tagger-v1.0-onnx",
    "wd-eva02-large-tagger-v3": "SmilingWolf/wd-eva02-large-tagger-v3",
    "wd-vit-large-tagger-v3": "SmilingWolf/wd-vit-large-tagger-v3",
    "wd-swinv2-tagger-v3": "SmilingWolf/wd-swinv2-tagger-v3",
    "wd-convnext-tagger-v3": "SmilingWolf/wd-convnext-tagger-v3",
    "wd-vit-tagger-v3": "SmilingWolf/wd-vit-tagger-v3",
}

LEGACY_MODEL_VARIANTS = {
    "pixai-tagger-v1.0": ["A1yCE/pixai-tagger-v1.0-onnx-fp16"],
}

MODEL_REPO_SPECS = {
    "noaione/pixai-tagger-v1.0-onnx": {
        "required_files": ["model.onnx", "model.onnx.data", "tags.json"],
        "model_file": "model.onnx",
        "label_file": "tags.json",
        "download_size_bytes": int(1980.0 * 1024 * 1024),
    },
    "A1yCE/pixai-tagger-v1.0-onnx-fp16": {
        "required_files": ["model.onnx", "tags.json"],
        "model_file": "model.onnx",
        "label_file": "tags.json",
        "download_size_bytes": int(935.4 * 1024 * 1024),
    },
}

# Speed ranking (relative, lower is faster)
MODEL_SPEED_RANKING = {
    "wd-vit-tagger-v3": 1,        # Fastest
    "wd-convnext-tagger-v3": 2,
    "wd-swinv2-tagger-v3": 3,
    "wd-eva02-large-tagger-v3": 4,
    "wd-vit-large-tagger-v3": 5,
    "pixai-tagger-v1.0": 6,       # Slowest
}

# Accuracy ranking (relative, lower is more accurate), based on benchmarks found online
MODEL_ACCURACY_RANKING = {
    "pixai-tagger-v1.0": 1,        # Most accurate
    "wd-eva02-large-tagger-v3": 2,
    "wd-vit-large-tagger-v3": 3,
    "wd-swinv2-tagger-v3": 4,
    "wd-convnext-tagger-v3": 5,
    "wd-vit-tagger-v3": 6,         # Least accurate
}

MODEL_FILENAME = "model.onnx"
LABEL_FILENAME = "selected_tags.csv"

# Measured per-model plateau caps on CPU (Ryzen 7 5700G)
OPTIMAL_BATCH_SIZES = {
    "pixai-tagger-v1.0": 1,
    "wd-convnext-tagger-v3": 1,
    "wd-eva02-large-tagger-v3": 2,
    "wd-vit-large-tagger-v3": 5,
    "wd-vit-tagger-v3": 10,
    "wd-swinv2-tagger-v3": 15,
}

# Total download sizes (model file + tags file) in bytes
MODEL_DOWNLOAD_SIZES_BYTES = {
    "wd-vit-tagger-v3": int(379.3 * 1024 * 1024),
    "wd-convnext-tagger-v3": int(375.3 * 1024 * 1024),
    "wd-swinv2-tagger-v3": int(445.3 * 1024 * 1024),
    "wd-eva02-large-tagger-v3": int(850.3 * 1024 * 1024),
    "wd-vit-large-tagger-v3": int(1200.3 * 1024 * 1024),
    "pixai-tagger-v1.0": int(1980.0 * 1024 * 1024),
}

VALID_INPUT_LAYOUTS = ("auto", "nhwc", "nchw")
VALID_COLOR_SPACES = ("bgr", "rgb")
VALID_RESIZE_MODES = ("pad_white", "pad_black", "stretch")
VALID_INTERPOLATIONS = ("bicubic", "bilinear", "lanczos")
VALID_NORMALIZATIONS = ("none_255", "zero_to_one", "minus_one_to_one", "imagenet", "custom")
VALID_OUTPUT_ACTIVATIONS = ("auto", "sigmoid", "none")

MODEL_CONFIG_BOUNDS = {
    "batch_size": (1, 64),
    "temperature": (0.05, 5.0),
    "input_size": (64, 2048),
    "norm_mean": (-10.0, 10.0),
    "norm_std": (0.001, 10.0),
    "output_index": (0, 15),
    "threshold": (0.0, 1.0),
}

@dataclass(frozen=True)
class ModelInferenceConfig:
    batch_size: int = 1
    temperature: float = 1.0
    input_size: int = 448
    input_layout: str = "nhwc"
    color_space: str = "bgr"
    resize_mode: str = "pad_white"
    interpolation: str = "bicubic"
    normalization: str = "none_255"
    norm_mean: Tuple[float, float, float] = (0.5, 0.5, 0.5)
    norm_std: Tuple[float, float, float] = (0.5, 0.5, 0.5)
    output_activation: str = "none"
    output_index: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "batch_size": self.batch_size,
            "temperature": self.temperature,
            "input_size": self.input_size,
            "input_layout": self.input_layout,
            "color_space": self.color_space,
            "resize_mode": self.resize_mode,
            "interpolation": self.interpolation,
            "normalization": self.normalization,
            "norm_mean": list(self.norm_mean),
            "norm_std": list(self.norm_std),
            "output_activation": self.output_activation,
            "output_index": self.output_index,
        }

BUILTIN_MODEL_CONFIGS: Dict[str, ModelInferenceConfig] = {
    "pixai-tagger-v1.0": ModelInferenceConfig(
        batch_size=OPTIMAL_BATCH_SIZES["pixai-tagger-v1.0"],
        temperature=1.0,
        input_size=1008,
        input_layout="nchw",
        color_space="rgb",
        resize_mode="pad_black",
        interpolation="bilinear",
        normalization="minus_one_to_one",
        norm_mean=(0.5, 0.5, 0.5),
        norm_std=(0.5, 0.5, 0.5),
        output_activation="sigmoid",
        output_index=0,
    ),
    **{
        name: ModelInferenceConfig(
            batch_size=OPTIMAL_BATCH_SIZES.get(name, 4),
            temperature=1.0,
            input_size=448,
            input_layout="nhwc",
            color_space="bgr",
            resize_mode="pad_white",
            interpolation="bicubic",
            normalization="none_255",
            norm_mean=(0.5, 0.5, 0.5),
            norm_std=(0.5, 0.5, 0.5),
            output_activation="none",
            output_index=0,
        )
        for name in AVAILABLE_MODELS
        if name != "pixai-tagger-v1.0"
    },
}

def _clamp_int(val: Any, low: int, high: int, default: int) -> int:
    if val is None or isinstance(val, bool):
        return max(low, min(high, default))
    try:
        parsed = int(round(float(val)))
    except (TypeError, ValueError):
        return max(low, min(high, default))
    return max(low, min(high, parsed))

def _clamp_float(val: Any, low: float, high: float, default: float, decimals: int = 4) -> float:
    if val is None or isinstance(val, bool):
        return round(max(low, min(high, default)), decimals)
    try:
        parsed = float(val)
        if not np.isfinite(parsed):
            return round(max(low, min(high, default)), decimals)
    except (TypeError, ValueError):
        return round(max(low, min(high, default)), decimals)
    return round(max(low, min(high, parsed)), decimals)

def _clamp_vec3(
    val: Any,
    low: float,
    high: float,
    default: Tuple[float, float, float],
    decimals: int = 6,
) -> Tuple[float, float, float]:
    if isinstance(val, (list, tuple)) and len(val) == 3:
        return (
            _clamp_float(val[0], low, high, default[0], decimals),
            _clamp_float(val[1], low, high, default[1], decimals),
            _clamp_float(val[2], low, high, default[2], decimals),
        )
    return (
        _clamp_float(default[0], low, high, 0.5, decimals),
        _clamp_float(default[1], low, high, 0.5, decimals),
        _clamp_float(default[2], low, high, 0.5, decimals),
    )

def _clean_enum(val: Any, allowed: Tuple[str, ...], default: str) -> str:
    if isinstance(val, str):
        lowered = val.strip().lower()
        if lowered in allowed:
            return lowered
    return default if default in allowed else allowed[0]

def clamp_threshold(val: Any, default: float) -> float:
    low, high = MODEL_CONFIG_BOUNDS["threshold"]
    return _clamp_float(val, low, high, default, decimals=4)

def clamp_model_config(
    raw: Optional[Dict[str, Any]],
    base: Optional[ModelInferenceConfig] = None,
) -> ModelInferenceConfig:
    """Validate and clamp a model inference config dictionary against strict min/max bounds."""
    b = base or ModelInferenceConfig()
    data = raw if isinstance(raw, dict) else {}

    return ModelInferenceConfig(
        batch_size=_clamp_int(
            data.get("batch_size"),
            *MODEL_CONFIG_BOUNDS["batch_size"],
            default=b.batch_size,
        ),
        temperature=_clamp_float(
            data.get("temperature"),
            *MODEL_CONFIG_BOUNDS["temperature"],
            default=b.temperature,
            decimals=4,
        ),
        input_size=_clamp_int(
            data.get("input_size"),
            *MODEL_CONFIG_BOUNDS["input_size"],
            default=b.input_size,
        ),
        input_layout=_clean_enum(data.get("input_layout"), VALID_INPUT_LAYOUTS, b.input_layout),
        color_space=_clean_enum(data.get("color_space"), VALID_COLOR_SPACES, b.color_space),
        resize_mode=_clean_enum(data.get("resize_mode"), VALID_RESIZE_MODES, b.resize_mode),
        interpolation=_clean_enum(data.get("interpolation"), VALID_INTERPOLATIONS, b.interpolation),
        normalization=_clean_enum(data.get("normalization"), VALID_NORMALIZATIONS, b.normalization),
        norm_mean=_clamp_vec3(
            data.get("norm_mean"),
            *MODEL_CONFIG_BOUNDS["norm_mean"],
            default=b.norm_mean,
        ),
        norm_std=_clamp_vec3(
            data.get("norm_std"),
            *MODEL_CONFIG_BOUNDS["norm_std"],
            default=b.norm_std,
        ),
        output_activation=_clean_enum(
            data.get("output_activation"),
            VALID_OUTPUT_ACTIVATIONS,
            b.output_activation,
        ),
        output_index=_clamp_int(
            data.get("output_index"),
            *MODEL_CONFIG_BOUNDS["output_index"],
            default=b.output_index,
        ),
    )

def _normalize_category_name(raw_cat: Any) -> str:
    """Map numeric Danbooru category IDs or string category names to canonical Blombooru categories."""
    if raw_cat is None:
        return "general"

    if isinstance(raw_cat, (int, np.integer)) and not isinstance(raw_cat, bool):
        cat_id = int(raw_cat)
        return {
            0: "general",
            1: "artist",
            3: "copyright",
            4: "character",
            5: "meta",
            9: "rating",
        }.get(cat_id, "general")

    s = str(raw_cat).strip().lower()
    if s.isdigit():
        return _normalize_category_name(int(s))

    mapping = {
        "general": "general",
        "gen": "general",
        "character": "character",
        "char": "character",
        "copyright": "copyright",
        "series": "copyright",
        "ip": "copyright",
        "artist": "artist",
        "style": "artist",
        "creator": "artist",
        "meta": "meta",
        "metadata": "meta",
        "year": "meta",
        "rating": "rating",
    }
    return mapping.get(s, "general")

def _finalize_label_dict(
    names: List[str],
    categories: List[str],
    label_format: str,
    is_pixai: bool = False,
) -> dict:
    if not names or not any(n.strip() for n in names):
        raise ValueError("Label file contains no valid tags")

    buckets: Dict[str, List[int]] = {
        "general": [],
        "character": [],
        "copyright": [],
        "artist": [],
        "meta": [],
        "rating": [],
    }
    for idx, (tag_name, cat) in enumerate(zip(names, categories)):
        if not tag_name:
            continue
        buckets[cat if cat in buckets else "general"].append(idx)

    return {
        "names": names,
        **{cat: np.array(indices, dtype=int) for cat, indices in buckets.items()},
        "is_pixai": is_pixai,
        "label_format": label_format,
        "num_labels": len(names),
    }

def inspect_onnx_session(sess: Any) -> Dict[str, Any]:
    """Inspect an onnxruntime.InferenceSession and return normalized input/output metadata."""
    inputs = sess.get_inputs()
    outputs = sess.get_outputs()
    if not inputs:
        raise ValueError("ONNX model defines no input tensors")
    if not outputs:
        raise ValueError("ONNX model defines no output tensors")

    in0 = inputs[0]
    in_shape = list(in0.shape) if in0.shape else []
    in_type = str(in0.type or "tensor(float)")
    input_dtype = "float16" if "float16" in in_type.lower() else "float32"

    if len(in_shape) == 4 and in_shape[1] == 3:
        is_nchw = True
        h_dim = in_shape[2] if isinstance(in_shape[2], int) and in_shape[2] > 0 else None
        w_dim = in_shape[3] if isinstance(in_shape[3], int) and in_shape[3] > 0 else None
        static_spatial_size = h_dim or w_dim
        detected_size = static_spatial_size or 1008
    else:
        is_nchw = False
        h_dim = in_shape[1] if len(in_shape) >= 3 and isinstance(in_shape[1], int) and in_shape[1] > 0 else None
        w_dim = in_shape[2] if len(in_shape) >= 3 and isinstance(in_shape[2], int) and in_shape[2] > 0 else None
        static_spatial_size = h_dim or w_dim
        detected_size = static_spatial_size or 448

    fixed_batch_one = bool(len(in_shape) >= 1 and in_shape[0] == 1)

    outputs_meta = [
        {
            "index": idx,
            "name": out_meta.name,
            "shape": [d if isinstance(d, int) else str(d) for d in (out_meta.shape or [])],
            "type": str(out_meta.type or ""),
        }
        for idx, out_meta in enumerate(outputs)
    ]

    return {
        "input_name": in0.name,
        "input_shape": [d if isinstance(d, int) else str(d) for d in in_shape],
        "raw_input_shape": in_shape,
        "input_dtype": input_dtype,
        "is_nchw": is_nchw,
        "detected_layout": "nchw" if is_nchw else "nhwc",
        "static_spatial_size": static_spatial_size,
        "detected_size": detected_size,
        "fixed_batch_one": fixed_batch_one,
        "outputs": outputs_meta,
    }

def parse_label_data(label_path: str) -> dict:
    """Parse tag labels from CSV, JSON (PixAI v1.0/v0.9, Camie, dict, list), or TXT files."""
    lower_path = label_path.lower()

    if lower_path.endswith(".json"):
        with open(label_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # PixAI v1.0 schema: {"num_classes": ..., "categories": [{"name", "offset", "count", "tags"}]}
        if isinstance(data, dict) and isinstance(data.get("categories"), list):
            max_end = max(
                (int(c["offset"]) + len(c["tags"]) for c in data["categories"] if "offset" in c and "tags" in c),
                default=0,
            )
            num_classes = max(int(data.get("num_classes", 0)), max_end)
            if num_classes <= 0:
                raise ValueError("PixAI label JSON contains no tag classes")
            all_names = [""] * num_classes
            all_cats = ["general"] * num_classes

            for cat in data["categories"]:
                cname = _normalize_category_name(cat.get("name"))
                offset = int(cat["offset"])
                tags = cat["tags"]
                for i, tag in enumerate(tags):
                    all_names[offset + i] = str(tag)
                    all_cats[offset + i] = cname

            return _finalize_label_dict(all_names, all_cats, label_format="pixai_json", is_pixai=True)

        # PixAI v0.9 schema: {"tag_map": {tag: idx}, "tag_split": {"gen_tag_count": ..., "character_tag_count": ...}}
        if isinstance(data, dict) and isinstance(data.get("tag_map"), dict) and isinstance(data.get("tag_split"), dict):
            tag_map = data["tag_map"]
            if not tag_map:
                raise ValueError("tag_map in label JSON is empty")
            num_classes = max(int(v) for v in tag_map.values()) + 1
            all_names = [""] * num_classes
            all_cats = ["general"] * num_classes
            gen_count = int(data["tag_split"].get("gen_tag_count", 0))
            char_count = int(data["tag_split"].get("character_tag_count", 0))

            for tag, idx_val in tag_map.items():
                idx = int(idx_val)
                all_names[idx] = str(tag)
                if gen_count <= idx < gen_count + char_count:
                    all_cats[idx] = "character"
                else:
                    all_cats[idx] = "general"

            return _finalize_label_dict(all_names, all_cats, label_format="pixai_v09_json", is_pixai=True)

        # Camie Tagger metadata schema: dataset_info.tag_mapping.idx_to_tag or top-level idx_to_tag
        if isinstance(data, dict):
            tag_mapping = (
                data.get("dataset_info", {}).get("tag_mapping")
                if isinstance(data.get("dataset_info"), dict)
                else None
            ) or data.get("tag_mapping") or (data if "idx_to_tag" in data else None)

            if isinstance(tag_mapping, dict) and isinstance(tag_mapping.get("idx_to_tag"), dict):
                idx_to_tag = tag_mapping["idx_to_tag"]
                tag_to_cat = tag_mapping.get("tag_to_category") or {}
                if not idx_to_tag:
                    raise ValueError("idx_to_tag in label JSON is empty")
                num_classes = max(int(k) for k in idx_to_tag.keys()) + 1
                all_names = [""] * num_classes
                all_cats = ["general"] * num_classes
                for k, tag in idx_to_tag.items():
                    idx = int(k)
                    t_str = str(tag)
                    all_names[idx] = t_str
                    all_cats[idx] = _normalize_category_name(tag_to_cat.get(t_str, "general"))
                return _finalize_label_dict(all_names, all_cats, label_format="camie_json")

        # Flat JSON dict: either {"tag": idx} or {"0": "tag"} or {"0": {"name": ..., "category": ...}}
        if isinstance(data, dict) and data:
            keys = list(data.keys())
            vals = list(data.values())
            if all(isinstance(v, int) and not isinstance(v, bool) for v in vals):
                num_classes = max(vals) + 1
                all_names = [""] * num_classes
                all_cats = ["general"] * num_classes
                for tag, idx in data.items():
                    if idx < 0:
                        raise ValueError("Tag index in JSON cannot be negative")
                    all_names[idx] = str(tag)
                return _finalize_label_dict(all_names, all_cats, label_format="dict_json")

            if all(str(k).isdigit() for k in keys):
                num_classes = max(int(k) for k in keys) + 1
                all_names = [""] * num_classes
                all_cats = ["general"] * num_classes
                for k, v in data.items():
                    idx = int(k)
                    if isinstance(v, dict):
                        all_names[idx] = str(v.get("name") or v.get("tag") or "")
                        all_cats[idx] = _normalize_category_name(v.get("category"))
                    else:
                        all_names[idx] = str(v)
                return _finalize_label_dict(all_names, all_cats, label_format="dict_json")

        # JSON list: ["1girl", "solo", ...] or [{"name": ..., "category": ...}]
        if isinstance(data, list) and data:
            all_names = []
            all_cats = []
            for item in data:
                if isinstance(item, dict):
                    all_names.append(str(item.get("name") or item.get("tag") or ""))
                    all_cats.append(_normalize_category_name(item.get("category")))
                else:
                    all_names.append(str(item))
                    all_cats.append("general")
            return _finalize_label_dict(all_names, all_cats, label_format="list_json")

        raise ValueError("Unsupported JSON label file structure")

    if lower_path.endswith(".txt"):
        with open(label_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
        return _finalize_label_dict(lines, ["general"] * len(lines), label_format="txt")

    # CSV format (standard WD / Danbooru / e621 tagger CSVs)
    df = pd.read_csv(label_path, keep_default_na=False)
    if df.empty:
        raise ValueError("CSV label file is empty")

    col_map = {str(c).strip().lower(): c for c in df.columns}
    name_col = col_map.get("name") or col_map.get("tag") or col_map.get("tag_name")
    if name_col is None:
        if len(df.columns) == 1:
            name_col = df.columns[0]
        else:
            raise ValueError("CSV label file must contain a 'name' or 'tag' column")

    all_names = [str(v).strip() for v in df[name_col].tolist()]
    cat_col = col_map.get("category")
    if cat_col is not None:
        all_cats = [_normalize_category_name(v) for v in df[cat_col].tolist()]
    else:
        all_cats = ["general"] * len(all_names)

    return _finalize_label_dict(all_names, all_cats, label_format="csv")
