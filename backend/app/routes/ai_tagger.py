import asyncio
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import require_admin_mode
from ..config import settings
from ..utils.request_helpers import safe_error_detail
from ..database import get_db
from ..models import Media, User
from ..services.wd_tagger import DownloadCancelledException, WDTagger, get_wd_tagger

router = APIRouter(prefix="/api/ai-tagger", tags=["ai-tagger"])

# Dedicated thread pool for inference
_inference_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="wd_inference")

def shutdown_tagger_resources():
    """Cleanup tagger resources on application shutdown."""
    _inference_executor.shutdown(wait=False)
    try:
        from ..services.wd_tagger import cleanup_orphaned_model_temp_files, get_wd_tagger
        get_wd_tagger().shutdown()
        cleanup_orphaned_model_temp_files()
    except Exception as e:
        pass

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
            "confidence": conf
        })

    return result

class PredictTagsRequest(BaseModel):
    general_threshold: float = 0.35
    character_threshold: float = 0.85
    hide_rating_tags: bool = True
    character_tags_first: bool = True
    model_name: str = "wd-eva02-large-tagger-v3"

class BatchPredictRequest(BaseModel):
    media_ids: List[int]
    general_threshold: float = 0.35
    character_threshold: float = 0.85
    hide_rating_tags: bool = True
    character_tags_first: bool = True
    model_name: str = "wd-eva02-large-tagger-v3"

class PredictedTag(BaseModel):
    name: str
    category: str
    confidence: float

class PredictTagsResponse(BaseModel):
    media_id: int
    tags: List[PredictedTag]
    model_used: str

class BatchPredictResponse(BaseModel):
    results: List[PredictTagsResponse]
    failed_ids: List[int]
    model_used: str
    processing_time_ms: float

class ModelStatusResponse(BaseModel):
    model_name: str
    is_downloaded: bool
    is_loaded: bool
    is_downloading: bool = False
    download_size_mb: Optional[float] = None
    optimal_batch_size: Optional[int] = None

@router.get("/status")
async def get_tagger_status():
    """Check if the AI tagger is available and loaded."""
    try:
        tagger = get_wd_tagger()
        return {
            "available": True,
            "loaded": tagger.is_loaded,
            "current_model": tagger.current_model,
            "available_models": list(WDTagger.AVAILABLE_MODELS.keys()),
        }
    except ImportError as e:
        return {
            "available": False,
            "error": str(e),
            "available_models": list(WDTagger.AVAILABLE_MODELS.keys())
        }

class WDTaggerSettingsRequest(BaseModel):
    general_threshold: Optional[float] = None
    character_threshold: Optional[float] = None
    model_name: Optional[str] = None
    blacklisted_tags: Optional[List[str]] = None
    blacklisted_categories: Optional[List[str]] = None

@router.get("/settings")
async def get_settings(
    current_user: User = Depends(require_admin_mode)
):
    """Get AI tagger settings."""
    return {
        **settings.WD_TAGGER_SETTINGS,
        "available_models": list(WDTagger.AVAILABLE_MODELS.keys())
    }

@router.put("/settings")
@router.post("/settings")
async def update_settings(
    req: WDTaggerSettingsRequest,
    current_user: User = Depends(require_admin_mode)
):
    """Update AI tagger settings in settings.json and in-memory."""
    current_settings = settings.WD_TAGGER_SETTINGS.copy()
    
    if req.general_threshold is not None:
        val = max(0.0, min(1.0, req.general_threshold))
        current_settings["general_threshold"] = round(val, 4)
        
    if req.character_threshold is not None:
        val = max(0.0, min(1.0, req.character_threshold))
        current_settings["character_threshold"] = round(val, 4)
        
    if req.model_name is not None:
        if req.model_name not in WDTagger.AVAILABLE_MODELS:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown model: {req.model_name}. Valid models: {list(WDTagger.AVAILABLE_MODELS.keys())}"
            )
        current_settings["model_name"] = req.model_name

    if req.blacklisted_tags is not None:
        current_settings["blacklisted_tags"] = req.blacklisted_tags

    if req.blacklisted_categories is not None:
        current_settings["blacklisted_categories"] = req.blacklisted_categories
        
    settings.save_settings({"wd_tagger": current_settings})
    
    return {
        "success": True,
        **current_settings,
        "available_models": list(WDTagger.AVAILABLE_MODELS.keys())
    }

@router.get("/models")
async def get_models(
    current_user: User = Depends(require_admin_mode)
):
    """Get list of available models and their download/load status."""
    try:
        tagger = get_wd_tagger()
        current_model = tagger.current_model if tagger.is_loaded else None
        
        models_info = []
        for model_name, repo_id in WDTagger.AVAILABLE_MODELS.items():
            models_info.append({
                "name": model_name,
                "repo_id": repo_id,
                "is_downloaded": WDTagger.is_model_downloaded(model_name),
                "is_loaded": (current_model == model_name),
                "is_downloading": WDTagger.is_downloading(model_name),
                "speed_rank": WDTagger.MODEL_SPEED_RANKING.get(model_name, 99),
            })
        
        models_info.sort(key=lambda x: x["speed_rank"])
        return models_info
        
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
    """Check if a specific model is downloaded, loaded, or currently downloading."""
    if model_name not in WDTagger.AVAILABLE_MODELS:
        raise HTTPException(status_code=400, detail=f"Unknown model: {model_name}")
    
    try:
        tagger = get_wd_tagger()
        is_loaded = tagger.is_loaded and tagger.current_model == model_name
        is_downloading = WDTagger.is_downloading(model_name)
        is_downloaded = WDTagger.is_model_downloaded(model_name)
        
        model_sizes = {
            "wd-eva02-large-tagger-v3": 850,
            "wd-vit-tagger-v3": 350,
            "wd-swinv2-tagger-v3": 450,
            "wd-convnext-tagger-v3": 350,
            "wd-vit-large-tagger-v3": 1200,
        }
        
        return ModelStatusResponse(
            model_name=model_name,
            is_downloaded=is_downloaded,
            is_loaded=is_loaded,
            is_downloading=is_downloading,
            download_size_mb=model_sizes.get(model_name),
            optimal_batch_size=WDTagger.OPTIMAL_BATCH_SIZES.get(model_name)
        )
        
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=f"AI Tagger dependencies not installed: {str(e)}"
        )

@router.delete("/model/{model_name}")
async def delete_model(
    model_name: str,
    current_user: User = Depends(require_admin_mode)
):
    """Delete a downloaded model from the local cache."""
    if model_name not in WDTagger.AVAILABLE_MODELS:
        raise HTTPException(status_code=400, detail=f"Unknown model: {model_name}")

    if WDTagger.is_downloading(model_name):
        raise HTTPException(status_code=409, detail="Cannot delete a model that is currently downloading.")

    try:
        import huggingface_hub
        import shutil

        repo_id = WDTagger.AVAILABLE_MODELS[model_name]
        cache_info = huggingface_hub.scan_cache_dir(cache_dir=settings.MODELS_DIR)

        deleted = False
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

        if not deleted:
            repo_folder_name = "models--" + repo_id.replace("/", "--")
            repo_dir = settings.MODELS_DIR / repo_folder_name
            if repo_dir.exists():
                shutil.rmtree(repo_dir, ignore_errors=True)
                deleted = True

        if not deleted:
            raise HTTPException(status_code=404, detail=f"Model '{model_name}' is not downloaded.")

        # Unload from memory if it was the active model
        tagger = get_wd_tagger()
        if tagger.is_loaded and tagger.current_model == model_name:
            tagger.shutdown()

        return {"success": True, "model_name": model_name}

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
    """Download a specific model with real-time streaming progress."""
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
            while True:
                if disconnect_event.is_set():
                    break
                
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=0.2)
                except asyncio.TimeoutError:
                    if not WDTagger.is_downloading(model_name) and queue.empty():
                        break
                    continue

                yield f"data: {json.dumps(item)}\n\n"
                
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
        filtered_predictions = filter_tags(predictions, blacklisted_tags, blacklisted_categories)
        enriched_predictions = enrich_predicted_tags(filtered_predictions, db)
        final_predictions = filter_tags(enriched_predictions, blacklisted_tags, blacklisted_categories)
        
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
                filtered_tags = filter_tags(tags, blacklisted_tags, blacklisted_categories)
                enriched_tags = enrich_predicted_tags(filtered_tags, db)
                final_tags = filter_tags(enriched_tags, blacklisted_tags, blacklisted_categories)
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
    """
    Stream prediction results using Server-Sent Events.
    Each event is a complete JSON object on its own line.
    """
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
            
            await loop.run_in_executor(_inference_executor, load_model)
            
            file_paths = [fp for _, fp in file_info]
            total = len(file_paths)
            processed = 0
            blacklisted_tags = settings.WD_TAGGER_SETTINGS.get("blacklisted_tags", [])
            blacklisted_categories = settings.WD_TAGGER_SETTINGS.get("blacklisted_categories", [])
            
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
                
                chunk_results = await loop.run_in_executor(_inference_executor, do_chunk)
                
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
                    
                    filtered_tags = filter_tags(tags, blacklisted_tags, blacklisted_categories)
                    enriched_tags = enrich_predicted_tags(filtered_tags, db)
                    final_tags = filter_tags(enriched_tags, blacklisted_tags, blacklisted_categories)
                    
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
                
                if tagger._oom_encountered:
                    target_size = min(target_size + 1, 8)
                else:
                    target_size = min(target_size * 2, 8)
            
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
    model_name: str = Query(default="wd-eva02-large-tagger-v3"),
    current_user: User = Depends(require_admin_mode)
):
    """Pre-load a specific model."""
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
