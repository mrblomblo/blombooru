from typing import Any, Dict, List, Optional

from .backends.a1111 import Automatic1111Backend
from .backends.base import AIMetadataBackend
from .backends.comfyui import ComfyUIBackend
from .backends.fooocus import FooocusBackend
from .backends.invokeai import InvokeAIBackend
from .backends.novelai import NovelAIBackend
from .backends.swarmui import SwarmUIBackend
from .tags import extract_prompt_tags

DEFAULT_BACKENDS: List[AIMetadataBackend] = [
    SwarmUIBackend(),
    FooocusBackend(),
    ComfyUIBackend(),
    NovelAIBackend(),
    InvokeAIBackend(),
    Automatic1111Backend(),
]

def normalize_ai_metadata(
    raw_meta: Dict[str, Any],
    backends: Optional[List[AIMetadataBackend]] = None
) -> Dict[str, Any]:
    """Orchestrates parsing across all known AI generator backends and produces a cleaned metadata structure."""
    if not raw_meta or not isinstance(raw_meta, dict):
        return {}

    backend_list = backends if backends is not None else DEFAULT_BACKENDS

    for backend in backend_list:
        try:
            if backend.detect(raw_meta):
                res = backend.parse(raw_meta)
                if res and (res.get("prompt") or res.get("seed") or res.get("model") or res.get("steps") or res.get("workflow")):
                    if res.get("prompt") and isinstance(res["prompt"], str) and "prompt_tags" not in res:
                        res["prompt_tags"] = extract_prompt_tags(res["prompt"])
                    return res
        except Exception:
            continue

    # Fallback: simple prompt in description or prompt key if nothing else matched
    for key in ("prompt", "description", "Description", "image_description"):
        val = raw_meta.get(key)
        if isinstance(val, str) and val.strip():
            prompt_str = val.strip()
            return {
                "prompt": prompt_str,
                "prompt_tags": extract_prompt_tags(prompt_str),
            }

    return {}
