import json
from typing import Any, Dict

from ..common import clean_numeric_or_string
from .base import AIMetadataBackend

class InvokeAIBackend(AIMetadataBackend):
    name = "InvokeAI"

    def detect(self, raw_meta: Dict[str, Any]) -> bool:
        return "invokeai_metadata" in raw_meta or "sd-metadata" in raw_meta

    def parse(self, raw_meta: Dict[str, Any]) -> Dict[str, Any]:
        if "invokeai_metadata" in raw_meta:
            return parse_invokeai_metadata(raw_meta["invokeai_metadata"])
        if "sd-metadata" in raw_meta:
            return parse_invokeai_metadata(raw_meta["sd-metadata"])
        return {}

def parse_invokeai_metadata(invoke_obj: Any) -> Dict[str, Any]:
    """Parse InvokeAI metadata (invokeai_metadata or sd-metadata)."""
    data: Dict[str, Any] = {"software": "InvokeAI"}
    if not invoke_obj:
        return data

    if isinstance(invoke_obj, str):
        try:
            invoke_obj = json.loads(invoke_obj)
        except Exception:
            return data
    if not isinstance(invoke_obj, dict):
        return data

    # InvokeAI v3/v4 format
    if "positive_prompt" in invoke_obj and invoke_obj["positive_prompt"]:
        data["prompt"] = str(invoke_obj["positive_prompt"]).strip()
    if "negative_prompt" in invoke_obj and invoke_obj["negative_prompt"]:
        data["negative_prompt"] = str(invoke_obj["negative_prompt"]).strip()

    if "model" in invoke_obj:
        m = invoke_obj["model"]
        if isinstance(m, dict):
            name = m.get("name")
            if name:
                data["model"] = str(name).strip()
            elif "model_name" in m:
                data["model"] = str(m["model_name"]).strip()
            else:
                data["model"] = str(m).strip()
        elif m:
            data["model"] = str(m).strip()

    if "steps" in invoke_obj:
        data["steps"] = clean_numeric_or_string(str(invoke_obj["steps"]))
    if "cfg_scale" in invoke_obj:
        data["cfg_scale"] = clean_numeric_or_string(str(invoke_obj["cfg_scale"]))
    if "seed" in invoke_obj:
        data["seed"] = clean_numeric_or_string(str(invoke_obj["seed"]))
    if "width" in invoke_obj:
        data["width"] = clean_numeric_or_string(str(invoke_obj["width"]))
    if "height" in invoke_obj:
        data["height"] = clean_numeric_or_string(str(invoke_obj["height"]))

    # Older InvokeAI sd-metadata format
    if "image" in invoke_obj and isinstance(invoke_obj["image"], dict):
        img_meta = invoke_obj["image"]
        if "prompt" in img_meta and "prompt" not in data:
            p = img_meta["prompt"]
            if isinstance(p, list):
                # Guard against list of strings vs list of dicts
                data["prompt"] = "\n".join(
                    str(x.get("prompt", x) if isinstance(x, dict) else x).strip()
                    for x in p if x
                )
            elif p:
                data["prompt"] = str(p).strip()

        if "steps" in img_meta and "steps" not in data:
            data["steps"] = clean_numeric_or_string(str(img_meta["steps"]))
        if "cfg_scale" in img_meta and "cfg_scale" not in data:
            data["cfg_scale"] = clean_numeric_or_string(str(img_meta["cfg_scale"]))
        if "seed" in img_meta and "seed" not in data:
            data["seed"] = clean_numeric_or_string(str(img_meta["seed"]))
        if "sampler" in img_meta and "sampler" not in data:
            data["sampler"] = str(img_meta["sampler"]).strip()

    return data
