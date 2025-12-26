from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel
from pathlib import Path
import logging
import os

from ..database import get_db
from ..auth import require_admin_mode
from ..models import Media, User
from ..services.wd_tagger import get_wd_tagger, WDTagger
from ..config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai-tagger", tags=["ai-tagger"])


def find_media_file(filename: str) -> Optional[Path]:
    """
    Find a media file in ORIGINAL_DIR or its subdirectories.
    Returns the full path if found, None otherwise.
    """
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


class PredictedTag(BaseModel):
    name: str
    category: str
    confidence: float


class PredictTagsResponse(BaseModel):
    media_id: int
    tags: list[PredictedTag]
    model_used: str


class ModelStatusResponse(BaseModel):
    model_name: str
    is_downloaded: bool
    is_loaded: bool
    download_size_mb: Optional[float] = None


@router.get("/status")
async def get_tagger_status():
    """Check if the AI tagger is available and loaded."""
    try:
        tagger = get_wd_tagger()
        return {
            "available": True,
            "loaded": tagger.is_loaded,
            "current_model": tagger.current_model,
            "available_models": list(WDTagger.AVAILABLE_MODELS.keys())
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
        
        # Check if model files exist in HuggingFace cache
        is_downloaded = False
        try:
            import huggingface_hub
            model_repo = WDTagger.AVAILABLE_MODELS[model_name]
            
            # Try to get cached file paths (doesn't download)
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
        
        # Approximate download sizes for models (in MB)
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
            download_size_mb=model_sizes.get(model_name)
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
        tagger = get_wd_tagger()
        tagger.ensure_loaded(model_name)
        
        return {
            "success": True,
            "model": model_name,
            "message": f"Model {model_name} downloaded and loaded successfully"
        }
        
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=f"AI Tagger dependencies not installed: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error downloading model {model_name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/predict/{media_id}", response_model=PredictTagsResponse)
async def predict_tags(
    media_id: int,
    request: PredictTagsRequest = PredictTagsRequest(),
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Predict tags for a media item using WD Tagger."""
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
        tagger = get_wd_tagger()
        
        # Check if model is loaded - if not, the caller should have called /download first
        if not tagger.is_loaded or tagger.current_model != request.model_name:
            # Check if already downloaded
            try:
                import huggingface_hub
                model_repo = WDTagger.AVAILABLE_MODELS[request.model_name]
                huggingface_hub.hf_hub_download(
                    model_repo, 
                    WDTagger.MODEL_FILENAME,
                    local_files_only=True
                )
            except Exception:
                raise HTTPException(
                    status_code=428,  # Precondition Required
                    detail="Model not downloaded. Please download the model first."
                )
        
        predictions = tagger.predict_from_file(
            str(file_path),
            general_threshold=request.general_threshold,
            character_threshold=request.character_threshold,
            hide_rating_tags=request.hide_rating_tags,
            character_tags_first=request.character_tags_first,
            model_name=request.model_name
        )
        
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
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error predicting tags for media {media_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error predicting tags: {str(e)}"
        )


@router.post("/load")
async def load_model(
    model_name: str = Query(default="wd-eva02-large-tagger-v3"),
    current_user: User = Depends(require_admin_mode)
):
    """Pre-load a specific model (assumes already downloaded)."""
    try:
        tagger = get_wd_tagger()
        tagger.ensure_loaded(model_name)
        
        return {
            "success": True,
            "model": model_name,
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
        logger.error(f"Error loading model {model_name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
