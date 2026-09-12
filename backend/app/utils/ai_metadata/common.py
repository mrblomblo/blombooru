import json
import re
from typing import Any, Optional, Union

NEGATIVE_PROMPT_KEYWORDS_REGEX = re.compile(
    r"\b(bad|worst|ugly|deformed|blurry|low quality|watermark|jpeg artifacts|extra limbs|missing limbs)\b",
    re.IGNORECASE,
)

CANONICAL_KEYS = [
    "software",
    "prompt",
    "negative_prompt",
    "prompt_tags",
    "model",
    "model_hash",
    "sampler",
    "scheduler",
    "seed",
    "steps",
    "cfg_scale",
    "denoise",
    "vae",
    "width",
    "height",
    "loras",
    "additional_parameters",
    "workflow",
]

def clean_numeric_or_string(val_str: str) -> Union[int, float, bool, str]:
    """Convert string representation of int, float, or bool to native type."""
    if not isinstance(val_str, str):
        return val_str
    val_str = val_str.strip()
    if not val_str:
        return ""
    if val_str.lower() == "true":
        return True
    if val_str.lower() == "false":
        return False
    try:
        if "." not in val_str:
            return int(val_str)
        return float(val_str)
    except ValueError:
        return val_str

def try_parse_json(val: Any) -> Optional[Any]:
    """Safely attempt to parse JSON string, returning None if parsing fails."""
    if isinstance(val, (dict, list)):
        return val
    if not isinstance(val, str):
        return None
    s = val.strip()
    if not ((s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]"))):
        return None
    try:
        return json.loads(s)
    except Exception:
        return None
