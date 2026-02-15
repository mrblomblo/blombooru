from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class BooruTag:
    """A tag from an external booru."""
    name: str
    category: str  # general, artist, character, copyright, meta

@dataclass
class BooruPost:
    """A post from an external booru."""
    id: int
    tags: List[BooruTag]
    rating: str  # safe, questionable, explicit
    source: str
    file_url: Optional[str]
    preview_url: Optional[str]
    filename: str
    width: int = 0
    height: int = 0
    file_size: int = 0
    score: int = 0
    booru_url: str = ""
