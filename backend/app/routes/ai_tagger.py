import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from PIL import Image
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..auth import require_admin_mode
from ..config import settings
from ..database import get_db
from ..models import Media, User
from ..services.wd_tagger import (
    DownloadCancelledException,
    WDTagger,
    clamp_model_config,
    clamp_threshold,
    classify_uploaded_filename,
    custom_model_manager,
    get_wd_tagger,
    is_custom_model_id,
)
from ..utils.request_helpers import safe_error_detail

router = APIRouter(prefix="/api/ai-tagger", tags=["ai-tagger"])

# Dedicated thread pool for inference and ONNX validation
_inference_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="wd_inference")

SSE_HEARTBEAT_INTERVAL = 10.0  # seconds
SSE_HEARTBEAT = ": heartbeat\n\n"
DEFAULT_MODEL_NAME = "wd-eva02-large-tagger-v3"
_REPO_ROOT = Path(__file__).resolve().parents[3]

async def run_with_heartbeat(awaitable, interval: float = SSE_HEARTBEAT_INTERVAL):
    """Await `awaitable` while periodically yielding heartbeats."""
    task = asyncio.ensure_future(awaitable)
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=interval)
            if done:
                yield True, task.result()
                return
            yield False, SSE_HEARTBEAT
    finally:
        if not task.done():
            task.cancel()

def shutdown_tagger_resources():
    """Cleanup tagger resources on application shutdown."""
    _inference_executor.shutdown(wait=False)
    try:
        from ..services.wd_tagger import cleanup_orphaned_model_temp_files, get_wd_tagger
        get_wd_tagger().shutdown()
        cleanup_orphaned_model_temp_files()
    except Exception as e:
        pass

def _resolve_no_thumbnail_path() -> Path:
    primary = settings.BASE_DIR / "frontend" / "static" / "images" / "no-thumbnail.png"
    if primary.is_file():
        return primary
    fallback = _REPO_ROOT / "frontend" / "static" / "images" / "no-thumbnail.png"
    if fallback.is_file():
        return fallback
    raise FileNotFoundError("no-thumbnail.png could not be found")

def _resolve_valid_active_model(raw_model_name: Optional[str]) -> str:
    if raw_model_name and WDTagger.is_valid_model(raw_model_name):
        return raw_model_name
    return DEFAULT_MODEL_NAME

def _build_model_descriptor(model_id: str, current_loaded_model: Optional[str]) -> Dict[str, Any]:
    is_custom = is_custom_model_id(model_id)
    if is_custom:
        entry = custom_model_manager.get_model(model_id)
        if not entry:
            raise KeyError(f"Custom model '{model_id}' not found")
        display_name = entry.get("display_name") or model_id
        model_info = entry.get("model_info") or {}
        fixed_batch_one = bool(model_info.get("fixed_batch_one", False))
        repo_id = None
        speed_rank = 99
        accuracy_rank = 99
    else:
        display_name = model_id
        model_info = None
        fixed_batch_one = model_id == "pixai-tagger-v1.0"
        repo_id = WDTagger.get_active_repo_id(model_id)
        speed_rank = WDTagger.MODEL_SPEED_RANKING.get(model_id, 99)
        accuracy_rank = WDTagger.MODEL_ACCURACY_RANKING.get(model_id, 99)

    return {
        "id": model_id,
        "name": model_id,
        "display_name": display_name,
        "is_custom": is_custom,
        "repo_id": repo_id,
        "is_downloaded": WDTagger.is_model_downloaded(model_id),
        "is_loaded": current_loaded_model == model_id,
        "is_downloading": WDTagger.is_downloading(model_id),
        "download_size_mb": WDTagger.get_download_size_mb(model_id),
        "fixed_batch_one": fixed_batch_one,
        "speed_rank": speed_rank,
        "accuracy_rank": accuracy_rank,
        "default_config": WDTagger.get_default_config(model_id).to_dict(),
        "effective_config": WDTagger.get_effective_config(model_id).to_dict(),
        "model_info": model_info,
    }

def _build_all_models_list(current_loaded_model: Optional[str]) -> List[Dict[str, Any]]:
    builtin = [
        _build_model_descriptor(mid, current_loaded_model)
        for mid in WDTagger.AVAILABLE_MODELS.keys()
    ]
    builtin.sort(key=lambda x: x["accuracy_rank"])

    custom = [
        _build_model_descriptor(entry["id"], current_loaded_model)
        for entry in custom_model_manager.list_models()
    ]
    return builtin + custom

def find_media_file(filename: str) -> Optional[Path]:
    """Find a media file in ORIGINAL_DIR or its subdirectories."""
    direct_path = settings.ORIGINAL_DIR / filename
    if direct_path.exists():
        return direct_path
    
    if '/' in filename or '\\' in filename:
        return direct_path if direct_path.exists() else None
    
    for path in settings.ORIGINAL_DIR.rglob(filename):
        if path.is_file():
            return path
    
    return None

def compile_blacklist(blacklisted_tags: List[str]) -> List[re.Pattern]:
    compiled = []
    special_chars = ['.', '^', '$', '+', '(', ')', '[', ']', '{', '}', '|', '\\']
    for pattern in blacklisted_tags:
        escaped_pattern = pattern
        for char in special_chars:
            escaped_pattern = escaped_pattern.replace(char, '\\' + char)
        escaped_pattern = escaped_pattern.replace('*', '.*')
        escaped_pattern = escaped_pattern.replace('?', '.?')
        regex_str = '^' + escaped_pattern + '$'
        compiled.append(re.compile(regex_str, re.IGNORECASE))
    return compiled

def filter_tags(tags: List[dict], blacklisted_tags: List[str], blacklisted_categories: Optional[List[str]] = None) -> List[dict]:
    if not blacklisted_tags and not blacklisted_categories:
        return tags
    compiled_patterns = compile_blacklist(blacklisted_tags) if blacklisted_tags else []
    cat_set = {c.lower().strip() for c in blacklisted_categories} if blacklisted_categories else set()
    filtered = []
    for tag in tags:
        tag_cat = (tag.get("category") or "").lower().strip()
        if cat_set and tag_cat in cat_set:
            continue
        if compiled_patterns and any(pattern.match(tag["name"]) for pattern in compiled_patterns):
            continue
        filtered.append(tag)
    return filtered

def enrich_predicted_tags(tags: List[dict], db: Session) -> List[dict]:
    """Resolve aliases, apply implications, enforce categories, and deduplicate tag predictions."""
    if not tags:
        return []

    from ..utils.tag_utils import enrich_and_resolve_tags, resolve_aliases

    conf_map = {t["name"].strip().lower(): t.get("confidence", 1.0) for t in tags if "name" in t}
    alias_map = resolve_aliases(db, list(conf_map.keys()))

    resolved_conf_map = dict(conf_map)
    for raw_name, conf in conf_map.items():
        if raw_name in alias_map:
            target_name = alias_map[raw_name][0].lower()
            resolved_conf_map[target_name] = max(resolved_conf_map.get(target_name, 0.0), conf)

    enriched_booru_tags = enrich_and_resolve_tags(db, tags, dry_run=True)

    result = []
    for bt in enriched_booru_tags:
        conf = resolved_conf_map.get(bt.name.lower(), 1.0)
        result.append({
            "name": bt.name,
            "category": bt.category,
            "rating": getattr(bt, "rating", "none") or "none",
            "confidence": conf
        })

    return result

def postprocess_predicted_tags(
    tags: List[dict],
    db: Session,
    blacklisted_tags: List[str],
    blacklisted_categories: Optional[List[str]] = None,
) -> List[dict]:
    """Filter blacklisted tags/categories, enrich aliases/implications, and re-filter."""
    filtered = filter_tags(tags, blacklisted_tags, blacklisted_categories)
    enriched = enrich_predicted_tags(filtered, db)
    return filter_tags(enriched, blacklisted_tags, blacklisted_categories)

class PredictTagsRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    general_threshold: float = 0.35
    character_threshold: float = 0.85
    hide_rating_tags: bool = True
    character_tags_first: bool = True
    model_name: str = DEFAULT_MODEL_NAME

class BatchPredictRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    media_ids: List[int]
    general_threshold: float = 0.35
    character_threshold: float = 0.85
    hide_rating_tags: bool = True
    character_tags_first: bool = True
    model_name: str = DEFAULT_MODEL_NAME

class PredictedTag(BaseModel):
    name: str
    category: str
    confidence: float
    rating: str = "none"

class PredictTagsResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    media_id: int
    tags: List[PredictedTag]
    model_used: str

class BatchPredictResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    results: List[PredictTagsResponse]
    failed_ids: List[int]
    model_used: str
    processing_time_ms: float

class ModelStatusResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    model_name: str
    display_name: str = ""
    is_custom: bool = False
    is_downloaded: bool
    is_loaded: bool
    is_downloading: bool = False
    download_size_mb: Optional[float] = None
    optimal_batch_size: Optional[int] = None
    fixed_batch_one: bool = False
    default_config: Optional[Dict[str, Any]] = None
    effective_config: Optional[Dict[str, Any]] = None

@router.get("/status")
async def get_tagger_status():
    """Check if the AI tagger is available and loaded."""
    try:
        tagger = get_wd_tagger()
        return {
            "available": True,
            "loaded": tagger.is_loaded,
            "current_model": tagger.current_model,
            "available_models": WDTagger.get_all_model_ids(),
        }
    except ImportError as e:
        return {
            "available": False,
            "error": str(e),
            "available_models": WDTagger.get_all_model_ids(),
        }

class WDTaggerSettingsRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    general_threshold: Optional[float] = None
    character_threshold: Optional[float] = None
    model_name: Optional[str] = None
    blacklisted_tags: Optional[List[str]] = None
    blacklisted_categories: Optional[List[str]] = None
    inference_config: Optional[Dict[str, Any]] = None

class TestModelRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    model_name: str = DEFAULT_MODEL_NAME
    general_threshold: Optional[float] = 0.35
    character_threshold: Optional[float] = 0.85
    hide_rating_tags: bool = True
    character_tags_first: bool = True
    blacklisted_tags: List[str] = []
    blacklisted_categories: List[str] = []
    inference_config: Optional[Dict[str, Any]] = None

@router.get("/settings")
async def get_settings(
    current_user: User = Depends(require_admin_mode)
):
    """Get AI tagger settings and full built-in + custom model descriptors."""
    current_settings = settings.WD_TAGGER_SETTINGS.copy()
    current_settings["model_name"] = _resolve_valid_active_model(current_settings.get("model_name"))

    tagger = get_wd_tagger()
    current_loaded = tagger.current_model if tagger.is_loaded else None
    models_list = _build_all_models_list(current_loaded)

    return {
        **current_settings,
        "available_models": [m["id"] for m in models_list],
        "models": models_list,
    }

@router.put("/settings")
@router.post("/settings")
async def update_settings(
    req: WDTaggerSettingsRequest,
    current_user: User = Depends(require_admin_mode)
):
    """Update AI tagger settings in settings.json and custom_models.json."""
    current_settings = settings.WD_TAGGER_SETTINGS.copy()
    current_settings["model_name"] = _resolve_valid_active_model(current_settings.get("model_name"))
    
    if req.general_threshold is not None:
        current_settings["general_threshold"] = clamp_threshold(
            req.general_threshold,
            current_settings.get("general_threshold", 0.35),
        )
        
    if req.character_threshold is not None:
        current_settings["character_threshold"] = clamp_threshold(
            req.character_threshold,
            current_settings.get("character_threshold", 0.85),
        )
        
    if req.model_name is not None:
        if not WDTagger.is_valid_model(req.model_name):
            raise HTTPException(
                status_code=400,
                detail=f"Unknown model: {req.model_name}. Valid models: {WDTagger.get_all_model_ids()}"
            )
        current_settings["model_name"] = req.model_name

    if req.blacklisted_tags is not None:
        current_settings["blacklisted_tags"] = req.blacklisted_tags

    if req.blacklisted_categories is not None:
        current_settings["blacklisted_categories"] = req.blacklisted_categories

    target_model = current_settings["model_name"]
    if req.inference_config is not None and WDTagger.is_valid_model(target_model):
        if is_custom_model_id(target_model):
            custom_model_manager.update_config(target_model, req.inference_config)
        else:
            default_cfg = WDTagger.get_default_config(target_model)
            existing_cfg = WDTagger.get_effective_config(target_model)
            merged_raw = {**existing_cfg.to_dict(), **req.inference_config}
            clamped_cfg = clamp_model_config(merged_raw, base=default_cfg)
            model_settings = dict(current_settings.get("model_settings") or {})
            if clamped_cfg.to_dict() == default_cfg.to_dict():
                model_settings.pop(target_model, None)
            else:
                model_settings[target_model] = clamped_cfg.to_dict()
            current_settings["model_settings"] = model_settings
        
    settings.save_settings({"wd_tagger": current_settings})

    tagger = get_wd_tagger()
    current_loaded = tagger.current_model if tagger.is_loaded else None
    models_list = _build_all_models_list(current_loaded)
    
    return {
        "success": True,
        **current_settings,
        "available_models": [m["id"] for m in models_list],
        "models": models_list,
    }

@router.get("/models")
async def get_models(
    current_user: User = Depends(require_admin_mode)
):
    """Get list of available built-in and custom models and their status."""
    try:
        tagger = get_wd_tagger()
        current_model = tagger.current_model if tagger.is_loaded else None
        return _build_all_models_list(current_model)
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=f"AI Tagger dependencies not installed: {str(e)}"
        )

@router.get("/model-status/{model_name}", response_model=ModelStatusResponse)
async def get_model_status(
    model_name: str,
    current_user: User = Depends(require_admin_mode)
):
    """Check if a specific built-in or custom model is downloaded, loaded, or downloading."""
    if not WDTagger.is_valid_model(model_name):
        raise HTTPException(status_code=400, detail=f"Unknown model: {model_name}")
    
    try:
        tagger = get_wd_tagger()
        current_loaded = tagger.current_model if tagger.is_loaded else None
        desc = _build_model_descriptor(model_name, current_loaded)
        
        return ModelStatusResponse(
            model_name=model_name,
            display_name=desc["display_name"],
            is_custom=desc["is_custom"],
            is_downloaded=desc["is_downloaded"],
            is_loaded=desc["is_loaded"],
            is_downloading=desc["is_downloading"],
            download_size_mb=desc["download_size_mb"],
            optimal_batch_size=tagger.get_optimal_batch_size(model_name),
            fixed_batch_one=desc["fixed_batch_one"],
            default_config=desc["default_config"],
            effective_config=desc["effective_config"],
        )
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=f"AI Tagger dependencies not installed: {str(e)}"
        )

@router.post("/custom-models", status_code=201)
async def upload_custom_model(
    files: List[UploadFile] = File(...),
    name: str = Form(""),
    current_user: User = Depends(require_admin_mode),
):
    """Upload and validate a custom ONNX tagger model, label file, and optional external weights."""
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    staging_dir: Optional[Path] = None
    try:
        staging_dir = custom_model_manager.create_staging_dir()
        seen_names = set()

        for upload in files:
            safe_name, _ = classify_uploaded_filename(upload.filename or "")
            lower_key = safe_name.lower()
            if lower_key in seen_names:
                raise ValueError(f"Duplicate filename in upload: '{safe_name}'")
            seen_names.add(lower_key)

            dest_file = staging_dir / safe_name
            written = 0
            with dest_file.open("wb") as out_f:
                while chunk := await upload.read(1024 * 1024):
                    out_f.write(chunk)
                    written += len(chunk)

            if written == 0:
                raise ValueError(f"Uploaded file '{safe_name}' is empty.")

        loop = asyncio.get_event_loop()
        entry, warnings = await loop.run_in_executor(
            _inference_executor,
            custom_model_manager.install_from_staging,
            staging_dir,
            name,
        )

        tagger = get_wd_tagger()
        current_loaded = tagger.current_model if tagger.is_loaded else None
        descriptor = _build_model_descriptor(entry["id"], current_loaded)

        return {
            "success": True,
            "model": descriptor,
            "warnings": warnings,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=safe_error_detail("Failed to install custom model", e),
        )
    finally:
        custom_model_manager.cleanup_staging_dir(staging_dir)

@router.post("/test")
async def test_model(
    req: TestModelRequest,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db),
):
    """Test a model against no-thumbnail.png using live, unsaved, clamped settings."""
    if not WDTagger.is_valid_model(req.model_name):
        raise HTTPException(status_code=400, detail=f"Unknown model: {req.model_name}")

    if not WDTagger.is_model_downloaded(req.model_name):
        raise HTTPException(
            status_code=400,
            detail=f"Model '{WDTagger.get_display_name(req.model_name)}' is not downloaded yet.",
        )

    gen_thresh = clamp_threshold(req.general_threshold, 0.35)
    char_thresh = clamp_threshold(req.character_threshold, 0.85)
    base_cfg = WDTagger.get_effective_config(req.model_name)
    clamped_cfg = clamp_model_config(req.inference_config, base=base_cfg)

    try:
        no_thumb_path = _resolve_no_thumbnail_path()
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))

    try:
        loop = asyncio.get_event_loop()

        def do_test():
            tagger = get_wd_tagger()
            with Image.open(no_thumb_path) as img:
                return tagger.predict_image_test(
                    image=img.copy(),
                    model_name=req.model_name,
                    config_override=clamped_cfg,
                    general_threshold=gen_thresh,
                    character_threshold=char_thresh,
                    hide_rating_tags=req.hide_rating_tags,
                    character_tags_first=req.character_tags_first,
                )

        test_out = await loop.run_in_executor(_inference_executor, do_test)
        final_tags = postprocess_predicted_tags(
            test_out["tags"], db, req.blacklisted_tags, req.blacklisted_categories
        )

        return {
            "success": True,
            "model_used": req.model_name,
            "display_name": WDTagger.get_display_name(req.model_name),
            "is_custom": is_custom_model_id(req.model_name),
            "inference_time_ms": test_out["inference_time_ms"],
            "provider": test_out["provider"],
            "resolved_activation": test_out["resolved_activation"],
            "model_info": test_out["model_info"],
            "effective_settings": {
                "general_threshold": gen_thresh,
                "character_threshold": char_thresh,
                "hide_rating_tags": req.hide_rating_tags,
                "character_tags_first": req.character_tags_first,
                "blacklisted_tags": req.blacklisted_tags,
                "blacklisted_categories": req.blacklisted_categories,
                "inference_config": clamped_cfg.to_dict(),
            },
            "raw_matched_count": len(test_out["tags"]),
            "tags": [PredictedTag(**tag) for tag in final_tags],
            "top_raw_tags": test_out["top_raw_tags"],
            "warnings": test_out["warnings"],
        }
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=f"AI Tagger dependencies not installed: {str(e)}",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=safe_error_detail("Model test failed", e),
        )

@router.delete("/model/{model_name}")
async def delete_model(
    model_name: str,
    current_user: User = Depends(require_admin_mode)
):
    """Delete a downloaded built-in model from cache or uninstall a custom model and its files."""
    if not WDTagger.is_valid_model(model_name):
        raise HTTPException(status_code=400, detail=f"Unknown model: {model_name}")

    if is_custom_model_id(model_name):
        try:
            tagger = get_wd_tagger()
            tagger.unload_model(model_name)
            custom_model_manager.delete_model(model_name)

            current_settings = settings.WD_TAGGER_SETTINGS.copy()
            settings_changed = False
            model_settings = dict(current_settings.get("model_settings") or {})
            if model_name in model_settings:
                model_settings.pop(model_name, None)
                current_settings["model_settings"] = model_settings
                settings_changed = True
            if current_settings.get("model_name") == model_name:
                current_settings["model_name"] = DEFAULT_MODEL_NAME
                settings_changed = True
            if settings_changed:
                settings.save_settings({"wd_tagger": current_settings})

            return {
                "success": True,
                "model_name": model_name,
                "is_custom": True,
                "active_model": _resolve_valid_active_model(current_settings.get("model_name")),
            }
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Custom model '{model_name}' not found.")
        except Exception as e:
            raise HTTPException(status_code=500, detail=safe_error_detail("AI tagger error", e))

    if WDTagger.is_downloading(model_name):
        raise HTTPException(status_code=409, detail="Cannot delete a model that is currently downloading.")

    try:
        import huggingface_hub
        import shutil

        repos_to_delete = [WDTagger.AVAILABLE_MODELS[model_name]] + WDTagger.LEGACY_MODEL_VARIANTS.get(model_name, [])
        cache_info = huggingface_hub.scan_cache_dir(cache_dir=settings.MODELS_DIR)

        deleted = False
        for repo_id in repos_to_delete:
            for repo in cache_info.repos:
                if repo.repo_id == repo_id:
                    revisions = [r.commit_hash for r in repo.revisions]
                    if revisions:
                        delete_strategy = cache_info.delete_revisions(*revisions)
                        delete_strategy.execute()
                    if hasattr(repo, "repo_path") and Path(repo.repo_path).exists():
                        shutil.rmtree(repo.repo_path, ignore_errors=True)
                    deleted = True
                    break

            repo_folder_name = "models--" + repo_id.replace("/", "--")
            repo_dir = settings.MODELS_DIR / repo_folder_name
            if repo_dir.exists():
                shutil.rmtree(repo_dir, ignore_errors=True)
                deleted = True

        if not deleted:
            raise HTTPException(status_code=404, detail=f"Model '{model_name}' is not downloaded.")

        # Unload from memory if it was the active model without killing worker pools
        tagger = get_wd_tagger()
        tagger.unload_model(model_name)

        return {
            "success": True,
            "model_name": model_name,
            "is_custom": False,
            "active_model": _resolve_valid_active_model(settings.WD_TAGGER_SETTINGS.get("model_name")),
        }

    except HTTPException:
        raise
    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"AI Tagger dependencies not installed: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=safe_error_detail("AI tagger error", e))

@router.post("/download/{model_name}")
async def download_model(
    model_name: str,
    request: Request,
    current_user: User = Depends(require_admin_mode)
):
    """Download a specific built-in model with real-time streaming progress."""
    if is_custom_model_id(model_name):
        raise HTTPException(status_code=400, detail="Custom models are stored locally and cannot be downloaded.")
    if model_name not in WDTagger.AVAILABLE_MODELS:
        raise HTTPException(status_code=400, detail=f"Unknown model: {model_name}")
    
    async def generate():
        disconnect_event = asyncio.Event()

        async def watch_disconnect():
            try:
                while not disconnect_event.is_set():
                    msg = await request.receive()
                    if msg.get("type") == "http.disconnect":
                        disconnect_event.set()
                        break
            except Exception:
                disconnect_event.set()

        disconnect_task = asyncio.create_task(watch_disconnect())
        queue = asyncio.Queue()
        loop = asyncio.get_event_loop()

        def listener(data: dict):
            loop.call_soon_threadsafe(queue.put_nowait, data)

        task, is_new = WDTagger.register_download(model_name)
        task.add_listener(listener)

        if is_new:
            def run_download():
                tagger = None
                try:
                    tagger = get_wd_tagger()
                    tagger.ensure_loaded(
                        model_name,
                        is_cancelled=task.is_cancelled,
                        progress_callback=task.notify
                    )
                    batch_size = tagger.get_optimal_batch_size(model_name)
                    task.notify({
                        "type": "complete",
                        "model": model_name,
                        "optimal_batch_size": batch_size,
                        "message": f"Model {model_name} downloaded and loaded successfully"
                    })
                except DownloadCancelledException:
                    task.cancelled = True
                    task.notify({"type": "cancelled"})
                except Exception as e:
                    task.notify({"type": "error", "error": str(e)})
                finally:
                    WDTagger.unregister_download(model_name)
                    if tagger is not None:
                        tagger._reset_idle_timer()

            loop.run_in_executor(_inference_executor, run_download)

        try:
            # Flush headers immediately
            yield SSE_HEARTBEAT
            last_sent = time.monotonic()

            while True:
                if disconnect_event.is_set():
                    break
                
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=0.2)
                except asyncio.TimeoutError:
                    if not WDTagger.is_downloading(model_name) and queue.empty():
                        break
                    if time.monotonic() - last_sent >= SSE_HEARTBEAT_INTERVAL:
                        yield SSE_HEARTBEAT
                        last_sent = time.monotonic()
                    continue

                yield f"data: {json.dumps(item)}\n\n"
                last_sent = time.monotonic()
                
                if item.get("type") in ("complete", "error", "cancelled"):
                    break

        except (asyncio.CancelledError, GeneratorExit):
            disconnect_event.set()
        finally:
            disconnect_event.set()
            task.remove_listener(listener)
            if disconnect_task and not disconnect_task.done():
                disconnect_task.cancel()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )

@router.post("/cancel-download")
async def cancel_active_downloads(current_user: User = Depends(require_admin_mode)):
    """Cancel all active model downloads."""
    WDTagger.cancel_all_downloads()
    return {"success": True}

@router.post("/download/{model_name}/cancel")
async def cancel_model_download(
    model_name: str,
    current_user: User = Depends(require_admin_mode)
):
    """Cancel an active model download."""
    WDTagger.cancel_download(model_name)
    return {"success": True}

@router.post("/predict/{media_id}", response_model=PredictTagsResponse)
async def predict_tags(
    media_id: int,
    request: PredictTagsRequest = PredictTagsRequest(),
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Predict tags for a single media item."""
    if not WDTagger.is_valid_model(request.model_name):
        raise HTTPException(status_code=400, detail=f"Unknown model: {request.model_name}")

    media = db.query(Media).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    
    file_path = find_media_file(media.filename)
    
    if not file_path:
        raise HTTPException(
            status_code=404, 
            detail=f"Media file not found: {media.filename}"
        )
    
    try:
        loop = asyncio.get_event_loop()
        
        def do_predict():
            tagger = get_wd_tagger()
            tagger.ensure_loaded(request.model_name)
            return tagger.predict_from_file(
                str(file_path),
                general_threshold=request.general_threshold,
                character_threshold=request.character_threshold,
                hide_rating_tags=request.hide_rating_tags,
                character_tags_first=request.character_tags_first,
                model_name=request.model_name
            )
        
        predictions = await loop.run_in_executor(_inference_executor, do_predict)
        
        blacklisted_tags = settings.WD_TAGGER_SETTINGS.get("blacklisted_tags", [])
        blacklisted_categories = settings.WD_TAGGER_SETTINGS.get("blacklisted_categories", [])
        final_predictions = postprocess_predicted_tags(
            predictions, db, blacklisted_tags, blacklisted_categories
        )
        
        return PredictTagsResponse(
            media_id=media_id,
            tags=[PredictedTag(**tag) for tag in final_predictions],
            model_used=request.model_name
        )
    
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=f"AI Tagger dependencies not installed: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=safe_error_detail("Error predicting tags", e)
        )

@router.post("/predict-batch", response_model=BatchPredictResponse)
async def predict_tags_batch(
    request: BatchPredictRequest,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """
    Predict tags for multiple media items using efficient batch processing.
    """
    if not WDTagger.is_valid_model(request.model_name):
        raise HTTPException(status_code=400, detail=f"Unknown model: {request.model_name}")

    start_time = time.time()
    
    if not request.media_ids:
        return BatchPredictResponse(
            results=[],
            failed_ids=[],
            model_used=request.model_name,
            processing_time_ms=0
        )
    
    max_batch = 200
    if len(request.media_ids) > max_batch:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum batch size is {max_batch}. Got {len(request.media_ids)}."
        )
    
    # Fetch all media records at once
    media_records = db.query(Media).filter(Media.id.in_(request.media_ids)).all()
    media_map = {m.id: m for m in media_records}
    
    # Build file path list
    file_info = []
    not_found = []
    
    for media_id in request.media_ids:
        if media_id not in media_map:
            not_found.append(media_id)
            continue
        
        media = media_map[media_id]
        file_path = find_media_file(media.filename)
        
        if not file_path:
            not_found.append(media_id)
            continue
        
        file_info.append((media_id, str(file_path)))
    
    if not file_info:
        return BatchPredictResponse(
            results=[],
            failed_ids=not_found,
            model_used=request.model_name,
            processing_time_ms=(time.time() - start_time) * 1000
        )
    
    try:
        loop = asyncio.get_event_loop()
        
        def do_batch_predict():
            tagger = get_wd_tagger()
            tagger.ensure_loaded(request.model_name)
            
            file_paths = [fp for _, fp in file_info]
            
            return tagger.predict_from_files_batch(
                file_paths,
                general_threshold=request.general_threshold,
                character_threshold=request.character_threshold,
                hide_rating_tags=request.hide_rating_tags,
                character_tags_first=request.character_tags_first,
                model_name=request.model_name
            )
        
        predictions = await loop.run_in_executor(_inference_executor, do_batch_predict)
        
        # Build results
        results = []
        path_to_media_id = {fp: mid for mid, fp in file_info}
        blacklisted_tags = settings.WD_TAGGER_SETTINGS.get("blacklisted_tags", [])
        blacklisted_categories = settings.WD_TAGGER_SETTINGS.get("blacklisted_categories", [])
        
        for file_path, tags in predictions:
            media_id = path_to_media_id.get(file_path)
            if media_id is not None:
                final_tags = postprocess_predicted_tags(
                    tags, db, blacklisted_tags, blacklisted_categories
                )
                results.append(PredictTagsResponse(
                    media_id=media_id,
                    tags=[PredictedTag(**tag) for tag in final_tags],
                    model_used=request.model_name
                ))
        
        processing_time = (time.time() - start_time) * 1000
        
        return BatchPredictResponse(
            results=results,
            failed_ids=not_found,
            model_used=request.model_name,
            processing_time_ms=processing_time
        )
    
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=f"AI Tagger dependencies not installed: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=safe_error_detail("Error predicting tags", e)
        )

@router.post("/predict-stream")
async def predict_tags_stream(
    request: Request,
    batch_request: BatchPredictRequest,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Stream prediction results using Server-Sent Events."""
    if not WDTagger.is_valid_model(batch_request.model_name):
        raise HTTPException(status_code=400, detail=f"Unknown model: {batch_request.model_name}")

    if not batch_request.media_ids:
        async def empty_stream():
            yield f"data: {json.dumps({'complete': True, 'total': 0})}\n\n"
        return StreamingResponse(empty_stream(), media_type="text/event-stream")
    
    # Fetch media records
    media_records = db.query(Media).filter(Media.id.in_(batch_request.media_ids)).all()
    media_map = {m.id: m for m in media_records}
    
    # Build file info
    file_info = []
    path_to_id = {}
    failed_ids = []
    
    for media_id in batch_request.media_ids:
        if media_id not in media_map:
            failed_ids.append(media_id)
            continue
        
        media = media_map[media_id]
        file_path = find_media_file(media.filename)
        
        if file_path:
            path_str = str(file_path)
            file_info.append((media_id, path_str))
            path_to_id[path_str] = media_id
        else:
            failed_ids.append(media_id)
    
    async def generate():
        # Flush headers immediately
        yield SSE_HEARTBEAT

        # Send failed items first
        for media_id in failed_ids:
            event = {
                "type": "error",
                "media_id": media_id,
                "error": "File not found"
            }
            yield f"data: {json.dumps(event)}\n\n"
            await asyncio.sleep(0)
        
        if not file_info:
            yield f"data: {json.dumps({'type': 'complete', 'total': 0})}\n\n"
            return
        
        disconnect_event = asyncio.Event()

        async def watch_disconnect():
            try:
                while not disconnect_event.is_set():
                    msg = await request.receive()
                    if msg.get("type") == "http.disconnect":
                        disconnect_event.set()
                        break
            except Exception:
                disconnect_event.set()

        disconnect_task = asyncio.create_task(watch_disconnect())

        tagger = None
        try:
            tagger = get_wd_tagger()
            loop = asyncio.get_event_loop()
            
            def load_model():
                tagger.ensure_loaded(batch_request.model_name, is_cancelled=lambda: disconnect_event.is_set())
            
            async for finished, value in run_with_heartbeat(
                loop.run_in_executor(_inference_executor, load_model)
            ):
                if not finished:
                    yield value
            
            file_paths = [fp for _, fp in file_info]
            total = len(file_paths)
            processed = 0
            blacklisted_tags = settings.WD_TAGGER_SETTINGS.get("blacklisted_tags", [])
            blacklisted_categories = settings.WD_TAGGER_SETTINGS.get("blacklisted_categories", [])
            
            max_stream_batch = tagger.get_optimal_batch_size(batch_request.model_name)
            target_size = 1
            i = 0
            
            while i < total:
                if disconnect_event.is_set() or await request.is_disconnected():
                    disconnect_event.set()
                    return
                
                actual_chunk_size = min(target_size, total - i)
                batch_paths = file_paths[i:i + actual_chunk_size]
                
                def do_chunk():
                    return tagger._process_chunk_oom_protected(
                        batch_paths,
                        batch_request.general_threshold,
                        batch_request.character_threshold,
                        batch_request.hide_rating_tags,
                        batch_request.character_tags_first,
                        is_cancelled=lambda: disconnect_event.is_set()
                    )
                
                chunk_results = None
                async for finished, value in run_with_heartbeat(
                    loop.run_in_executor(_inference_executor, do_chunk)
                ):
                    if finished:
                        chunk_results = value
                    else:
                        yield value
                
                if disconnect_event.is_set() or await request.is_disconnected():
                    disconnect_event.set()
                    return
                
                for fp in batch_paths:
                    if disconnect_event.is_set() or await request.is_disconnected():
                        disconnect_event.set()
                        return
                    
                    media_id = path_to_id.get(fp)
                    processed += 1
                    tags = chunk_results.get(fp, [])
                    
                    final_tags = postprocess_predicted_tags(
                        tags, db, blacklisted_tags, blacklisted_categories
                    )
                    
                    event = {
                        "type": "result",
                        "media_id": media_id,
                        "tags": final_tags,
                        "progress": processed,
                        "total": total
                    }
                    yield f"data: {json.dumps(event)}\n\n"
                    await asyncio.sleep(0)
                
                i += actual_chunk_size
                target_size = tagger.next_batch_size(target_size, max_stream_batch)
            
            # Completion event
            if not disconnect_event.is_set():
                yield f"data: {json.dumps({'type': 'complete', 'total': processed})}\n\n"
            
        except (asyncio.CancelledError, GeneratorExit):
            disconnect_event.set()
            return
        except Exception as e:
            if not disconnect_event.is_set():
                yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
        finally:
            disconnect_event.set()
            if disconnect_task and not disconnect_task.done():
                disconnect_task.cancel()
            if tagger is not None:
                tagger._reset_idle_timer()
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )

@router.post("/load")
async def load_model(
    request: Request,
    model_name: str = Query(default=DEFAULT_MODEL_NAME),
    current_user: User = Depends(require_admin_mode)
):
    """Pre-load a specific model."""
    if not WDTagger.is_valid_model(model_name):
        raise HTTPException(status_code=400, detail=f"Unknown model: {model_name}")

    disconnect_event = asyncio.Event()

    async def watch_disconnect():
        try:
            while not disconnect_event.is_set():
                msg = await request.receive()
                if msg.get("type") == "http.disconnect":
                    disconnect_event.set()
                    break
        except Exception:
            disconnect_event.set()

    disconnect_task = asyncio.create_task(watch_disconnect())
    tagger = None

    try:
        tagger = get_wd_tagger()
        loop = asyncio.get_event_loop()
        
        def load():
            tagger.ensure_loaded(model_name, is_cancelled=lambda: disconnect_event.is_set())
            return tagger.get_optimal_batch_size(model_name)
        
        batch_size = await loop.run_in_executor(_inference_executor, load)
        
        if disconnect_event.is_set():
            raise HTTPException(status_code=499, detail="Load cancelled")
            
        return {
            "success": True,
            "model": model_name,
            "optimal_batch_size": batch_size,
            "message": f"Model {model_name} loaded successfully"
        }
        
    except (asyncio.CancelledError, GeneratorExit, DownloadCancelledException):
        disconnect_event.set()
        raise HTTPException(status_code=499, detail="Load cancelled")
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=f"AI Tagger dependencies not installed: {str(e)}"
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=safe_error_detail("Invalid model", e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=safe_error_detail("Failed to load model", e))
    finally:
        disconnect_event.set()
        if disconnect_task and not disconnect_task.done():
            disconnect_task.cancel()
        if tagger is not None:
            tagger._reset_idle_timer()
