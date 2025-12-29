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

blombooru_media_tags = Table(
    'blombooru_media_tags',
    Base.metadata,
    Column('media_id', Integer, ForeignKey('blombooru_media.id', ondelete='CASCADE'), primary_key=True),
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
    duration = Column(Float, nullable=True)
    rating = Column(Enum(RatingEnum), default=RatingEnum.safe, index=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    is_shared = Column(Boolean, default=False, index=True)
    share_uuid = Column(String(36), unique=True, nullable=True, index=True)
    share_ai_metadata = Column(Boolean, default=False)
    source = Column(String(500), nullable=True)
    parent_id = Column(Integer, ForeignKey('blombooru_media.id', ondelete='SET NULL'), nullable=True, index=True)
    
    tags = relationship('Tag', secondary=blombooru_media_tags, back_populates='media')
    children = relationship('Media', backref='parent', remote_side=[id])

    @property
    def has_children(self) -> bool:
        from .database import SessionLocal
        db = SessionLocal()
        try:
            return db.query(Media).filter(Media.parent_id == self.id).first() is not None
        finally:
            db.close()

class Tag(Base):
    __tablename__ = 'blombooru_tags'
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    category = Column(Enum(TagCategoryEnum), default=TagCategoryEnum.general, index=True)
    post_count = Column(Integer, default=0, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    media = relationship('Media', secondary=blombooru_media_tags, back_populates='tags')
    aliases = relationship('TagAlias', foreign_keys='TagAlias.target_tag_id', back_populates='target_tag')

class TagAlias(Base):
    __tablename__ = 'blombooru_tag_aliases'
    
    id = Column(Integer, primary_key=True, index=True)
    alias_name = Column(String(255), unique=True, nullable=False, index=True)
    target_tag_id = Column(Integer, ForeignKey('blombooru_tags.id', ondelete='CASCADE'), nullable=False)
    
    target_tag = relationship('Tag', foreign_keys=[target_tag_id], back_populates='aliases')

# Album-Media association table
blombooru_album_media = Table(
    'blombooru_album_media',
    Base.metadata,
    Column('album_id', Integer, ForeignKey('blombooru_albums.id', ondelete='CASCADE'), primary_key=True),
    Column('media_id', Integer, ForeignKey('blombooru_media.id', ondelete='CASCADE'), primary_key=True),
    Column('added_at', DateTime(timezone=True), server_default=func.now(), index=True)
)

# Album hierarchy (self-referential many-to-many for parent-child relationships)
blombooru_album_hierarchy = Table(
    'blombooru_album_hierarchy',
    Base.metadata,
    Column('parent_album_id', Integer, ForeignKey('blombooru_albums.id', ondelete='CASCADE'), primary_key=True),
    Column('child_album_id', Integer, ForeignKey('blombooru_albums.id', ondelete='CASCADE'), primary_key=True)
)

class Album(Base):
    __tablename__ = 'blombooru_albums'
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_modified = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # Relationships
    media = relationship('Media', secondary=blombooru_album_media, back_populates='albums')
    
    # Self-referential relationships for album hierarchy
    children = relationship(
        'Album',
        secondary=blombooru_album_hierarchy,
        primaryjoin=id == blombooru_album_hierarchy.c.parent_album_id,
        secondaryjoin=id == blombooru_album_hierarchy.c.child_album_id,
        backref='parents'
    )

# Update Media model to include albums relationship
Media.albums = relationship('Album', secondary=blombooru_album_media, back_populates='media')
