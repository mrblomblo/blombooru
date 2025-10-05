from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, Table, Float, Enum, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base
import enum

class RatingEnum(str, enum.Enum):
    safe = "safe"
    questionable = "questionable"
    explicit = "explicit"

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

# Association Tables
blombooru_media_tags = Table(
    'blombooru_media_tags',
    Base.metadata,
    Column('media_id', Integer, ForeignKey('blombooru_media.id', ondelete='CASCADE'), primary_key=True),
    Column('tag_id', Integer, ForeignKey('blombooru_tags.id', ondelete='CASCADE'), primary_key=True)
)

blombooru_album_media = Table(
    'blombooru_album_media',
    Base.metadata,
    Column('album_id', Integer, ForeignKey('blombooru_albums.id', ondelete='CASCADE'), primary_key=True),
    Column('media_id', Integer, ForeignKey('blombooru_media.id', ondelete='CASCADE'), primary_key=True),
    Column('position', Integer, default=0)
)

blombooru_album_tags = Table(
    'blombooru_album_tags',
    Base.metadata,
    Column('album_id', Integer, ForeignKey('blombooru_albums.id', ondelete='CASCADE'), primary_key=True),
    Column('tag_id', Integer, ForeignKey('blombooru_tags.id', ondelete='CASCADE'), primary_key=True)
)

class User(Base):
    __tablename__ = 'blombooru_users'
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Media(Base):
    __tablename__ = 'blombooru_media'
    
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    path = Column(String(500), nullable=False, unique=True)
    thumbnail_path = Column(String(500))
    hash = Column(String(64), unique=True, index=True)
    file_type = Column(Enum(FileTypeEnum), nullable=False)
    mime_type = Column(String(100))
    file_size = Column(Integer)
    width = Column(Integer)
    height = Column(Integer)
    duration = Column(Float, nullable=True)  # For videos
    rating = Column(Enum(RatingEnum), default=RatingEnum.safe, index=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    is_shared = Column(Boolean, default=False, index=True)
    share_uuid = Column(String(36), unique=True, nullable=True, index=True)
    
    tags = relationship('Tag', secondary=blombooru_media_tags, back_populates='media')
    albums = relationship('Album', secondary=blombooru_album_media, back_populates='media')

class Tag(Base):
    __tablename__ = 'blombooru_tags'
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    category = Column(Enum(TagCategoryEnum), default=TagCategoryEnum.general, index=True)
    post_count = Column(Integer, default=0, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    media = relationship('Media', secondary=blombooru_media_tags, back_populates='tags')
    albums = relationship('Album', secondary=blombooru_album_tags, back_populates='tags')
    aliases = relationship('TagAlias', foreign_keys='TagAlias.target_tag_id', back_populates='target_tag')
    implications = relationship('TagImplication', foreign_keys='TagImplication.source_tag_id', back_populates='source_tag')

class Album(Base):
    __tablename__ = 'blombooru_albums'
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    rating = Column(Enum(RatingEnum), default=RatingEnum.safe)
    cover_media_id = Column(Integer, ForeignKey('blombooru_media.id'), nullable=True)
    is_system = Column(Boolean, default=False)
    is_shared = Column(Boolean, default=False, index=True)
    share_uuid = Column(String(36), unique=True, nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    media = relationship('Media', secondary=blombooru_album_media, back_populates='albums')
    tags = relationship('Tag', secondary=blombooru_album_tags, back_populates='albums')
    cover_media = relationship('Media', foreign_keys=[cover_media_id])

class TagAlias(Base):
    __tablename__ = 'blombooru_tag_aliases'
    
    id = Column(Integer, primary_key=True, index=True)
    alias_name = Column(String(255), unique=True, nullable=False, index=True)
    target_tag_id = Column(Integer, ForeignKey('blombooru_tags.id', ondelete='CASCADE'), nullable=False)
    
    target_tag = relationship('Tag', foreign_keys=[target_tag_id], back_populates='aliases')

class TagImplication(Base):
    __tablename__ = 'blombooru_tag_implications'
    
    id = Column(Integer, primary_key=True, index=True)
    source_tag_id = Column(Integer, ForeignKey('blombooru_tags.id', ondelete='CASCADE'), nullable=False)
    implied_tag_id = Column(Integer, ForeignKey('blombooru_tags.id', ondelete='CASCADE'), nullable=False)
    
    source_tag = relationship('Tag', foreign_keys=[source_tag_id], back_populates='implications')
    implied_tag = relationship('Tag', foreign_keys=[implied_tag_id])
