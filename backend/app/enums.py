import enum
from typing import Any, Dict, Iterable, List, Optional, Union

class RatingEnum(str, enum.Enum):
    safe = "safe"
    questionable = "questionable"
    explicit = "explicit"

    @classmethod
    def _missing_(cls, value: object):
        if isinstance(value, str):
            cleaned = value.strip().lower()
            if cleaned in RATING_MAP:
                return RATING_MAP[cleaned]
        return super()._missing_(value)

    @classmethod
    def normalize(cls, val: Any) -> Optional["RatingEnum"]:
        """Normalize any rating string, shorthand, or enum to a RatingEnum, or None if invalid."""
        if val is None:
            return None
        if isinstance(val, cls):
            return val
        if isinstance(val, str):
            cleaned = val.strip().lower()
            return RATING_MAP.get(cleaned)
        return None

class TagCategoryEnum(str, enum.Enum):
    general = "general"
    artist = "artist"
    character = "character"
    copyright = "copyright"
    meta = "meta"

class FileTypeEnum(str, enum.Enum):
    image = "image"
    video = "video"
    gif = "gif"

class ApiKeyPermissionEnum(str, enum.Enum):
    read = "read"
    write = "write"
    admin = "admin"

RATING_MAP: Dict[str, RatingEnum] = {
    "s": RatingEnum.safe,
    "safe": RatingEnum.safe,
    "q": RatingEnum.questionable,
    "questionable": RatingEnum.questionable,
    "e": RatingEnum.explicit,
    "explicit": RatingEnum.explicit,
}

RATING_TO_SHORTHAND_MAP: Dict[str, str] = {
    "safe": "s",
    "questionable": "q",
    "explicit": "e",
}

def parse_rating_filter(rating: Optional[Union[str, Iterable[Any]]]) -> List[RatingEnum]:
    """Parse a comma-separated rating string or iterable into unique valid RatingEnum values."""
    if rating is None:
        return []
    if isinstance(rating, str):
        if not rating.strip():
            return []
        vals = [r.strip().lower() for r in rating.split(",") if r.strip()]
    elif isinstance(rating, (list, tuple, set)):
        vals = []
        for item in rating:
            if isinstance(item, RatingEnum):
                vals.append(item.value)
            elif isinstance(item, str) and item.strip():
                for sub in item.split(","):
                    if sub.strip():
                        vals.append(sub.strip().lower())
    else:
        return []

    ratings = [RATING_MAP[r] for r in vals if r in RATING_MAP]
    seen = set()
    result = []
    for r in ratings:
        if r not in seen:
            seen.add(r)
            result.append(r)
    return result

def is_rating_filter_active(valid_ratings: List[RatingEnum]) -> bool:
    """Returns True if ratings are restricted (i.e. not empty and not all ratings allowed)."""
    return 0 < len(valid_ratings) < len(RatingEnum)

def rating_to_str(rating: Any) -> str:
    if rating is None:
        return "safe"
    return rating.value if hasattr(rating, "value") else str(rating)
