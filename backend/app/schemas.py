from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from .enums import (ApiKeyPermissionEnum, FileTypeEnum, RatingEnum,
                    TagCategoryEnum)

TagRatingValue = Literal["none", "safe", "questionable", "explicit"]

class TagBase(BaseModel):
    name: str
    category: TagCategoryEnum = TagCategoryEnum.general

class TagCreate(TagBase):
    rating: Optional[TagRatingValue] = None

class TagResponse(TagBase):
    id: int
    rating: TagRatingValue = "none"
    post_count: int
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

    @field_validator("rating", mode="before")
    @classmethod
    def normalize_rating(cls, v: Any) -> str:
        if v is None:
            return "none"
        if hasattr(v, "value"):
            return v.value
        s = str(v).strip().lower()
        return s if s in ("safe", "questionable", "explicit", "none") else "none"

class TagListItem(TagResponse):
    aliases: List[str] = []

class MediaTagResponse(TagResponse):
    implied: bool = False
    implied_by: List[List[str]] = Field(default_factory=list)

    @field_validator("implied", mode="before")
    @classmethod
    def normalize_implied(cls, v: Any) -> bool:
        return bool(v)

    @field_validator("implied_by", mode="before")
    @classmethod
    def normalize_implied_by(cls, v: Any) -> List[List[str]]:
        if not v or not isinstance(v, list):
            return []
        result = []
        for group in v:
            if isinstance(group, list):
                cleaned = [str(item) for item in group if item]
                if cleaned:
                    result.append(cleaned)
        return result

class BulkRatingUpdateRequest(BaseModel):
    tag_ids: List[int]
    rating: TagRatingValue

class MediaBase(BaseModel):
    rating: RatingEnum = RatingEnum.safe

class MediaCreate(MediaBase):
    tags: List[str] = []
    source: Optional[str] = None

class MediaUpdate(BaseModel):
    rating: Optional[RatingEnum] = None
    tags: Optional[List[str]] = None
    implied_tags: Optional[Dict[str, List[List[str]]]] = None
    source: Optional[str] = None
    description: Optional[str] = None
    description_enlarged: Optional[bool] = None
    parent_id: Optional[int] = None
    custom_date: Optional[Union[datetime, str]] = None

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
    custom_date: Optional[datetime] = None
    is_shared: bool
    share_uuid: Optional[str]
    share_language: Optional[str] = None
    source: Optional[str] = None
    description: Optional[str] = None
    description_enlarged: Optional[bool] = False
    parent_id: Optional[int] = None
    has_children: bool = False
    tags: List[MediaTagResponse] = []
    
    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="wrap")
    @classmethod
    def populate_tag_implications(cls, data: Any, handler: Any) -> "MediaResponse":
        instance = handler(data)
        if not isinstance(data, dict) and hasattr(data, "media_tag_links"):
            try:
                links = getattr(data, "media_tag_links", None) or []
            except Exception:
                links = []
            if links and instance.tags:
                id_to_name: dict[int, str] = {t.id: t.name for t in instance.tags}
                missing_ids: set[int] = set()
                for link in links:
                    if link.implied and isinstance(link.implied_by, list):
                        for grp in link.implied_by:
                            if isinstance(grp, list):
                                for item in grp:
                                    if isinstance(item, int) and not isinstance(item, bool) and item not in id_to_name:
                                        missing_ids.add(item)

                if missing_ids:
                    try:
                        from sqlalchemy.orm import object_session
                        from .models import Tag
                        sess = object_session(data)
                        if sess is not None:
                            for tid, tname in sess.query(Tag.id, Tag.name).filter(Tag.id.in_(missing_ids)).all():
                                id_to_name[tid] = tname
                        else:
                            from .database import SessionLocal
                            tmp_db = SessionLocal()
                            try:
                                for tid, tname in tmp_db.query(Tag.id, Tag.name).filter(Tag.id.in_(missing_ids)).all():
                                    id_to_name[tid] = tname
                            finally:
                                tmp_db.close()
                    except Exception:
                        pass

                links_by_tag_id = {link.tag_id: link for link in links}
                for tag_resp in instance.tags:
                    link = links_by_tag_id.get(tag_resp.id)
                    if link is not None:
                        tag_resp.implied = bool(link.implied)
                        if link.implied and isinstance(link.implied_by, list):
                            resolved_groups: list[list[str]] = []
                            for grp in link.implied_by:
                                if not isinstance(grp, list):
                                    continue
                                names_in_grp: list[str] = []
                                for item in grp:
                                    if isinstance(item, int) and not isinstance(item, bool):
                                        tname = id_to_name.get(item)
                                        if tname:
                                            names_in_grp.append(tname)
                                    elif isinstance(item, str) and item.strip():
                                        names_in_grp.append(item.strip())
                                cleaned = sorted(set(names_in_grp))
                                if cleaned and cleaned not in resolved_groups:
                                    resolved_groups.append(cleaned)
                            tag_resp.implied_by = resolved_groups
                        else:
                            tag_resp.implied_by = []
        return instance

    @model_validator(mode="after")
    def ensure_custom_date(self) -> "MediaResponse":
        if self.custom_date is None and self.uploaded_at is not None:
            self.custom_date = self.uploaded_at
        return self

class MediaCreatedResponse(MediaResponse):
    """Response for endpoints that create a post directly (no upload queue to review)."""
    near_duplicates: List[Dict[str, Any]] = []

class MediaDetailResponse(MediaResponse):
    @computed_field
    @property
    def description_html(self) -> Optional[str]:
        if not self.description:
            return None
        try:
            from .utils.markdown import render_description_markdown
            return render_description_markdown(self.description)
        except Exception as e:
            import html as html_lib
            import logging
            logging.getLogger(__name__).error(f"Error rendering media description: {e}")
            return f'<p class="mb-3 text-xs last:mb-0 leading-relaxed">{html_lib.escape(self.description)}</p>'

class SharedTagResponse(TagBase):
    model_config = ConfigDict(from_attributes=True)

class SharedMediaResponse(MediaBase):
    filename: str
    file_type: FileTypeEnum
    mime_type: Optional[str]
    transcoded_path: Optional[str] = None
    file_size: int
    width: Optional[int]
    height: Optional[int]
    duration: Optional[float]
    uploaded_at: datetime
    custom_date: Optional[datetime] = None
    is_shared: bool
    share_uuid: Optional[str]
    share_language: Optional[str] = None
    share_ai_metadata: bool
    hash: str
    tags: List[SharedTagResponse] = []
    
    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def ensure_custom_date(self) -> "SharedMediaResponse":
        if self.custom_date is None and self.uploaded_at is not None:
            self.custom_date = self.uploaded_at
        return self

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
    auto_apply_ai_tags: Optional[bool] = None
    custom_background: Optional[CustomBackgroundSettings] = None
    similarity_weights: Optional[SimilarityWeights] = None
    stripped_cache_max_mb: Optional[int] = None
    booru_proxy_url: Optional[str] = None
    blur_explicit_thumbnails: Optional[bool] = None

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
    thumbnail_ratings: List[str] = []
    rating: RatingEnum = RatingEnum.safe
    media_count: int = 0
    
    model_config = ConfigDict(from_attributes=True)

class AlbumTreeNode(AlbumBase):
    id: int
    parent_id: Optional[int] = None
    depth: int = 0
    media_count: int = 0
    direct_media_count: int = 0
    children_count: int = 0
    rating: RatingEnum = RatingEnum.safe

    model_config = ConfigDict(from_attributes=True)

class AlbumHierarchyResponse(BaseModel):
    items: List[AlbumTreeNode]

class AlbumStatsResponse(BaseModel):
    total_albums: int
    root_albums: int
    total_media_in_albums: int

class AlbumAutocompleteItem(BaseModel):
    id: int
    name: str
    parent_path: Optional[str] = None
    media_count: int = 0
    rating: RatingEnum = RatingEnum.safe

class MediaIds(BaseModel):
    media_ids: List[int]

class AlbumReorderRequest(BaseModel):
    album_ids: List[int]

class MediaReorderRequest(BaseModel):
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
    implied_by: Dict[str, List[List[str]]] = Field(default_factory=dict)

class BatchResolveCombinedResponse(BaseModel):
    results: Dict[str, BatchResolveCombinedResultItem]
    alias_resolutions: Dict[str, str] = {}

class BulkTagUpdateItem(BaseModel):
    id: int
    tags: List[str]
    implied_tags: Optional[Dict[str, List[List[str]]]] = None

class BulkTagUpdateRequest(BaseModel):
    items: List[BulkTagUpdateItem]

class BulkTagUpdateResponse(BaseModel):
    status: str = "success"
    updated_count: int
    updated_media_ids: List[int]

class BulkMediaRatingItem(BaseModel):
    id: int
    rating: RatingEnum

class BulkMediaRatingUpdateRequest(BaseModel):
    items: List[BulkMediaRatingItem]

class BulkMediaRatingUpdateResponse(BaseModel):
    status: str = "success"
    updated_count: int
    updated_media_ids: List[int]

class ProposedTag(BaseModel):
    name: str
    category: TagCategoryEnum = TagCategoryEnum.general
    rating: TagRatingValue = "none"
    is_new: bool = False
    source: Optional[str] = "user"
    user_assigned: Optional[bool] = False
    implied: bool = False
    implied_by: List[List[str]] = Field(default_factory=list)

    @field_validator("rating", mode="before")
    @classmethod
    def normalize_rating(cls, v: Any) -> str:
        if v is None:
            return "none"
        if hasattr(v, "value"):
            return v.value
        s = str(v).strip().lower()
        return s if s in ("safe", "questionable", "explicit", "none") else "none"

class UploadSessionItemUpdate(BaseModel):
    rating: Optional[RatingEnum] = None
    tags: Optional[List[ProposedTag]] = None
    source: Optional[str] = None
    description: Optional[str] = None
    album_ids: Optional[List[int]] = None
    suggested_album_path: Optional[str] = None
    custom_date: Optional[str] = None
    parent_media_id: Optional[int] = None
    parent_item_id: Optional[str] = None
    child_media_ids: Optional[List[int]] = None

class UploadSessionAddUntrackedRequest(BaseModel):
    file_path: str
    relative_path: Optional[str] = None
    base_rating: Optional[str] = None
    base_source: Optional[str] = None
    base_tags: Optional[str] = None
    base_album_ids: Optional[str] = None
    category_hints: Optional[str] = None
    user_assigned_tags: Optional[str] = None
    base_description: Optional[str] = None
    client_date: Optional[str] = None
    booru_date: Optional[str] = None
    custom_date: Optional[str] = None

class AlbumPathSegment(BaseModel):
    name: str
    existing_id: Optional[int] = None
    depth: int = 0

class UploadSessionItem(BaseModel):
    item_id: str
    filename: str
    source_path: Optional[str] = None
    is_untracked: bool = False
    relative_path: Optional[str] = None
    file_size: int = 0
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[float] = None
    file_type: Optional[FileTypeEnum] = None
    mime_type: Optional[str] = None
    hash: Optional[str] = None
    phash: Optional[str] = None
    parent_media_id: Optional[int] = None
    parent_item_id: Optional[str] = None
    child_media_ids: List[int] = []
    rating: RatingEnum = RatingEnum.safe
    source: Optional[str] = None
    description: Optional[str] = None
    tags: List[ProposedTag] = []
    album_ids: List[int] = []
    suggested_album_path: Optional[str] = None
    suggested_album_segments: Optional[List[AlbumPathSegment]] = None
    folder_album_removed: Optional[bool] = False
    folder_album_custom_path: Optional[str] = None
    is_duplicate: bool = False
    duplicate_of: Optional[str] = None
    custom_date: Optional[str] = None
    custom_date_origin: Optional[str] = None
    custom_date_auto: Optional[str] = None
    custom_date_auto_origin: Optional[str] = None

class PendingTagEntity(BaseModel):
    name: str
    category: TagCategoryEnum = TagCategoryEnum.general
    rating: TagRatingValue = "none"
    used_by: List[str] = []
    merge_into: Optional[str] = None
    user_assigned: bool = False

class PendingAlbumEntity(BaseModel):
    path: str
    name: Optional[str] = None
    parent_path: Optional[str] = None
    depth: int = 0
    existing_id: Optional[int] = None
    used_by: List[str] = []
    item_count: int = 0
    single_item_warning: bool = False

class PendingEntitiesResponse(BaseModel):
    pending_tags: List[PendingTagEntity] = []
    pending_albums: List[PendingAlbumEntity] = []

class PendingTagUpdate(BaseModel):
    new_name: Optional[str] = None
    category: Optional[TagCategoryEnum] = None
    rating: Optional[TagRatingValue] = None
    merge_into: Optional[str] = None
    remove: Optional[bool] = False

class PendingAlbumUpdate(BaseModel):
    path: str
    new_name: Optional[str] = None
    merge_into_id: Optional[int] = None
    remove: Optional[bool] = False
    promote_to_parent: Optional[bool] = False

class FolderMappingRequest(BaseModel):
    enabled: bool = True
    root_mode: str = "use_root"

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
