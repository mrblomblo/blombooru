import os
import numpy as np
import pandas as pd
import onnxruntime as rt
from PIL import Image
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class WDTagger:
    """
    WD Tagger using ONNX models from SmilingWolf's collection.
    Singleton pattern to avoid reloading the model.
    """
    _instance = None
    _initialized = False
    
    AVAILABLE_MODELS = {
        "wd-eva02-large-tagger-v3": "SmilingWolf/wd-eva02-large-tagger-v3",
        "wd-vit-tagger-v3": "SmilingWolf/wd-vit-tagger-v3",
        "wd-swinv2-tagger-v3": "SmilingWolf/wd-swinv2-tagger-v3",
        "wd-convnext-tagger-v3": "SmilingWolf/wd-convnext-tagger-v3",
        "wd-vit-large-tagger-v3": "SmilingWolf/wd-vit-large-tagger-v3",
    }
    
    MODEL_FILENAME = "model.onnx"
    LABEL_FILENAME = "selected_tags.csv"
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self._model = None
            self._tag_data = None
            self._target_size = None
            self._current_model_name = None
            WDTagger._initialized = True
    
    def _load_model(self, model_name: str = "wd-eva02-large-tagger-v3"):
        """Load the specified model from HuggingFace Hub."""
        if model_name not in self.AVAILABLE_MODELS:
            raise ValueError(f"Unknown model: {model_name}. Available: {list(self.AVAILABLE_MODELS.keys())}")
        
        if self._current_model_name == model_name and self._model is not None:
            return  # Already loaded
        
        try:
            import huggingface_hub
        except ImportError:
            raise ImportError("huggingface_hub is required. Install with: pip install huggingface_hub")
        
        model_repo = self.AVAILABLE_MODELS[model_name]
        logger.info(f"Loading WD Tagger model: {model_name} from {model_repo}")
        
        # Download from HuggingFace
        csv_path = huggingface_hub.hf_hub_download(model_repo, self.LABEL_FILENAME)
        model_path = huggingface_hub.hf_hub_download(model_repo, self.MODEL_FILENAME)
        
        # Load tags
        df = pd.read_csv(csv_path)
        self._tag_data = {
            'names': df["name"].tolist(),
            'rating': list(np.where(df["category"] == 9)[0]),
            'general': list(np.where(df["category"] == 0)[0]),
            'character': list(np.where(df["category"] == 4)[0]),
        }
        
        # Load model with ONNX Runtime
        try:
            available = rt.get_available_providers()
            providers = []
            
            if 'CUDAExecutionProvider' in available:
                providers.append('CUDAExecutionProvider')
            
            providers.append('CPUExecutionProvider')
            
            self._model = rt.InferenceSession(model_path, providers=providers)
        except Exception as e:
            logger.warning(f"Failed to load model with preferred providers: {e}. Attempting CPU fallback.")
            try:
                self._model = rt.InferenceSession(model_path, providers=['CPUExecutionProvider'])
            except Exception as e2:
                logger.error(f"Critical error: Failed to load model even on CPU: {e2}")
                raise e2

        self._target_size = self._model.get_inputs()[0].shape[2]
        self._current_model_name = model_name
        
        active_providers = self._model.get_providers()
        logger.info(f"WD Tagger loaded successfully. Target size: {self._target_size}, Active Providers: {active_providers}")
    
    def ensure_loaded(self, model_name: str = "wd-eva02-large-tagger-v3"):
        """Ensure the model is loaded."""
        if self._model is None or self._current_model_name != model_name:
            self._load_model(model_name)
    
    def _prepare_image(self, image: Image.Image) -> np.ndarray:
        """Preprocess image for the model."""
        # Handle transparency - paste on white background
        if image.mode == 'RGBA':
            canvas = Image.new("RGBA", image.size, (255, 255, 255, 255))
            canvas.paste(image, mask=image.split()[3])
            image = canvas.convert("RGB")
        elif image.mode != 'RGB':
            image = image.convert("RGB")
        
        # Pad to square
        max_dim = max(image.size)
        pad_left = (max_dim - image.size[0]) // 2
        pad_top = (max_dim - image.size[1]) // 2
        padded_image = Image.new("RGB", (max_dim, max_dim), (255, 255, 255))
        padded_image.paste(image, (pad_left, pad_top))
        
        # Resize to target size
        padded_image = padded_image.resize((self._target_size, self._target_size), Image.BICUBIC)
        
        # Convert to numpy array in BGR format (model expects BGR)
        image_array = np.asarray(padded_image, dtype=np.float32)[..., [2, 1, 0]]
        
        return np.expand_dims(image_array, axis=0)
    
    def predict(
        self,
        image: Image.Image,
        general_threshold: float = 0.35,
        character_threshold: float = 0.85,
        hide_rating_tags: bool = True,
        character_tags_first: bool = True,
        model_name: str = "wd-eva02-large-tagger-v3"
    ) -> list[dict]:
        """
        Predict tags for an image.
        
        Returns list of dicts with 'name', 'category', and 'confidence' keys.
        """
        self.ensure_loaded(model_name)
        
        processed_image = self._prepare_image(image)
        preds = self._model.run(None, {self._model.get_inputs()[0].name: processed_image})[0]
        scores = preds.flatten()
        
        results = []
        
        # Character tags
        for i in self._tag_data['character']:
            if scores[i] >= character_threshold:
                results.append({
                    'name': self._tag_data['names'][i],
                    'category': 'character',
                    'confidence': float(scores[i])
                })
        
        # General tags
        for i in self._tag_data['general']:
            if scores[i] >= general_threshold:
                results.append({
                    'name': self._tag_data['names'][i],
                    'category': 'general',
                    'confidence': float(scores[i])
                })
        
        # Rating tags (optional)
        if not hide_rating_tags:
            for i in self._tag_data['rating']:
                if scores[i] > 0.5:  # Only include if reasonably confident
                    results.append({
                        'name': self._tag_data['names'][i],
                        'category': 'rating',
                        'confidence': float(scores[i])
                    })
        
        # Sort by confidence within each category, then combine
        if character_tags_first:
            char_tags = sorted([r for r in results if r['category'] == 'character'], 
                             key=lambda x: x['confidence'], reverse=True)
            general_tags = sorted([r for r in results if r['category'] == 'general'], 
                                key=lambda x: x['confidence'], reverse=True)
            rating_tags = sorted([r for r in results if r['category'] == 'rating'], 
                               key=lambda x: x['confidence'], reverse=True)
            results = char_tags + general_tags + rating_tags
        else:
            results.sort(key=lambda x: x['confidence'], reverse=True)
        
        return results
    
    def predict_from_file(
        self,
        file_path: str,
        **kwargs
    ) -> list[dict]:
        """
        Predict tags from a file path.
        Handles images, GIFs (first frame), and videos (first frame).
        """
        ext = Path(file_path).suffix.lower()
        
        if ext == '.gif':
            image = self._extract_gif_frame(file_path)
        elif ext in ['.mp4', '.webm', '.mov', '.avi', '.mkv']:
            image = self._extract_video_frame(file_path)
        else:
            image = Image.open(file_path)
        
        return self.predict(image, **kwargs)
    
    def _extract_gif_frame(self, file_path: str, frame_index: int = 0) -> Image.Image:
        """Extract a frame from a GIF."""
        with Image.open(file_path) as gif:
            gif.seek(frame_index)
            return gif.convert('RGB')
    
    def _extract_video_frame(self, file_path: str, frame_index: int = 0) -> Image.Image:
        """Extract a frame from a video file using ffmpeg."""
        import subprocess
        import tempfile
        
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            tmp_path = tmp.name
        
        try:
            # Use ffmpeg to extract the first frame
            cmd = [
                'ffmpeg', '-i', file_path,
                '-vf', f'select=eq(n\\,{frame_index})',
                '-vframes', '1',
                '-y', tmp_path
            ]
            subprocess.run(cmd, capture_output=True, check=True)
            
            image = Image.open(tmp_path).convert('RGB')
            return image
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    
    @property
    def is_loaded(self) -> bool:
        return self._model is not None
    
    @property
    def current_model(self) -> Optional[str]:
        return self._current_model_name


# Global singleton instance
_tagger_instance: Optional[WDTagger] = None

def get_wd_tagger() -> WDTagger:
    """Get the singleton WD Tagger instance."""
    global _tagger_instance
    if _tagger_instance is None:
        _tagger_instance = WDTagger()
    return _tagger_instance
