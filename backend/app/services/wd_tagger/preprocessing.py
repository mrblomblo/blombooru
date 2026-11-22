import os
from typing import Any, Dict, List

import numpy as np
from PIL import Image

from ...utils import image_plugins

def prepare_image(image: Image.Image, target_size: int, is_nchw: bool = False) -> np.ndarray:
    """
    Preprocess a single image for the model.
    Optimized version with minimal allocations.
    """
    if is_nchw:
        if image.mode != "RGB":
            image = image.convert("RGBA")
            canvas = Image.new("RGBA", image.size, (255, 255, 255))
            canvas.alpha_composite(image)
            image = canvas.convert("RGB")

        width, height = image.size
        size = target_size
        if height != size or width != size:
            scale = min(size / height, size / width)
            new_size = (int(width * scale), int(height * scale))
            image = image.resize(new_size, Image.Resampling.BILINEAR)
            canvas = Image.new("RGB", (size, size), (0, 0, 0))
            canvas.paste(image, ((size - new_size[0]) // 2, (size - new_size[1]) // 2))
            image = canvas

        array = np.asarray(image, dtype=np.float32) / 255.0
        array = (array - 0.5) / 0.5
        return np.transpose(array, (2, 0, 1))

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
    if image.size[0] != target_size:
        image = image.resize(
            (target_size, target_size), 
            Image.BICUBIC
        )
    
    # Convert to numpy array in BGR format (model expects BGR)
    # Using np.asarray is faster than np.array as it doesn't copy if not needed
    image_array = np.asarray(image, dtype=np.float32)
    
    # RGB to BGR conversion using fancy indexing
    image_array = image_array[:, :, ::-1].copy()
    
    return image_array

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
    results = []
    names = tag_data['names']
    
    # Character tags - vectorized threshold check
    char_indices = tag_data['character']
    if len(char_indices) > 0:
        char_scores = scores[char_indices]
        char_mask = char_scores >= character_threshold
        for idx, score in zip(char_indices[char_mask], char_scores[char_mask]):
            results.append({
                'name': names[idx],
                'category': 'character',
                'confidence': float(score)
            })

    # Copyright tags
    cpy_indices = tag_data.get('copyright', np.array([], dtype=int))
    if len(cpy_indices) > 0:
        cpy_scores = scores[cpy_indices]
        cpy_mask = cpy_scores >= general_threshold
        for idx, score in zip(cpy_indices[cpy_mask], cpy_scores[cpy_mask]):
            results.append({
                'name': names[idx],
                'category': 'copyright',
                'confidence': float(score)
            })

    # Artist tags (e.g. style tags from PixAI)
    art_indices = tag_data.get('artist', np.array([], dtype=int))
    if len(art_indices) > 0:
        art_scores = scores[art_indices]
        art_mask = art_scores >= general_threshold
        for idx, score in zip(art_indices[art_mask], art_scores[art_mask]):
            results.append({
                'name': names[idx],
                'category': 'artist',
                'confidence': float(score)
            })
    
    # General tags
    gen_indices = tag_data['general']
    if len(gen_indices) > 0:
        gen_scores = scores[gen_indices]
        gen_mask = gen_scores >= general_threshold
        for idx, score in zip(gen_indices[gen_mask], gen_scores[gen_mask]):
            results.append({
                'name': names[idx],
                'category': 'general',
                'confidence': float(score)
            })

    # Meta tags
    meta_indices = tag_data.get('meta', np.array([], dtype=int))
    if len(meta_indices) > 0:
        meta_scores = scores[meta_indices]
        meta_mask = meta_scores >= general_threshold
        for idx, score in zip(meta_indices[meta_mask], meta_scores[meta_mask]):
            results.append({
                'name': names[idx],
                'category': 'meta',
                'confidence': float(score)
            })
    
    # Rating tags
    if not hide_rating_tags:
        rating_indices = tag_data['rating']
        if len(rating_indices) > 0:
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
        cpy_tags = sorted(
            [r for r in results if r['category'] == 'copyright'],
            key=lambda x: x['confidence'], 
            reverse=True
        )
        art_tags = sorted(
            [r for r in results if r['category'] == 'artist'],
            key=lambda x: x['confidence'], 
            reverse=True
        )
        general_tags = sorted(
            [r for r in results if r['category'] == 'general'],
            key=lambda x: x['confidence'], 
            reverse=True
        )
        meta_tags = sorted(
            [r for r in results if r['category'] == 'meta'],
            key=lambda x: x['confidence'], 
            reverse=True
        )
        rating_tags = sorted(
            [r for r in results if r['category'] == 'rating'],
            key=lambda x: x['confidence'], 
            reverse=True
        )
        results = char_tags + cpy_tags + art_tags + general_tags + meta_tags + rating_tags
    else:
        results.sort(key=lambda x: x['confidence'], reverse=True)
    
    return results
