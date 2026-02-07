from sqlalchemy import Column, Integer, String, DateTime, Enum, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

SharedBase = declarative_base()

class TagCategoryEnum(str, enum.Enum):
    general = "general"
    artist = "artist"
    character = "character"
    copyright = "copyright"
    meta = "meta"

class SharedTag(SharedBase):
    """Tag model for the shared tag database"""
    __tablename__ = 'shared_tags'
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    category = Column(Enum(TagCategoryEnum), default=TagCategoryEnum.general, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    aliases = relationship('SharedTagAlias', back_populates='target_tag', cascade="all, delete-orphan")

class SharedTagAlias(SharedBase):
    """Tag alias model for the shared tag database"""
    __tablename__ = 'shared_tag_aliases'
    
    id = Column(Integer, primary_key=True, index=True)
    alias_name = Column(String(255), unique=True, nullable=False, index=True)
    target_tag_id = Column(Integer, ForeignKey('shared_tags.id'), nullable=False, index=True)
    
    target_tag = relationship('SharedTag', back_populates='aliases')
