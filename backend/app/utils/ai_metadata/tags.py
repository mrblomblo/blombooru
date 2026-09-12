import json
import re
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

_WORDLIST_PATH = Path(__file__).parent / "ai_prose_wordlists.json"

def get_ai_prose_wordlists_dict() -> Dict[str, Any]:
    """Return the raw dictionary containing centralized AI prose wordlists."""
    try:
        with open(_WORDLIST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "stopwords": sorted(PROSE_STOPWORDS),
            "start_patterns": list(PROSE_START_PATTERNS),
        }

def get_ai_prose_wordlists_json() -> str:
    """Return the centralized AI prose wordlists as a JSON string."""
    try:
        return _WORDLIST_PATH.read_text(encoding="utf-8")
    except Exception:
        return json.dumps(get_ai_prose_wordlists_dict())

def _load_wordlists() -> Tuple[Set[str], Tuple[str, ...]]:
    try:
        with open(_WORDLIST_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        stopwords = {w.lower() for w in data.get("stopwords", []) if isinstance(w, str)}
        start_patterns = tuple(p for p in data.get("start_patterns", []) if isinstance(p, str))
        return stopwords, start_patterns
    except Exception:
        return set(), ()

PROSE_STOPWORDS, PROSE_START_PATTERNS = _load_wordlists()

PROSE_START_REGEX = re.compile(
    r"^(?:" + "|".join(re.escape(p) for p in sorted(PROSE_START_PATTERNS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

def strip_enclosing_brackets(s: str) -> str:
    """
    Strip outer SD/Booru weight brackets like (tag:1.2), ((tag)), {tag}, [tag]
    only when they wrap the entire token, preserving disambiguation parens like star_(sky).
    """
    while True:
        s = s.strip()
        if len(s) < 2:
            break

        # Check weight syntax: (tag:1.2) or [tag:0.8]
        m = re.match(r"^[(\[{]+(.+?)(?::[0-9.]+)?[\)\]}]+$", s)
        if m:
            inner = m.group(1).strip()
            if inner:
                s = inner
                continue

        # Check if wrapped by matching ( ), [ ], or { }
        pairs = [("(", ")"), ("[", "]"), ("{", "}")]
        stripped_any = False
        for open_ch, close_ch in pairs:
            if s.startswith(open_ch) and s.endswith(close_ch):
                depth = 0
                wraps_entire = True
                for idx, ch in enumerate(s):
                    if ch == open_ch:
                        depth += 1
                    elif ch == close_ch:
                        depth -= 1
                        if depth == 0 and idx < len(s) - 1:
                            wraps_entire = False
                            break
                if wraps_entire and depth == 0:
                    s = s[1:-1].strip()
                    stripped_any = True
                    break

        if not stripped_any:
            break

    return s

def is_prose_segment(s: str) -> bool:
    """Check if a comma-separated or sentence segment is natural-language prose rather than a tag."""
    s = s.strip()
    if not s:
        return False

    # Internal sentence boundary: e.g. "blurred effect. Lighting is artificial"
    if re.search(r"\b[a-z]{2,}[.!?]\s+[A-Za-z]", s):
        return True

    # Starts with a narrative participle, verb, or prepositional phrase
    if PROSE_START_REGEX.search(s):
        return True

    words = [w.lower().strip(".,;:\"'!?") for w in re.split(r"\s+", s) if w.strip(".,;:\"'!?")]
    if not words:
        return False

    stopword_count = sum(1 for w in words if w in PROSE_STOPWORDS)
    if stopword_count >= 2:
        return True

    # A fragment ending with a period that contains a prose word or has >= 2 words
    if s.endswith(".") and (len(words) >= 2 or stopword_count >= 1):
        return True

    # Monolithic long clause
    if len(words) > 7 or len(s) > 55:
        return True

    return False

def split_prompt_segments(text: str) -> List[str]:
    """Split a prompt string on commas and newlines outside of bracket pairs (), [], {}."""
    segments: List[str] = []
    current: List[str] = []
    depth = 0
    in_quotes = False

    for ch in text:
        if ch == '"' and depth == 0:
            in_quotes = not in_quotes
            current.append(ch)
        elif not in_quotes and ch in "([{":
            depth += 1
            current.append(ch)
        elif not in_quotes and ch in ")]}":
            if depth > 0:
                depth -= 1
            current.append(ch)
        elif not in_quotes and depth == 0 and (ch == "," or ch == "\n"):
            seg = "".join(current).strip()
            if seg:
                segments.append(seg)
            current = []
        else:
            current.append(ch)

    if current:
        seg = "".join(current).strip()
        if seg:
            segments.append(seg)

    return segments

def extract_prompt_tags(prompt: str) -> List[str]:
    """Extract clean Booru tags from an AI prompt string."""
    if not prompt or not isinstance(prompt, str):
        return []

    # 1. Remove LoRA, wildcard, and embedding directives
    cleaned = re.sub(r"<[^>]+>", " ", prompt)
    cleaned = re.sub(r"\bembedding:[^\s,]+\b", " ", cleaned, flags=re.IGNORECASE)

    # 2. Space-separated tag dump fallback (no commas or newlines present)
    if "," not in cleaned and "\n" not in cleaned:
        tokens = [t.strip() for t in cleaned.split() if t.strip()]
        if len(tokens) >= 3:
            prose_count = sum(1 for t in tokens if t.lower().strip(".,;:\"'!?") in PROSE_STOPWORDS)
            # If low stopword count and not a sentence ending in period, treat as tag dump
            if prose_count < 2 and not cleaned.strip().endswith((".", "!", "?")):
                raw_segments = tokens
            else:
                raw_segments = []
        else:
            raw_segments = tokens
    else:
        raw_segments = split_prompt_segments(cleaned)

    # Use a worklist to support grouped/weighted tags like:
    # (worst quality, low quality, normal quality:1.4)
    worklist: List[str] = list(raw_segments)
    tags: List[str] = []
    seen: Set[str] = set()

    while worklist:
        seg = worklist.pop(0).strip()
        if not seg:
            continue

        # Skip directives
        if seg.upper() in ("BREAK", "AND"):
            continue

        # Strip outer enclosing brackets: (tag:1.2), ((tag)), {tag}, [tag]
        unwrapped = strip_enclosing_brackets(seg)
        if not unwrapped:
            continue

        # If unwrapping revealed internal commas/newlines that were protected by brackets,
        # e.g. "(worst quality, low quality, normal quality:1.4)" -> "worst quality, low quality, normal quality"
        # expand the sub-segments back into the worklist
        if unwrapped != seg and ("," in unwrapped or "\n" in unwrapped):
            if re.search(r"\b[a-z]{2,}[.!?]\s+[A-Za-z]", unwrapped) or PROSE_START_REGEX.search(unwrapped):
                continue
            sub_segs = split_prompt_segments(unwrapped)
            if len(sub_segs) > 1:
                worklist = sub_segs + worklist
                continue

        # Check prose segment heuristic on the individual tag/segment
        if is_prose_segment(unwrapped):
            continue

        s = unwrapped

        # Clean trailing and leading punctuation (periods, commas, quotes, semicolons)
        s = s.strip(" ,;\"'")
        while s.endswith(".") and not s.endswith(".."):
            s = s[:-1].strip()

        # Strip leading conjunctions/articles: e.g. "and black gloves" -> "black gloves"
        s = re.sub(r"^(and|with|a|an|the)\s+", "", s, flags=re.IGNORECASE).strip()
        if not s:
            continue

        # Normalization: lower case and underscores
        normalized = re.sub(r"\s+", "_", s).lower()

        # Check word count and length
        word_count = len(normalized.split("_"))
        if word_count > 7 or len(normalized) > 55:
            continue

        if normalized and normalized not in seen:
            seen.add(normalized)
            tags.append(normalized)

    return tags
