from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel
from pathlib import Path
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import os
import time

from ..database import get_db
from ..auth import require_admin_mode
from ..models import Media, User
from ..services.wd_tagger import get_wd_tagger, WDTagger
from ..config import settings

router = APIRouter(prefix="/api/ai-tagger", tags=["ai-tagger"])

# Dedicated thread pool for inference
_inference_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="wd_inference")

def shutdown_tagger_resources():
    """Cleanup tagger resources on application shutdown."""
    _inference_executor.shutdown(wait=False)
    try:
        from ..services.wd_tagger import get_wd_tagger
        get_wd_tagger().shutdown()
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

@router.get("/model-status/{model_name}", response_model=ModelStatusResponse)
async def get_model_status(
    model_name: str,
    current_user: User = Depends(require_admin_mode)
):
    """Check if a specific model is downloaded and/or loaded."""
    if model_name not in WDTagger.AVAILABLE_MODELS:
        raise HTTPException(status_code=400, detail=f"Unknown model: {model_name}")
    
    try:
        tagger = get_wd_tagger()
        is_loaded = tagger.is_loaded and tagger.current_model == model_name
        
        is_downloaded = False
        try:
            import huggingface_hub
            model_repo = WDTagger.AVAILABLE_MODELS[model_name]
            
            try:
                huggingface_hub.hf_hub_download(
                    model_repo, 
                    WDTagger.MODEL_FILENAME,
                    local_files_only=True
                )
                huggingface_hub.hf_hub_download(
                    model_repo, 
                    WDTagger.LABEL_FILENAME,
                    local_files_only=True
                )
                is_downloaded = True
            except Exception:
                is_downloaded = False
                
        except ImportError:
            pass
        
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
            download_size_mb=model_sizes.get(model_name),
            optimal_batch_size=WDTagger.OPTIMAL_BATCH_SIZES.get(model_name)
        )
        
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=f"AI Tagger dependencies not installed: {str(e)}"
        )

@router.post("/download/{model_name}")
async def download_model(
    model_name: str,
    current_user: User = Depends(require_admin_mode)
):
    """Download a specific model (blocking)."""
    if model_name not in WDTagger.AVAILABLE_MODELS:
        raise HTTPException(status_code=400, detail=f"Unknown model: {model_name}")
    
    try:
        loop = asyncio.get_event_loop()
        
        def load():
            tagger = get_wd_tagger()
            tagger.ensure_loaded(model_name)
            return tagger.get_optimal_batch_size(model_name)
        
        batch_size = await loop.run_in_executor(_inference_executor, load)
        
        return {
            "success": True,
            "model": model_name,
            "optimal_batch_size": batch_size,
            "message": f"Model {model_name} downloaded and loaded successfully"
        }
        
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=f"AI Tagger dependencies not installed: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
        
        return PredictTagsResponse(
            media_id=media_id,
            tags=[PredictedTag(**tag) for tag in predictions],
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
            detail=f"Error predicting tags: {str(e)}"
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
        
        for file_path, tags in predictions:
            media_id = path_to_media_id.get(file_path)
            if media_id is not None:
                results.append(PredictTagsResponse(
                    media_id=media_id,
                    tags=[PredictedTag(**tag) for tag in tags],
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
            detail=f"Error predicting tags: {str(e)}"
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
        
        if not file_info:
            yield f"data: {json.dumps({'type': 'complete', 'total': 0})}\n\n"
            return
        
        try:
            tagger = get_wd_tagger()
            tagger.ensure_loaded(batch_request.model_name)
            
            file_paths = [fp for _, fp in file_info]
            total = len(file_paths)
            processed = 0
            
            for file_path, tags in tagger.predict_from_files_streaming(
                file_paths,
                general_threshold=batch_request.general_threshold,
                character_threshold=batch_request.character_threshold,
                hide_rating_tags=batch_request.hide_rating_tags,
                character_tags_first=batch_request.character_tags_first,
                model_name=batch_request.model_name
            ):
                # Check for client disconnect
                if await request.is_disconnected():
                    return
                
                media_id = path_to_id.get(file_path)
                processed += 1
                
                event = {
                    "type": "result",
                    "media_id": media_id,
                    "tags": tags,
                    "progress": processed,
                    "total": total
                }
                yield f"data: {json.dumps(event)}\n\n"
            
            # Completion event
            yield f"data: {json.dumps({'type': 'complete', 'total': processed})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
    
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
    model_name: str = Query(default="wd-eva02-large-tagger-v3"),
    current_user: User = Depends(require_admin_mode)
):
    """Pre-load a specific model."""
    try:
        loop = asyncio.get_event_loop()
        
        def load():
            tagger = get_wd_tagger()
            tagger.ensure_loaded(model_name)
            return tagger.get_optimal_batch_size(model_name)
        
        batch_size = await loop.run_in_executor(_inference_executor, load)
        
        return {
            "success": True,
            "model": model_name,
            "optimal_batch_size": batch_size,
            "message": f"Model {model_name} loaded successfully"
        }
    
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=f"AI Tagger dependencies not installed: {str(e)}"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
