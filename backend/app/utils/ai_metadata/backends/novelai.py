import json
from typing import Any, Dict

from ..common import clean_numeric_or_string, try_parse_json
from .base import AIMetadataBackend

class NovelAIBackend(AIMetadataBackend):
    name = "NovelAI"

    def detect(self, raw_meta: Dict[str, Any]) -> bool:
        if "Comment" in raw_meta:
            c = raw_meta["Comment"]
            parsed = try_parse_json(c) if isinstance(c, str) else c
            if isinstance(parsed, dict) and ("prompt" in parsed or "uc" in parsed):
                return True
        for key in ("description", "Description"):
            val = raw_meta.get(key)
            parsed = try_parse_json(val) if isinstance(val, str) else val
            if isinstance(parsed, dict) and ("prompt" in parsed or "uc" in parsed):
                return True
        return False

    def parse(self, raw_meta: Dict[str, Any]) -> Dict[str, Any]:
        if "Comment" in raw_meta:
            return parse_novelai_metadata(raw_meta["Comment"])
        for key in ("description", "Description"):
            val = raw_meta.get(key)
            parsed = try_parse_json(val) if isinstance(val, str) else val
            if isinstance(parsed, dict) and ("prompt" in parsed or "uc" in parsed):
                return parse_novelai_metadata(parsed)
        return {}

def parse_novelai_metadata(comment_obj: Any) -> Dict[str, Any]:
    """Parse NovelAI generation metadata typically embedded in PNG Comment chunk."""
    data: Dict[str, Any] = {"software": "NovelAI"}
    if not comment_obj:
        return data

    parsed = comment_obj
    if isinstance(comment_obj, str):
        try:
            parsed = json.loads(comment_obj)
        except Exception:
            return data

    if not isinstance(parsed, dict):
        return data

    if "prompt" in parsed and parsed["prompt"]:
        data["prompt"] = str(parsed["prompt"]).strip()
    if "uc" in parsed and parsed["uc"]:
        data["negative_prompt"] = str(parsed["uc"]).strip()
    elif "negative_prompt" in parsed and parsed["negative_prompt"]:
        data["negative_prompt"] = str(parsed["negative_prompt"]).strip()

    if "model" in parsed and parsed["model"]:
        data["model"] = str(parsed["model"]).strip()
    if "seed" in parsed:
        data["seed"] = clean_numeric_or_string(str(parsed["seed"]))
    if "steps" in parsed:
        data["steps"] = clean_numeric_or_string(str(parsed["steps"]))
    if "scale" in parsed:
        data["cfg_scale"] = clean_numeric_or_string(str(parsed["scale"]))
    if "sampler" in parsed and parsed["sampler"]:
        data["sampler"] = str(parsed["sampler"]).strip()
    if "width" in parsed:
        data["width"] = clean_numeric_or_string(str(parsed["width"]))
    if "height" in parsed:
        data["height"] = clean_numeric_or_string(str(parsed["height"]))

    additional: Dict[str, Any] = {}
    known_keys = {"prompt", "uc", "negative_prompt", "model", "seed", "steps", "scale", "sampler", "width", "height"}
    for k, v in parsed.items():
        if k not in known_keys:
            additional[k] = v
    if additional:
        data["additional_parameters"] = additional

    return data
