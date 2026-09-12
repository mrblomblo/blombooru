import re
from typing import Any, Dict, List

from ..common import clean_numeric_or_string, try_parse_json
from .base import AIMetadataBackend

class FooocusBackend(AIMetadataBackend):
    name = "Fooocus"

    SIGNATURE_KEYS = (
        "fooocus",
        "fooocus v2 expansion",
        "guidance scale:",
        "guidance_scale",
        "adm_scaler_positive",
        "base model:",
        "base_model",
    )

    def detect(self, raw_meta: Dict[str, Any]) -> bool:
        if "fooocus" in raw_meta:
            return True

        for key in ("parameters", "Parameters", "Comment", "user_comment", "description", "Description"):
            val = raw_meta.get(key)
            if isinstance(val, dict):
                if any(k in val for k in ("fooocus", "guidance_scale", "adm_scaler_positive", "base_model")):
                    return True
            elif isinstance(val, str) and val.strip():
                val_lower = val.lower()
                if "fooocus" in val_lower or any(sig in val_lower for sig in self.SIGNATURE_KEYS):
                    return True
        return False

    def parse(self, raw_meta: Dict[str, Any]) -> Dict[str, Any]:
        if "fooocus" in raw_meta:
            return parse_fooocus_metadata(raw_meta["fooocus"])

        for key in ("parameters", "Parameters", "Comment", "user_comment", "description", "Description"):
            val = raw_meta.get(key)
            parsed = try_parse_json(val) if isinstance(val, str) else val
            if isinstance(parsed, dict) and any(k in parsed for k in ("fooocus", "guidance_scale", "base_model", "prompt")):
                return parse_fooocus_metadata(parsed)
            if isinstance(val, str) and ("fooocus" in val.lower() or "guidance scale:" in val.lower()):
                return parse_fooocus_metadata(val)

        return {}

def parse_fooocus_metadata(raw: Any) -> Dict[str, Any]:
    """Parse Fooocus metadata from JSON dict or key-value string."""
    data: Dict[str, Any] = {"software": "Fooocus"}
    if not raw:
        return data

    if isinstance(raw, str):
        parsed_json = try_parse_json(raw)
        if isinstance(parsed_json, dict):
            raw = parsed_json
        else:
            return _parse_fooocus_text(raw, data)

    if not isinstance(raw, dict):
        return data

    # 1. JSON structure
    if "prompt" in raw and raw["prompt"]:
        data["prompt"] = str(raw["prompt"]).strip()
    if "negative_prompt" in raw and raw["negative_prompt"]:
        data["negative_prompt"] = str(raw["negative_prompt"]).strip()

    if "base_model" in raw and raw["base_model"]:
        data["model"] = str(raw["base_model"]).strip()
    elif "base_model_name" in raw and raw["base_model_name"]:
        data["model"] = str(raw["base_model_name"]).strip()

    if "sampler" in raw and raw["sampler"]:
        data["sampler"] = str(raw["sampler"]).strip()
    elif "sampler_name" in raw and raw["sampler_name"]:
        data["sampler"] = str(raw["sampler_name"]).strip()

    if "scheduler" in raw and raw["scheduler"]:
        data["scheduler"] = str(raw["scheduler"]).strip()

    if "seed" in raw:
        data["seed"] = clean_numeric_or_string(str(raw["seed"]))
    if "steps" in raw:
        data["steps"] = clean_numeric_or_string(str(raw["steps"]))

    # Guidance scale -> cfg_scale
    if "guidance_scale" in raw:
        data["cfg_scale"] = clean_numeric_or_string(str(raw["guidance_scale"]))
    elif "cfg" in raw:
        data["cfg_scale"] = clean_numeric_or_string(str(raw["cfg"]))

    # Resolution
    if "resolution" in raw:
        res = raw["resolution"]
        _extract_resolution(str(res), data)

    # Additional parameters
    additional: Dict[str, Any] = {}
    known = {
        "prompt", "negative_prompt", "base_model", "base_model_name",
        "sampler", "sampler_name", "scheduler", "seed", "steps",
        "guidance_scale", "cfg", "resolution"
    }
    for k, v in raw.items():
        if k not in known:
            additional[k] = v
    if additional:
        data["additional_parameters"] = additional

    return data

def _parse_fooocus_text(text: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Parse Fooocus key-value parameter block."""
    lines = text.splitlines()
    positive_lines: List[str] = []
    negative_lines: List[str] = []
    additional: Dict[str, Any] = {}

    state = "positive"

    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue
        line_lower = line_clean.lower()

        if line_lower.startswith("negative prompt:"):
            state = "negative"
            neg_content = line_clean[len("negative prompt:"):].strip()
            if neg_content:
                negative_lines.append(neg_content)
            continue

        if ":" in line_clean:
            parts = line_clean.split(":", 1)
            key = parts[0].strip().lower()
            val = parts[1].strip()

            if key in ("base model", "base_model"):
                state = "params"
                data["model"] = val
                continue
            elif key in ("sampler", "sampler_name"):
                state = "params"
                data["sampler"] = val
                continue
            elif key in ("scheduler", "schedule type"):
                state = "params"
                data["scheduler"] = val
                continue
            elif key == "seed":
                state = "params"
                data["seed"] = clean_numeric_or_string(val)
                continue
            elif key in ("steps", "step"):
                state = "params"
                data["steps"] = clean_numeric_or_string(val)
                continue
            elif key in ("guidance scale", "guidance_scale", "cfg scale"):
                state = "params"
                data["cfg_scale"] = clean_numeric_or_string(val)
                continue
            elif key == "resolution":
                state = "params"
                _extract_resolution(val, data)
                continue
            elif state == "params" or any(k in key for k in ("fooocus", "sharpness", "adm", "refiner", "styles", "performance")):
                state = "params"
                clean_k = re.sub(r"\s+", "_", key)
                additional[clean_k] = clean_numeric_or_string(val)
                continue

        if state == "positive":
            positive_lines.append(line_clean)
        elif state == "negative":
            negative_lines.append(line_clean)

    if positive_lines:
        data["prompt"] = "\n".join(positive_lines).strip()
    if negative_lines:
        data["negative_prompt"] = "\n".join(negative_lines).strip()
    if additional:
        data["additional_parameters"] = additional

    return data

def _extract_resolution(res_str: str, data: Dict[str, Any]) -> None:
    """Parse dimensions from resolution string like '(1152, 896)', '1152*896', or '1152x896'."""
    m = re.search(r"(\d+)\s*[,*xX]\s*(\d+)", res_str)
    if m:
        data["width"] = int(m.group(1))
        data["height"] = int(m.group(2))
