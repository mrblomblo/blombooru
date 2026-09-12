from typing import Any, Dict

from ..common import clean_numeric_or_string, try_parse_json
from .base import AIMetadataBackend

class SwarmUIBackend(AIMetadataBackend):
    name = "SwarmUI"

    def detect(self, raw_meta: Dict[str, Any]) -> bool:
        if "sui_image_params" in raw_meta:
            return True
        params = raw_meta.get("parameters")
        if isinstance(params, dict) and "sui_image_params" in params:
            return True
        parsed = try_parse_json(params)
        if isinstance(parsed, dict) and "sui_image_params" in parsed:
            return True
        return False

    def parse(self, raw_meta: Dict[str, Any]) -> Dict[str, Any]:
        if "sui_image_params" in raw_meta:
            return parse_swarmui_metadata(raw_meta)
        params = raw_meta.get("parameters")
        if isinstance(params, dict) and "sui_image_params" in params:
            return parse_swarmui_metadata(params)
        parsed = try_parse_json(params)
        if isinstance(parsed, dict) and "sui_image_params" in parsed:
            return parse_swarmui_metadata(parsed)
        return {}

def parse_swarmui_metadata(swarm_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Parse SwarmUI metadata containing sui_image_params and optional sui_extra_data."""
    data: Dict[str, Any] = {"software": "SwarmUI"}
    params = swarm_dict.get("sui_image_params", {})
    if not isinstance(params, dict):
        return data

    if "prompt" in params and params["prompt"]:
        data["prompt"] = str(params["prompt"]).strip()
    if "negativeprompt" in params and params["negativeprompt"]:
        data["negative_prompt"] = str(params["negativeprompt"]).strip()
    if "model" in params and params["model"]:
        data["model"] = str(params["model"]).strip()
    if "seed" in params:
        data["seed"] = clean_numeric_or_string(str(params["seed"]))
    if "steps" in params:
        data["steps"] = clean_numeric_or_string(str(params["steps"]))
    if "cfgscale" in params:
        data["cfg_scale"] = clean_numeric_or_string(str(params["cfgscale"]))
    if "sampler" in params and params["sampler"]:
        data["sampler"] = str(params["sampler"]).strip()
    if "scheduler" in params and params["scheduler"]:
        data["scheduler"] = str(params["scheduler"]).strip()
    if "width" in params:
        data["width"] = clean_numeric_or_string(str(params["width"]))
    if "height" in params:
        data["height"] = clean_numeric_or_string(str(params["height"]))

    # Promote VAE to canonical top-level key
    if "vae" in params and params["vae"]:
        data["vae"] = str(params["vae"]).strip()

    extra = swarm_dict.get("sui_extra_data", {})
    add_params: Dict[str, Any] = {}
    standard_keys = {
        "prompt", "negativeprompt", "model", "seed", "steps",
        "cfgscale", "sampler", "scheduler", "width", "height", "vae"
    }

    for k, v in params.items():
        if k not in standard_keys:
            add_params[k] = v
    if isinstance(extra, dict) and extra:
        add_params["extra_data"] = extra
    if add_params:
        data["additional_parameters"] = add_params

    return data
