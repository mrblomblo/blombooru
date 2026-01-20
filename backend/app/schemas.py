from pydantic import BaseModel, ConfigDict, Field
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

class MediaBase(BaseModel):
    rating: RatingEnum = RatingEnum.safe

class MediaCreate(MediaBase):
    tags: List[str] = []
    source: Optional[str] = None

class MediaUpdate(BaseModel):
    rating: Optional[RatingEnum] = None
    tags: Optional[List[str]] = None
    source: Optional[str] = None
    parent_id: Optional[int] = None

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
    source: Optional[str] = None
    parent_id: Optional[int] = None
    has_children: bool = False
    tags: List[TagResponse] = []
    
    model_config = ConfigDict(from_attributes=True)

class SharedTagResponse(TagBase):
    model_config = ConfigDict(from_attributes=True)

class SharedMediaResponse(MediaBase):
    filename: str
    file_type: FileTypeEnum
    mime_type: Optional[str]
    file_size: int
    width: Optional[int]
    height: Optional[int]
    duration: Optional[float]
    uploaded_at: datetime
    is_shared: bool
    share_uuid: Optional[str]
    share_ai_metadata: bool
    tags: List[SharedTagResponse] = []
    
    model_config = ConfigDict(from_attributes=True)

class UserCreate(BaseModel):
    username: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    
class ChangePasswordData(BaseModel):
    new_password: str = Field(..., min_length=6, max_length=50)

class ChangeUsernameData(BaseModel):
    new_username: str = Field(..., min_length=1)

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
    items_per_page: Optional[int] = None
    default_sort: Optional[str] = None
    default_order: Optional[str] = None
    theme: Optional[str] = None
    external_share_url: Optional[str] = None
    require_auth: Optional[bool] = None

class AlbumBase(BaseModel):
    name: str

class AlbumCreate(AlbumBase):
    parent_album_id: Optional[int] = None

class AlbumUpdate(BaseModel):
    name: Optional[str] = None
    parent_album_id: Optional[int] = None

class AlbumResponse(AlbumBase):
    id: int
    created_at: datetime
    updated_at: datetime
    last_modified: datetime
    media_count: int = 0
    children_count: int = 0
    rating: RatingEnum = RatingEnum.safe
    parent_ids: List[int] = []
    
    model_config = ConfigDict(from_attributes=True)

class AlbumListResponse(AlbumBase):
    id: int
    last_modified: datetime
    thumbnail_paths: List[str] = []
    rating: RatingEnum = RatingEnum.safe
    media_count: int = 0
    
    model_config = ConfigDict(from_attributes=True)

class MediaIds(BaseModel):
    media_ids: List[int]

class ApiKeyCreate(BaseModel):
    name: Optional[str] = None

class ApiKeyResponse(BaseModel):
    id: int
    key: str  # Only returned once on creation
    key_prefix: str
    name: Optional[str]
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class ApiKeyListResponse(BaseModel):
    id: int
    key_prefix: str
    name: Optional[str]
    created_at: datetime
    last_used_at: Optional[datetime]
    is_active: bool
    
    model_config = ConfigDict(from_attributes=True)
