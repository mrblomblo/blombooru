from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime
from enum import Enum

class RatingEnum(str, Enum):
    safe = "safe"
    questionable = "questionable"
    explicit = "explicit"

class TagCategoryEnum(str, Enum):
    general = "general"
    artist = "artist"
    character = "character"
    copyright = "copyright"
    meta = "meta"

class FileTypeEnum(str, Enum):
    image = "image"
    video = "video"
    gif = "gif"

# Tag Schemas
class TagBase(BaseModel):
    name: str
    category: TagCategoryEnum = TagCategoryEnum.general

class TagCreate(TagBase):
    pass

class TagResponse(TagBase):
    id: int
    post_count: int
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

# Media Schemas
class MediaBase(BaseModel):
    rating: RatingEnum = RatingEnum.safe

class MediaCreate(MediaBase):
    tags: List[str] = []

class MediaUpdate(BaseModel):
    rating: Optional[RatingEnum] = None
    tags: Optional[List[str]] = None

class MediaResponse(MediaBase):
    id: int
    filename: str
    path: str
    thumbnail_path: Optional[str]
    hash: str
    file_type: FileTypeEnum
    mime_type: Optional[str]
    file_size: int
    width: Optional[int]
    height: Optional[int]
    duration: Optional[float]
    uploaded_at: datetime
    is_shared: bool
    share_uuid: Optional[str]
    tags: List[TagResponse] = []
    
    model_config = ConfigDict(from_attributes=True)

# Auth Schemas
class UserCreate(BaseModel):
    username: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

# Settings Schemas
class DatabaseSettings(BaseModel):
    host: str
    port: int
    name: str
    user: str
    password: str

class OnboardingData(BaseModel):
    app_name: str
    admin_username: str
    admin_password: str
    database: DatabaseSettings

class SettingsUpdate(BaseModel):
    app_name: Optional[str] = None
    default_rating_filter: Optional[RatingEnum] = None
    items_per_page: Optional[int] = None
