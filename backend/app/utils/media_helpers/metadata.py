import cv2
import json
import math
import mimetypes
from pathlib import Path
from typing import Any, Dict
from PIL import ExifTags, Image
from .. import image_plugins
from ..ai_metadata import decode_exif_user_comment, normalize_ai_metadata, parse_xmp_packet
from ..format_registry import format_registry
from ..logger import logger

def sanitize_metadata_for_json(val: Any) -> Any:
    """Recursively convert PIL types (like IFDRational), tuples, sets, bytes, etc. into JSON-serializable types."""
    if val is None or isinstance(val, (str, bool)):
        return val
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            return None
        return val
    if hasattr(val, "numerator") and hasattr(val, "denominator"):
        try:
            if val.denominator == 0:
                return 0.0
            f = float(val)
            if math.isnan(f) or math.isinf(f):
                return None
            return f
        except Exception:
            return 0.0
    if isinstance(val, dict):
        return {str(k): sanitize_metadata_for_json(v) for k, v in val.items()}
    if isinstance(val, (list, tuple, set)):
        return [sanitize_metadata_for_json(item) for item in val]
    if isinstance(val, bytes):
        try:
            return val.decode("utf-8", errors="replace").replace("\x00", "").strip()
        except Exception:
            return None
    if isinstance(val, Path):
        return str(val)
    if hasattr(val, "value"):
        return sanitize_metadata_for_json(val.value)
    return str(val)

def extract_image_metadata(file_path: Path) -> Dict[str, Any]:
    """Extract metadata from media files (EXIF, PNG chunks, XMP, etc.)"""
    metadata: Dict[str, Any] = {}

    # Verify file is an image using format_registry or mimetypes
    if not format_registry.is_image(file_path):
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if not mime_type or not mime_type.startswith('image/'):
            return metadata

    # Record file-level stats
    try:
        stat = file_path.stat()
        metadata['file_size'] = stat.st_size
        metadata['file_type'] = 'image'
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if mime_type:
            metadata['mime_type'] = mime_type
    except Exception as e:
        logger.debug(f"Error getting file stat for {file_path}: {e}")

    try:
        container_parameters = None
        sub_ifd_user_comment = None
        ifd0_user_comment = None
        image_description = None
        xmp_comment = None
        xp_comment_val = None
        legacy_user_comment = None
        raw_prompt_graph = None
        raw_text_prompt = None

        with Image.open(file_path) as img:
            try:
                metadata['width'], metadata['height'] = img.size
            except Exception:
                pass

            # Get PNG text chunks
            if hasattr(img, 'info') and img.info:
                ignored_binary_keys = {'icc_profile', 'photoshop', 'exif', 'adobe', 'adobe_transform'}

                for key, value in img.info.items():
                    if key in ignored_binary_keys:
                        continue

                    if isinstance(value, str):
                        try:
                            parsed_val = json.loads(value)
                        except (json.JSONDecodeError, ValueError):
                            parsed_val = value
                    elif isinstance(value, bytes):
                        # If XMP chunk, parse XML packet
                        if key.lower() in ('xmp', 'xml:com.adobe.xmp'):
                            try:
                                parsed_xmp = parse_xmp_packet(value)
                                if parsed_xmp:
                                    metadata['xmp'] = parsed_xmp
                            except Exception as e:
                                logger.debug(f"Error parsing XMP chunk in {file_path}: {e}")
                            continue

                        try:
                            decoded = value.decode('utf-8', errors='replace').replace('\x00', '').strip()
                            try:
                                parsed_val = json.loads(decoded)
                            except (json.JSONDecodeError, ValueError):
                                parsed_val = decoded
                        except Exception:
                            continue
                    else:
                        parsed_val = sanitize_metadata_for_json(value)

                    # Quarantine prompt chunk to avoid collisions with the canonical human prompt field
                    if key.lower() == 'prompt':
                        if isinstance(parsed_val, (dict, list)):
                            raw_prompt_graph = parsed_val
                        elif isinstance(parsed_val, str) and parsed_val.strip():
                            raw_text_prompt = parsed_val.strip()
                        continue

                    metadata[key] = parsed_val

                if 'parameters' in metadata and metadata['parameters']:
                    container_parameters = metadata['parameters']

            # Extract potential parameter candidates from parsed XMP
            if 'xmp' in metadata and isinstance(metadata['xmp'], dict):
                xmp_dict = metadata['xmp']
                for xmp_k in ('UserComment', 'parameters', 'prompt', 'Description', 'description'):
                    if xmp_k in xmp_dict and xmp_dict[xmp_k]:
                        xmp_comment = xmp_dict[xmp_k]
                        break

            # Extract EXIF tags
            if hasattr(img, 'getexif'):
                try:
                    exif = img.getexif()
                except Exception as e:
                    logger.debug(f"Error calling getexif on {file_path}: {e}")
                    exif = None

                if exif:
                    # ComfyUI WebP often stores 'workflow:{...}' in Make and 'prompt:{...}' in Model
                    try:
                        for tag_id, key_name in ((271, 'workflow'), (272, 'prompt')):
                            if tag_id in exif:
                                val = exif[tag_id]
                                if isinstance(val, str) and val.startswith(f"{key_name}:"):
                                    raw_json = val[len(key_name) + 1:]
                                    try:
                                        parsed_exif = json.loads(raw_json)
                                    except Exception:
                                        parsed_exif = raw_json

                                    if key_name == 'prompt':
                                        if isinstance(parsed_exif, (dict, list)):
                                            if raw_prompt_graph is None:
                                                raw_prompt_graph = parsed_exif
                                        elif isinstance(parsed_exif, str) and parsed_exif.strip():
                                            if raw_text_prompt is None:
                                                raw_text_prompt = parsed_exif.strip()
                                    else:
                                        metadata[key_name] = parsed_exif
                    except Exception:
                        pass

                    # ImageDescription tag (0x010E / 270)
                    try:
                        if 0x010E in exif:
                            desc_raw = exif[0x010E]
                            desc_str = decode_exif_user_comment(desc_raw) if isinstance(desc_raw, bytes) else str(desc_raw).strip()
                            if desc_str:
                                try:
                                    image_description = json.loads(desc_str)
                                except (json.JSONDecodeError, ValueError):
                                    image_description = desc_str
                                metadata['description'] = image_description
                    except Exception:
                        pass

                    # UserComment tag in IFD0 (0x9286 / 37510)
                    try:
                        if 0x9286 in exif:
                            uc_text = decode_exif_user_comment(exif[0x9286])
                            if uc_text:
                                try:
                                    ifd0_user_comment = json.loads(uc_text)
                                except (json.JSONDecodeError, ValueError):
                                    ifd0_user_comment = uc_text
                                metadata['user_comment'] = uc_text
                    except Exception:
                        pass

                    # XPComment tag (0x9C9C / 40092) - Windows comment field
                    try:
                        if 0x9C9C in exif:
                            raw_xp = exif[0x9C9C]
                            if isinstance(raw_xp, bytes):
                                decoded_xp = raw_xp.decode('utf-16le', errors='replace').replace('\x00', '').strip()
                                if decoded_xp:
                                    try:
                                        xp_comment_val = json.loads(decoded_xp)
                                    except (json.JSONDecodeError, ValueError):
                                        xp_comment_val = decoded_xp
                                    metadata['xp_comment'] = decoded_xp
                    except Exception:
                        pass

                    # XPKeywords tag (0x9C9E / 40094)
                    try:
                        if 0x9C9E in exif:
                            raw_kw = exif[0x9C9E]
                            if isinstance(raw_kw, bytes):
                                decoded_kw = raw_kw.decode('utf-16le', errors='replace').replace('\x00', '').strip()
                                if decoded_kw:
                                    try:
                                        metadata['keywords'] = json.loads(decoded_kw)
                                    except (json.JSONDecodeError, ValueError):
                                        metadata['keywords'] = decoded_kw
                    except Exception:
                        pass

                    # Exif Sub-IFD (0x8769 / ExifTags.IFD.Exif)
                    # This is where UserComment (0x9286) standardly resides!
                    try:
                        exif_sub_ifd = exif.get_ifd(ExifTags.IFD.Exif)
                        if exif_sub_ifd and 0x9286 in exif_sub_ifd:
                            uc_sub = decode_exif_user_comment(exif_sub_ifd[0x9286])
                            if uc_sub:
                                try:
                                    sub_ifd_user_comment = json.loads(uc_sub)
                                except (json.JSONDecodeError, ValueError):
                                    sub_ifd_user_comment = uc_sub
                                metadata['user_comment'] = uc_sub
                    except Exception:
                        pass
            
            # Legacy EXIF method
            if hasattr(img, '_getexif') and callable(img._getexif):
                try:
                    legacy_exif = img._getexif()
                    if legacy_exif and 0x9286 in legacy_exif:
                        legacy_text = decode_exif_user_comment(legacy_exif[0x9286])
                        if legacy_text:
                            try:
                                legacy_user_comment = json.loads(legacy_text)
                            except (json.JSONDecodeError, ValueError):
                                legacy_user_comment = legacy_text
                except Exception:
                    pass

        # Strict priority order for metadata['parameters']:
        # 1. Native container text chunk (parameters from img.info)
        # 2. EXIF Sub-IFD UserComment (0x8769 -> 0x9286)
        # 3. EXIF IFD0 UserComment (0x9286)
        # 4. EXIF IFD0 ImageDescription (0x010E)
        # 5. XMP packet (UserComment, parameters, Description, etc.)
        # 6. EXIF Windows XPComment (0x9C9C)
        # 7. Legacy _getexif fallback
        selected_params = (
            container_parameters
            or sub_ifd_user_comment
            or ifd0_user_comment
            or image_description
            or xmp_comment
            or xp_comment_val
            or legacy_user_comment
        )
        if selected_params is not None:
            metadata['parameters'] = selected_params

        # Prepare dictionary for normalizer with quarantined graph if available
        meta_to_normalize = dict(metadata)
        if raw_prompt_graph is not None and 'prompt' not in meta_to_normalize:
            meta_to_normalize['prompt'] = raw_prompt_graph
        elif raw_text_prompt is not None and 'prompt' not in meta_to_normalize:
            meta_to_normalize['prompt'] = raw_text_prompt

        # Normalize AI metadata using the dedicated ai_metadata normalizer
        normalized = normalize_ai_metadata(meta_to_normalize)
        if normalized:
            # Extended dedup check: avoid duplicating workflow/prompt graph
            if 'workflow' in normalized:
                norm_wf = normalized['workflow']
                if ('workflow' in metadata and (metadata['workflow'] == norm_wf or metadata['workflow'] is norm_wf or 'workflow' in metadata)) or \
                   ('prompt' in metadata and (metadata['prompt'] == norm_wf or metadata['prompt'] is norm_wf)):
                    normalized.pop('workflow', None)

            metadata['ai'] = normalized

            # Set metadata['prompt'] only to the extracted human prompt text string
            if normalized.get('prompt') and isinstance(normalized['prompt'], str):
                metadata['prompt'] = normalized['prompt']
            elif raw_text_prompt and isinstance(raw_text_prompt, str):
                metadata['prompt'] = raw_text_prompt
        elif raw_text_prompt and isinstance(raw_text_prompt, str):
            metadata['prompt'] = raw_text_prompt

        # Ensure metadata['prompt'] is never a dict or list
        if isinstance(metadata.get('prompt'), (dict, list)):
            metadata.pop('prompt', None)

        return sanitize_metadata_for_json(metadata)
        
    except Exception as e:
        logger.error(f"Error reading metadata from {file_path}: {e}", exc_info=True)
        return sanitize_metadata_for_json(metadata)

def extract_video_metadata(file_path: Path) -> Dict[str, Any]:
    """Extract metadata from video files."""
    metadata = {}
    
    try:
        vid = cv2.VideoCapture(str(file_path))
        if vid.isOpened():
            metadata['width'] = int(vid.get(cv2.CAP_PROP_FRAME_WIDTH))
            metadata['height'] = int(vid.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            frame_count = int(vid.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = vid.get(cv2.CAP_PROP_FPS)
            
            metadata['frame_count'] = frame_count
            metadata['fps'] = fps
            
            if fps > 0:
                metadata['duration'] = frame_count / fps
            
            vid.release()
    except Exception as e:
        logger.error(f"Error reading video metadata with cv2 for {file_path}: {e}")

    try:
        stat = file_path.stat()
        metadata['file_size'] = stat.st_size
        metadata['file_type'] = 'video'
        
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if mime_type:
            metadata['mime_type'] = mime_type
            
    except Exception as e:
        logger.error(f"Error getting video metadata for {file_path}: {e}")
    
    return sanitize_metadata_for_json(metadata)

def extract_media_metadata(file_path: Path) -> Dict[str, Any]:
    """Extract metadata from any media file (image or video)."""
    raw_res = None
    if format_registry.is_video(file_path):
        raw_res = extract_video_metadata(file_path)
    elif format_registry.is_image(file_path):
        raw_res = extract_image_metadata(file_path)
    else:
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if mime_type:
            if mime_type.startswith('video/'):
                raw_res = extract_video_metadata(file_path)
            elif mime_type.startswith('image/'):
                raw_res = extract_image_metadata(file_path)
        
        if not raw_res:
            raw_res = extract_image_metadata(file_path) or extract_video_metadata(file_path)

    return sanitize_metadata_for_json(raw_res or {})
