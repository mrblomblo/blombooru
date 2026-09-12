import re
from typing import Any, Dict, List

from ..common import clean_numeric_or_string
from .base import AIMetadataBackend

class Automatic1111Backend(AIMetadataBackend):
    name = "Automatic1111"

    KNOWN_PARAM_KEYS = (
        "steps:", "sampler:", "cfg scale:", "seed:", "size:", "model:",
        "model hash:", "clip skip:", "denoising strength:", "hires upscale:",
        "hires upscaler:", "version:", "hashes:", "schedule type:", "controlnet"
    )

    def detect(self, raw_meta: Dict[str, Any]) -> bool:
        for key in ("parameters", "Parameters", "user_comment"):
            val = raw_meta.get(key)
            if isinstance(val, str) and val.strip():
                val_lower = val.lower()
                matches = sum(1 for k in self.KNOWN_PARAM_KEYS if k in val_lower)
                if matches >= 2 or (matches >= 1 and any(k in val_lower for k in ("steps:", "seed:", "negative prompt:"))):
                    return True
        return False

    def parse(self, raw_meta: Dict[str, Any]) -> Dict[str, Any]:
        param_string = ""
        for key in ("parameters", "Parameters", "user_comment", "description", "Description"):
            val = raw_meta.get(key)
            if isinstance(val, str) and val.strip():
                param_string = val.strip()
                break

        if not param_string:
            return {}

        return parse_a1111_parameters(param_string)

def parse_a1111_parameters(param_string: str) -> Dict[str, Any]:
    """Parse Automatic1111 / WebUI generation parameter block."""
    if not param_string or not isinstance(param_string, str):
        return {}

    data: Dict[str, Any] = {"software": "Automatic1111"}
    lines = param_string.splitlines()

    positive_lines: List[str] = []
    negative_lines: List[str] = []
    parameter_lines: List[str] = []

    state = "positive"

    known_keys = Automatic1111Backend.KNOWN_PARAM_KEYS

    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue
        line_lower = line_clean.lower()

        if (state in ("positive", "negative")) and line_lower.startswith("negative prompt:"):
            state = "negative"
            neg_content = line_clean[line_clean.find(":") + 1:].strip()
            if neg_content:
                negative_lines.append(neg_content)
            continue

        # Parameter line detection (order-independent)
        match_count = sum(1 for key in known_keys if key in line_lower)
        is_param_line = False
        if state == "parameters":
            is_param_line = True
        elif match_count >= 2 or (match_count >= 1 and any(k in line_lower for k in ("steps:", "seed:", "controlnet", "size:"))):
            is_param_line = True
            state = "parameters"

        if is_param_line:
            parameter_lines.append(line_clean)
        elif state == "negative":
            negative_lines.append(line_clean)
        else:
            positive_lines.append(line_clean)

    if positive_lines:
        data["prompt"] = "\n".join(positive_lines).strip()
    if negative_lines:
        data["negative_prompt"] = "\n".join(negative_lines).strip()

    if parameter_lines:
        full_param_text = ", ".join(l.rstrip(",") for l in parameter_lines)
        _parse_a1111_parameter_line(full_param_text, data)

    if not (data.get("prompt") or data.get("negative_prompt") or data.get("seed") or data.get("steps")):
        if param_string.strip():
            return {"prompt": param_string.strip()}
        return {}

    return data

def _parse_a1111_parameter_line(param_text: str, data: Dict[str, Any]) -> None:
    """Parse comma-separated key: value pairs from A1111 parameters line."""
    size_match = re.search(r"\bSize:\s*(\d+)\s*x\s*(\d+)\b", param_text, re.IGNORECASE)
    if size_match:
        data["width"] = int(size_match.group(1))
        data["height"] = int(size_match.group(2))

    tokens: List[str] = []
    current: List[str] = []
    in_quotes = False
    quote_char = ""
    bracket_depth = 0

    for char in param_text:
        if char in ('"', "'") and bracket_depth == 0:
            if not in_quotes:
                in_quotes = True
                quote_char = char
            elif quote_char == char:
                in_quotes = False
                quote_char = ""
            current.append(char)
        elif char in ("{", "["):
            bracket_depth += 1
            current.append(char)
        elif char in ("}", "]"):
            if bracket_depth > 0:
                bracket_depth -= 1
            current.append(char)
        elif char == "," and not in_quotes and bracket_depth == 0:
            tokens.append("".join(current).strip())
            current = []
        else:
            current.append(char)

    if current:
        tokens.append("".join(current).strip())

    key_mappings = {
        "steps": "steps",
        "sampler": "sampler",
        "schedule type": "scheduler",
        "cfg scale": "cfg_scale",
        "seed": "seed",
        "model": "model",
        "model hash": "model_hash",
        "clip skip": "clip_skip",
        "denoising strength": "denoise",
        "vae": "vae",
        "version": "version",
    }

    additional: Dict[str, Any] = {}

    for token in tokens:
        if not token or ":" not in token:
            continue
        parts = token.split(":", 1)
        raw_key = parts[0].strip()
        val_str = parts[1].strip()

        if (val_str.startswith('"') and val_str.endswith('"')) or (val_str.startswith("'") and val_str.endswith("'")):
            val_str = val_str[1:-1].strip()

        parsed_val = clean_numeric_or_string(val_str)
        norm_key = raw_key.lower()

        if norm_key in key_mappings:
            data[key_mappings[norm_key]] = parsed_val
        elif norm_key == "size":
            pass
        else:
            clean_key = re.sub(r"\s+", "_", norm_key)
            additional[clean_key] = parsed_val

    if additional:
        data["additional_parameters"] = additional
