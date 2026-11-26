import os
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

from ...utils import image_plugins
from .registry import ModelInferenceConfig

IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

def _composite_to_rgb(image: Image.Image) -> Image.Image:
    if image.mode == "RGB":
        return image
    if image.mode == "RGBA":
        canvas = Image.new("RGBA", image.size, (255, 255, 255, 255))
        canvas.alpha_composite(image)
        return canvas.convert("RGB")
    if image.mode in ("LA", "PA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        canvas = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        canvas.alpha_composite(rgba)
        return canvas.convert("RGB")
    return image.convert("RGB")

def _get_pil_resample(interpolation: str):
    interp = (interpolation or "bicubic").lower()
    if interp == "bilinear":
        return Image.Resampling.BILINEAR
    if interp == "lanczos":
        return Image.Resampling.LANCZOS
    return Image.Resampling.BICUBIC

def prepare_image(
    image: Image.Image,
    target_size: int = 448,
    is_nchw: bool = False,
    config: Optional[ModelInferenceConfig] = None,
    detected_nchw: bool = False,
    target_dtype: Any = np.float32,
) -> np.ndarray:
    """
    Preprocess a single image for an ONNX tagger model.
    Supports both legacy (target_size, is_nchw) arguments and full ModelInferenceConfig.
    """
    if config is None:
        if is_nchw:
            config = ModelInferenceConfig(
                input_size=target_size,
                input_layout="nchw",
                color_space="rgb",
                resize_mode="pad_black",
                interpolation="bilinear",
                normalization="minus_one_to_one",
            )
        else:
            config = ModelInferenceConfig(
                input_size=target_size,
                input_layout="nhwc",
                color_space="bgr",
                resize_mode="pad_white",
                interpolation="bicubic",
                normalization="none_255",
            )

    size = int(config.input_size)
    layout = config.input_layout
    if layout == "auto":
        layout = "nchw" if (detected_nchw or is_nchw) else "nhwc"

    resample = _get_pil_resample(config.interpolation)
    image = _composite_to_rgb(image)
    width, height = image.size

    if config.resize_mode == "pad_black":
        if height != size or width != size:
            scale = min(size / height, size / width)
            new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
            resized = image.resize(new_size, resample)
            canvas = Image.new("RGB", (size, size), (0, 0, 0))
            canvas.paste(resized, ((size - new_size[0]) // 2, (size - new_size[1]) // 2))
            image = canvas
    elif config.resize_mode == "stretch":
        if width != size or height != size:
            image = image.resize((size, size), resample)
    else:
        # pad_white (default WD style: pad to square on white, then resize)
        max_dim = max(width, height)
        if width != height:
            pad_left = (max_dim - width) // 2
            pad_top = (max_dim - height) // 2
            padded_image = Image.new("RGB", (max_dim, max_dim), (255, 255, 255))
            padded_image.paste(image, (pad_left, pad_top))
            image = padded_image
        if image.size[0] != size:
            image = image.resize((size, size), resample)

    array = np.asarray(image, dtype=np.float32)

    norm = config.normalization
    if norm == "zero_to_one":
        array = array / 255.0
    elif norm == "minus_one_to_one":
        array = (array / 255.0 - 0.5) / 0.5
    elif norm == "imagenet":
        array = (array / 255.0 - IMAGENET_MEAN) / IMAGENET_STD
    elif norm == "custom":
        mean_arr = np.array(config.norm_mean, dtype=np.float32)
        std_arr = np.maximum(np.array(config.norm_std, dtype=np.float32), 1e-6)
        array = (array / 255.0 - mean_arr) / std_arr

    if config.color_space == "bgr":
        array = array[:, :, ::-1].copy()

    if layout == "nchw":
        array = np.transpose(array, (2, 0, 1))

    if target_dtype == np.float16:
        return np.ascontiguousarray(array, dtype=np.float16)
    return np.ascontiguousarray(array, dtype=np.float32)

def _stable_sigmoid(logits: np.ndarray) -> np.ndarray:
    positive = logits >= 0
    probs = np.empty_like(logits, dtype=np.float32)
    probs[positive] = 1.0 / (1.0 + np.exp(-logits[positive]))
    negative = ~positive
    exp_neg = np.exp(logits[negative])
    probs[negative] = exp_neg / (1.0 + exp_neg)
    return probs

def apply_output_postprocessing(
    raw_preds: np.ndarray,
    output_activation: str = "none",
    temperature: float = 1.0,
) -> Tuple[np.ndarray, str]:
    """Apply output activation ('sigmoid', 'none', or 'auto') and temperature scaling."""
    preds = np.asarray(raw_preds, dtype=np.float32)
    temp = max(0.05, float(temperature))

    act = (output_activation or "none").lower()
    if act == "auto":
        if preds.size > 0 and (float(np.min(preds)) < -1e-4 or float(np.max(preds)) > 1.0 + 1e-4):
            resolved_act = "sigmoid"
        else:
            resolved_act = "none"
    elif act == "sigmoid":
        resolved_act = "sigmoid"
    else:
        resolved_act = "none"

    if resolved_act == "sigmoid":
        scaled = preds if abs(temp - 1.0) < 1e-6 else (preds / np.float32(temp))
        return _stable_sigmoid(scaled), "sigmoid"

    if abs(temp - 1.0) < 1e-6:
        return preds, "none"

    clipped = np.clip(preds, 1e-7, 1.0 - 1e-7)
    logits = np.log(clipped / (1.0 - clipped)) / np.float32(temp)
    return _stable_sigmoid(logits), "none"

def extract_gif_frame(file_path: str, frame_index: int = 0) -> Image.Image:
    """Extract a frame from a GIF."""
    with Image.open(file_path) as gif:
        gif.seek(frame_index)
        return gif.convert('RGB')

def extract_video_frame(file_path: str, frame_index: int = 0) -> Image.Image:
    """Extract a frame from a video file using ffmpeg."""
    import subprocess
    import tempfile

    import imageio_ffmpeg

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
        tmp_path = tmp.name
    
    try:
        cmd = [
            ffmpeg_exe, '-i', file_path,
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

def extract_tags_from_scores(
    tag_data: dict,
    scores: np.ndarray,
    general_threshold: float,
    character_threshold: float,
    hide_rating_tags: bool,
    character_tags_first: bool
) -> List[Dict[str, Any]]:
    """Extract tags from model output scores using vectorized operations."""
    names = tag_data['names']
    num_scores = len(scores)

    category_specs = [
        ("character", character_threshold, False),
        ("copyright", general_threshold, False),
        ("artist", general_threshold, False),
        ("general", general_threshold, False),
        ("meta", general_threshold, False),
    ]
    if not hide_rating_tags:
        category_specs.append(("rating", 0.5, True))

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for category, threshold, strict_gt in category_specs:
        raw_indices = tag_data.get(category)
        if raw_indices is None or len(raw_indices) == 0:
            continue
        indices = raw_indices[raw_indices < num_scores]
        if len(indices) == 0:
            continue
        cat_scores = scores[indices]
        mask = (cat_scores > threshold) if strict_gt else (cat_scores >= threshold)
        cat_tags = [
            {
                "name": names[idx],
                "category": category,
                "confidence": float(score),
            }
            for idx, score in zip(indices[mask], cat_scores[mask])
            if names[idx]
        ]
        if cat_tags:
            grouped[category] = cat_tags

    if character_tags_first:
        results: List[Dict[str, Any]] = []
        for category, _, _ in category_specs:
            if category in grouped:
                results.extend(sorted(grouped[category], key=lambda x: x["confidence"], reverse=True))
        return results

    results = [tag for cat_tags in grouped.values() for tag in cat_tags]
    results.sort(key=lambda x: x["confidence"], reverse=True)
    return results

def extract_top_raw_tags(
    tag_data: dict,
    scores: np.ndarray,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Return top-N raw scoring tags regardless of thresholds for model diagnostics."""
    names = tag_data.get("names") or []
    n = min(len(names), len(scores))
    if n <= 0 or limit <= 0:
        return []

    cat_lookup: Dict[int, str] = {}
    for cat_key in ("character", "copyright", "artist", "meta", "rating"):
        arr = tag_data.get(cat_key)
        if arr is not None:
            for idx in arr:
                cat_lookup[int(idx)] = cat_key

    sub_scores = scores[:n]
    k = min(limit, n)
    top_indices = np.argpartition(sub_scores, -k)[-k:]
    top_indices = top_indices[np.argsort(sub_scores[top_indices])[::-1]]

    out = []
    for idx in top_indices:
        idx_i = int(idx)
        name = names[idx_i]
        if not name:
            continue
        out.append({
            "name": name,
            "category": cat_lookup.get(idx_i, "general"),
            "confidence": float(sub_scores[idx_i]),
        })
    return out
