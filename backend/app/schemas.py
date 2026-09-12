from datetime import datetime
from typing import Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from .enums import (ApiKeyPermissionEnum, FileTypeEnum, RatingEnum,
                    TagCategoryEnum)

class TagBase(BaseModel):
    name: str
    category: TagCategoryEnum = TagCategoryEnum.general
    rating: str = None

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
    description: Optional[str] = None
    parent_id: Optional[int] = None

class MediaResponse(MediaBase):
    id: int
    filename: str
    path: str
    transcoded_path: Optional[str] = None
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
    share_language: Optional[str] = None
    source: Optional[str] = None
    description: Optional[str] = None
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
    share_language: Optional[str] = None
    share_ai_metadata: bool
    hash: str
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

class RedisSettings(BaseModel):
    host: str = "redis"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    enabled: bool = False

class SharedTagSettings(BaseModel):
    enabled: bool = False
    host: str = "shared-tag-db"
    port: int = 5432
    name: str = "shared_tags"
    user: str = "postgres"
    password: Optional[str] = None

class OnboardingData(BaseModel):
    app_name: str
    admin_username: str
    admin_password: str
    database: DatabaseSettings
    redis: RedisSettings

class CustomBackgroundSettings(BaseModel):
    enabled: bool = False
    media_id: Optional[int] = None
    blur: Optional[int] = 10
    brightness: Optional[int] = 100
    saturation: Optional[int] = 65
    contrast: Optional[int] = 100
    zoom: Optional[int] = 100
    size: Optional[str] = "cover"
    position_x: Optional[int] = 50
    position_y: Optional[int] = 50
    opacity: Optional[int] = 25

class SimilarityWeights(BaseModel):
    artist: Optional[float] = Field(5.0, ge=0.0, le=99.99)
    character: Optional[float] = Field(4.0, ge=0.0, le=99.99)
    general: Optional[float] = Field(1.0, ge=0.0, le=99.99)
    copyright: Optional[float] = Field(0.5, ge=0.0, le=99.99)
    meta: Optional[float] = Field(0.05, ge=0.0, le=99.99)

class SettingsUpdate(BaseModel):
    app_name: Optional[str] = None
    items_per_page: Optional[int] = None
    default_sort: Optional[str] = None
    default_order: Optional[str] = None
    popular_tags_mode: Optional[str] = None
    popular_tags_limit: Optional[int] = None
    theme: Optional[str] = None
    language: Optional[str] = None
    external_share_url: Optional[str] = None
    require_auth: Optional[bool] = None
    redis: Optional[RedisSettings] = None
    shared_tags: Optional[SharedTagSettings] = None
    sidebar_filter_mode: Optional[Literal["rating", "custom", "both", "off"]] = None
    sidebar_custom_buttons: Optional[List[dict]] = None
    media_type_tags: Optional[dict] = None
    custom_background: Optional[CustomBackgroundSettings] = None
    similarity_weights: Optional[SimilarityWeights] = None

class ShareSettingsUpdate(BaseModel):
    share_ai_metadata: Optional[bool] = None
    share_language: Optional[str] = None

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
    name: Optional[str] = Field(None, max_length=64)
    permission: ApiKeyPermissionEnum = ApiKeyPermissionEnum.read

class ApiKeyUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=64)
    permission: Optional[ApiKeyPermissionEnum] = None

class ApiKeyResponse(BaseModel):
    id: int
    key: str  # Only returned once on creation
    key_prefix: str
    name: Optional[str]
    permission: str
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class ApiKeyListResponse(BaseModel):
    id: int
    key_prefix: str
    name: Optional[str]
    permission: str
    created_at: datetime
    last_used_at: Optional[datetime]
    is_active: bool
    
    model_config = ConfigDict(from_attributes=True)

class KeybindingSpec(BaseModel):
    code: str = Field(..., min_length=1, description="KeyboardEvent.code (layout-independent)")
    key: str = Field("", description="KeyboardEvent.key at capture time (display only)")

class KeybindingsUpdate(BaseModel):
    bindings: dict[str, KeybindingSpec] # Only include the actions you want to change

class KeybindingsResetRequest(BaseModel):
    action_id: Optional[str] = None # Omit to reset all

class BatchMediaRequest(BaseModel):
    ids: List[int]
    projection: Optional[str] = None

class BatchMetadataRequest(BaseModel):
    ids: List[int]

class BatchTagValidateRequest(BaseModel):
    names: List[str]

class BatchResolveCombinedItem(BaseModel):
    id: Union[int, str]
    current_tags: List[str] = []
    new_tags: List[str] = []

class BatchResolveCombinedRequest(BaseModel):
    items: List[BatchResolveCombinedItem]

class BatchResolveCombinedResultItem(BaseModel):
    current_tags: List[str]
    new_tags: List[str]
    added_tags: List[str]

class BatchResolveCombinedResponse(BaseModel):
    results: Dict[str, BatchResolveCombinedResultItem]
    alias_resolutions: Dict[str, str] = {}

class BulkTagUpdateItem(BaseModel):
    id: int
    tags: List[str]

class BulkTagUpdateRequest(BaseModel):
    items: List[BulkTagUpdateItem]

class BulkTagUpdateResponse(BaseModel):
    status: str = "success"
    updated_count: int
    updated_media_ids: List[int]

class ProposedTag(BaseModel):
    name: str
    category: TagCategoryEnum = TagCategoryEnum.general
    is_new: bool = False
    source: Optional[str] = "user"
    user_assigned: Optional[bool] = False

class UploadSessionItemUpdate(BaseModel):
    rating: Optional[RatingEnum] = None
    tags: Optional[List[ProposedTag]] = None
    source: Optional[str] = None
    description: Optional[str] = None
    album_ids: Optional[List[int]] = None
    suggested_album_path: Optional[str] = None

class UploadSessionItem(BaseModel):
    item_id: str
    filename: str
    relative_path: Optional[str] = None
    file_size: int = 0
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[float] = None
    file_type: Optional[FileTypeEnum] = None
    mime_type: Optional[str] = None
    hash: Optional[str] = None
    rating: RatingEnum = RatingEnum.safe
    source: Optional[str] = None
    description: Optional[str] = None
    tags: List[ProposedTag] = []
    album_ids: List[int] = []
    suggested_album_path: Optional[str] = None
    is_duplicate: bool = False
    duplicate_of: Optional[str] = None

class PendingTagEntity(BaseModel):
    name: str
    category: TagCategoryEnum = TagCategoryEnum.general
    used_by: List[str] = []
    merge_into: Optional[str] = None
    user_assigned: bool = False

class PendingAlbumEntity(BaseModel):
    path: str
    used_by: List[str] = []

class PendingEntitiesResponse(BaseModel):
    pending_tags: List[PendingTagEntity] = []
    pending_albums: List[PendingAlbumEntity] = []

class PendingTagUpdate(BaseModel):
    new_name: Optional[str] = None
    category: Optional[TagCategoryEnum] = None
    merge_into: Optional[str] = None
    remove: Optional[bool] = False

class UploadSessionCommitItemResult(BaseModel):
    item_id: str
    filename: str
    media_id: Optional[int] = None
    status: str
    error: Optional[str] = None

class UploadSessionCommitResponse(BaseModel):
    results: List[UploadSessionCommitItemResult]
    total_created: int
    total_duplicates: int
    total_failed: int
