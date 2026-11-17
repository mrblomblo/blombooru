import re
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import Image, ImageOps

from ..enums import FileTypeEnum
from . import image_plugins
from .logger import logger

PHASH_BITS = 256
PHASH_HEX_LENGTH = PHASH_BITS // 4
_PRE_SCALE_LIMIT = 512
_DCT_SIZE = 64
_BLOCK = 16
_UINT256_MASK = (1 << PHASH_BITS) - 1
_MIRROR_X_MASK = int("aaaa" * _BLOCK, 16)
_MIN_COEFFICIENT_SPREAD = 10.0
_HEX_RE = re.compile(rf"^[0-9a-fA-F]{{{PHASH_HEX_LENGTH}}}$")

def phash_to_hex(value: int) -> str:
    """Format a 256-bit PDQ perceptual hash as a 64-character lowercase hex string."""
    return f"{int(value) & _UINT256_MASK:0{PHASH_HEX_LENGTH}x}"

def phash_from_hex(value: Optional[str]) -> Optional[int]:
    """Parse a 64-character hex string into an unsigned 256-bit PDQ hash integer."""
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not _HEX_RE.match(stripped):
        return None
    return int(stripped, 16) & _UINT256_MASK

def phash_to_words(value: int) -> np.ndarray:
    """Unpack a 256-bit hash integer into four big-endian uint64 words for vectorized XOR/popcount."""
    raw = (int(value) & _UINT256_MASK).to_bytes(PHASH_BITS // 8, "big")
    return np.frombuffer(raw, dtype=">u8").astype(np.uint64)

def mirror_phash(value: int) -> int:
    """Return the horizontally mirrored 256-bit PDQ hash via odd-column DCT parity."""
    return (int(value) ^ _MIRROR_X_MASK) & _UINT256_MASK

def hamming_distance(a: int, b: int) -> int:
    """Bitwise Hamming distance between two 256-bit PDQ hashes."""
    return ((int(a) ^ int(b)) & _UINT256_MASK).bit_count()

def mirror_hamming_distance(a: int, b: int) -> int:
    """Closest Hamming distance between two 256-bit PDQ hashes, accounting for horizontal mirroring."""
    return min(hamming_distance(a, b), hamming_distance(mirror_phash(a), b))

def similarity_percent(distance: int) -> float:
    """Express a 256-bit Hamming distance as a 0-100 similarity score."""
    return round((1.0 - distance / PHASH_BITS) * 100.0, 1)

def _flatten_alpha(img: Image.Image) -> Image.Image:
    has_alpha = (
        img.mode in ("RGBA", "LA", "PA")
        or (img.mode == "P" and "transparency" in img.info)
        or "transparency" in img.info
    )
    if not has_alpha:
        return img
    rgba = img.convert("RGBA")
    background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    return Image.alpha_composite(background, rgba)

def _trim_uniform_borders(grey: Image.Image) -> Image.Image:
    """Trim uniform letterbox, pillarbox, or solid frame bars from the edges of a greyscale image."""
    w, h = grey.size
    if w < 32 or h < 32:
        return grey
    arr = np.asarray(grey)

    def find_seam(lines: np.ndarray, max_trim: int) -> int:
        if lines.shape[0] < 8 or max_trim < 2:
            return 0
        p1_0, p50_0, p99_0 = np.percentile(lines[0], (1, 50, 99))
        if (p99_0 - p1_0) > 8:
            return 0
        bar_val = p50_0
        seam = None
        for chunk_start in range(0, max_trim, 32):
            chunk = lines[chunk_start:min(max_trim, chunk_start + 32)]
            p1, p50, p99 = np.percentile(chunk, (1, 50, 99), axis=1)
            is_bar = ((p99 - p1) <= 8) & (np.abs(p50 - bar_val) <= 6)
            non_bar = np.nonzero(~is_bar)[0]
            if non_bar.size:
                seam = chunk_start + int(non_bar[0])
                break
        if seam is None or seam < 2:
            return 0
        before = lines[max(0, seam - 2)].astype(np.int16)
        seam_line = lines[seam].astype(np.int16)
        start = seam if float(np.mean(np.abs(seam_line - before) >= 10)) >= 0.60 else seam + 1
        end_probe = min(lines.shape[0], start + 5)
        probe = lines[start:end_probe].astype(np.int16)
        if probe.shape[0] == 0:
            return 0
        # Require a persistent full-span canvas boundary so interior line art or gradients are never cropped.
        if float(np.min(np.mean(np.abs(probe - before[None, :]) >= 10, axis=1))) < 0.60:
            return 0
        return start

    max_y = int(h * 0.35)
    max_x = int(w * 0.35)
    top = find_seam(arr[:max_y + 7, :], max_y)
    bottom = find_seam(arr[::-1, :][:max_y + 7, :], max_y)
    left = find_seam(arr[:, :max_x + 7].T, max_x)
    right = find_seam(arr[:, ::-1][:, :max_x + 7].T, max_x)

    if top == 0 and bottom == 0 and left == 0 and right == 0:
        return grey
    if (w - left - right) < max(32, w // 3) or (h - top - bottom) < max(32, h // 3):
        return grey
    return grey.crop((left, top, w - right, h - bottom))

def compute_phash_from_image(img: Image.Image) -> Optional[int]:
    """Compute the 256-bit PDQ perceptual hash of an already decoded Pillow image."""
    img = _flatten_alpha(img)
    grey = img.convert("L")

    # Normalize large images before border trimming and downsampling.
    max_side = max(grey.size)
    if max_side > _PRE_SCALE_LIMIT:
        scale = _PRE_SCALE_LIMIT / max_side
        grey = grey.resize(
            (max(1, round(grey.width * scale)), max(1, round(grey.height * scale))),
            Image.Resampling.BILINEAR,
            reducing_gap=2.0,
        )

    grey = _trim_uniform_borders(grey)
    grey = grey.resize((_DCT_SIZE, _DCT_SIZE), Image.Resampling.LANCZOS, reducing_gap=3.0)
    pixels = np.asarray(grey, dtype=np.float32)

    dct = cv2.dct(pixels)
    block = dct[1:_BLOCK + 1, 1:_BLOCK + 1]

    if float(block.max() - block.min()) < _MIN_COEFFICIENT_SPREAD:
        return None

    # Even-frequency columns (1-based c = 2, 4, ..., 16) are invariant under horizontal reflection and
    # are thresholded at their median. Odd-frequency columns (c = 1, 3, ..., 15) are antisymmetric and
    # thresholded at 0 so that horizontal mirroring is an exact XOR with _MIRROR_X_MASK.
    bits = np.empty((_BLOCK, _BLOCK), dtype=bool)
    bits[:, 1::2] = block[:, 1::2] > np.median(block[:, 1::2])
    bits[:, 0::2] = block[:, 0::2] > 0.0
    return int.from_bytes(np.packbits(bits).tobytes(), "big")

def _open_image_frame(file_path: Path) -> Image.Image:
    """Open an image and return a fully decoded representative frame (the middle one for animations)."""
    with Image.open(file_path) as img:
        try:
            img.draft("RGB", (_PRE_SCALE_LIMIT, _PRE_SCALE_LIMIT))
        except Exception:
            pass

        n_frames = getattr(img, "n_frames", 1) or 1
        if n_frames > 1:
            try:
                img.seek(n_frames // 2)
            except EOFError:
                img.seek(0)

        frame = ImageOps.exif_transpose(img)
        if frame is img:
            frame = img.copy()
        frame.load()
        return frame

def _read_video_frame(file_path: Path) -> Optional[Image.Image]:
    cap = cv2.VideoCapture(str(file_path))
    try:
        if not cap.isOpened():
            return None
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        ok, frame = False, None
        if frame_count > 2:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_count // 2)
            ok, frame = cap.read()
        if not ok or frame is None:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = cap.read()
        if not ok or frame is None:
            return None
        return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    finally:
        cap.release()

def compute_media_phash(file_path: Path, file_type, fallback_path: Optional[Path] = None) -> Optional[int]:
    """Compute the perceptual hash of an image, animated image, or video file."""
    file_type_value = getattr(file_type, "value", file_type)
    candidates = [p for p in (file_path, fallback_path) if p is not None]

    for candidate in candidates:
        try:
            candidate = Path(candidate)
            if not candidate.exists():
                continue
            if file_type_value == FileTypeEnum.video.value:
                frame = _read_video_frame(candidate)
                if frame is None:
                    continue
                return compute_phash_from_image(frame)
            return compute_phash_from_image(_open_image_frame(candidate))
        except Exception as e:
            logger.debug(f"PDQ hash computation failed for {candidate}: {e}")
            continue
    return None
