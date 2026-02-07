from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc
from dataclasses import dataclass
from datetime import datetime

@dataclass
class SyncResult:
    """Result of a tag synchronization operation"""
    tags_imported: int = 0
    tags_exported: int = 0
    aliases_imported: int = 0
    aliases_exported: int = 0
    conflicts_resolved: int = 0
    errors: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []

class SharedTagService:
    """Service for managing shared tag database interactions"""
    def __init__(self, local_db: Session, shared_db: Optional[Session] = None):
        self.local_db = local_db
        self.shared_db = shared_db
    
    @property
    def is_available(self) -> bool:
        """Check if shared database is available"""
        return self.shared_db is not None
    
    def get_tag(self, name: str):
        """
        Get a tag by name, checking local DB first then shared.
        Local tag takes precedence for category if both exist.
        """
        from ..models import Tag
        
        # Always check local first
        local_tag = self.local_db.query(Tag).filter(Tag.name == name.lower()).first()
        if local_tag:
            return local_tag
        
        # Check shared if available
        if self.is_available:
            from ..shared_tag_models import SharedTag
            shared_tag = self.shared_db.query(SharedTag).filter(
                SharedTag.name == name.lower()
            ).first()
            
            if shared_tag:
                # Import to local DB on first access
                local_tag = self._import_shared_tag(shared_tag)
                return local_tag
        
        return None
    
    def get_merged_tags(
        self, 
        search: Optional[str] = None, 
        limit: int = 100,
        category = None
    ) -> List:
        """
        Get tags from both local and shared databases, merged.
        Local tags take precedence.
        """
        from ..models import Tag
        
        # Query local
        local_query = self.local_db.query(Tag)
        if search:
            local_query = local_query.filter(Tag.name.ilike(f"%{search}%"))
        if category:
            local_query = local_query.filter(Tag.category == category)
        local_query = local_query.order_by(desc(Tag.post_count))
        local_tags = local_query.limit(limit).all()
        
        local_names = {t.name for t in local_tags}
        
        # If shared is available, get additional tags
        if self.is_available and len(local_tags) < limit:
            from ..shared_tag_models import SharedTag
            
            remaining = limit - len(local_tags)
            shared_query = self.shared_db.query(SharedTag).filter(
                ~SharedTag.name.in_(local_names) if local_names else True
            )
            
            if search:
                shared_query = shared_query.filter(SharedTag.name.ilike(f"%{search}%"))
            if category:
                shared_query = shared_query.filter(SharedTag.category == category)
            
            shared_tags = shared_query.limit(remaining).all()
            
            # Convert shared tags to local format
            for st in shared_tags:
                local_tags.append(self._shared_to_local_tag_view(st))
        
        return local_tags
    
    def autocomplete_merged(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get autocomplete suggestions from both databases"""
        from ..models import Tag, TagAlias
        from sqlalchemy import case
        
        results = []
        seen_names = set()
        
        # Check local alias first
        alias = self.local_db.query(TagAlias).filter(
            TagAlias.alias_name.ilike(query)
        ).first()
        
        if alias:
            target_tag = self.local_db.query(Tag).filter(Tag.id == alias.target_tag_id).first()
            if target_tag:
                results.append({
                    "name": target_tag.name,
                    "category": target_tag.category,
                    "count": target_tag.post_count,
                    "is_alias": True,
                    "alias_name": query.lower(),
                    "source": "local"
                })
                seen_names.add(target_tag.name)
        
        # Query local tags
        priority = case(
            (Tag.name.ilike(f"{query}%"), 1),
            else_=2
        )
        
        local_tags = self.local_db.query(Tag).filter(
            Tag.name.ilike(f"%{query}%")
        ).order_by(priority, desc(Tag.post_count)).limit(limit).all()
        
        for tag in local_tags:
            if tag.name not in seen_names:
                results.append({
                    "name": tag.name, 
                    "category": tag.category, 
                    "count": tag.post_count,
                    "source": "local"
                })
                seen_names.add(tag.name)
        
        # Add from shared if available and room left
        if self.is_available and len(results) < limit:
            from ..shared_tag_models import SharedTag, SharedTagAlias
            
            remaining = limit - len(results)
            
            # Check shared aliases
            if query.lower() not in [r.get("alias_name", "") for r in results]:
                shared_alias = self.shared_db.query(SharedTagAlias).filter(
                    SharedTagAlias.alias_name.ilike(query)
                ).first()
                
                if shared_alias:
                    shared_target = self.shared_db.query(SharedTag).filter(
                        SharedTag.id == shared_alias.target_tag_id
                    ).first()
                    if shared_target and shared_target.name not in seen_names:
                        results.append({
                            "name": shared_target.name,
                            "category": shared_target.category.value if hasattr(shared_target.category, 'value') else shared_target.category,
                            "count": 0,
                            "is_alias": True,
                            "alias_name": query.lower(),
                            "source": "shared"
                        })
                        seen_names.add(shared_target.name)
            
            shared_tags = self.shared_db.query(SharedTag).filter(
                SharedTag.name.ilike(f"%{query}%"),
                ~SharedTag.name.in_(seen_names) if seen_names else True
            ).limit(remaining).all()
            
            for st in shared_tags:
                if st.name not in seen_names:
                    results.append({
                        "name": st.name,
                        "category": st.category.value if hasattr(st.category, 'value') else st.category,
                        "count": 0,
                        "source": "shared"
                    })
                    seen_names.add(st.name)
        
        return results[:limit]
    
    def sync_tag_to_shared(self, tag) -> bool:
        """Push a local tag to the shared database"""
        if not self.is_available:
            return False
        
        from ..shared_tag_models import SharedTag
        
        try:
            existing = self.shared_db.query(SharedTag).filter(
                SharedTag.name == tag.name
            ).first()
            
            if existing:
                # Don't update category - local just reports existence
                return True
            else:
                shared_tag = SharedTag(
                    name=tag.name,
                    category=tag.category
                )
                self.shared_db.add(shared_tag)
                self.shared_db.commit()
                return True
                
        except Exception as e:
            print(f"Error syncing tag to shared DB: {e}")
            self.shared_db.rollback()
            return False
    
    def sync_from_shared(self) -> SyncResult:
        """Pull new tags from shared database to local"""
        result = SyncResult()
        
        if not self.is_available:
            result.errors.append("Shared database not available")
            return result
        
        from ..models import Tag, TagAlias
        from ..shared_tag_models import SharedTag, SharedTagAlias
        
        try:
            # Get all shared tags
            shared_tags = self.shared_db.query(SharedTag).all()
            local_tag_names = {t.name for t in self.local_db.query(Tag.name).all()}
            
            for st in shared_tags:
                if st.name not in local_tag_names:
                    # Import new tag
                    new_tag = Tag(
                        name=st.name,
                        category=st.category,
                        post_count=0
                    )
                    self.local_db.add(new_tag)
                    result.tags_imported += 1
                else:
                    # Tag exists locally - local category takes precedence
                    result.conflicts_resolved += 1
            
            # Import aliases
            shared_aliases = self.shared_db.query(SharedTagAlias).all()
            local_alias_names = {a.alias_name for a in self.local_db.query(TagAlias.alias_name).all()}
            
            for sa in shared_aliases:
                if sa.alias_name not in local_alias_names:
                    # Find target tag in local DB
                    shared_target = self.shared_db.query(SharedTag).filter(
                        SharedTag.id == sa.target_tag_id
                    ).first()
                    
                    if shared_target:
                        local_target = self.local_db.query(Tag).filter(
                            Tag.name == shared_target.name
                        ).first()
                        
                        if local_target:
                            new_alias = TagAlias(
                                alias_name=sa.alias_name,
                                target_tag_id=local_target.id
                            )
                            self.local_db.add(new_alias)
                            result.aliases_imported += 1
            
            self.local_db.commit()
            
        except Exception as e:
            result.errors.append(str(e))
            self.local_db.rollback()
        
        return result
    
    def sync_to_shared(self) -> SyncResult:
        """Push all local tags to the shared database"""
        result = SyncResult()
        
        if not self.is_available:
            result.errors.append("Shared database not available")
            return result
        
        from ..models import Tag, TagAlias
        from ..shared_tag_models import SharedTag, SharedTagAlias
        
        try:
            local_tags = self.local_db.query(Tag).all()
            shared_tag_names = {t.name for t in self.shared_db.query(SharedTag.name).all()}
            
            for lt in local_tags:
                if lt.name not in shared_tag_names:
                    new_shared = SharedTag(
                        name=lt.name,
                        category=lt.category
                    )
                    self.shared_db.add(new_shared)
                    result.tags_exported += 1
            
            self.shared_db.commit()
            
            # Refresh shared tag mapping for aliases
            shared_tag_map = {t.name: t.id for t in self.shared_db.query(SharedTag).all()}
            shared_alias_names = {a.alias_name for a in self.shared_db.query(SharedTagAlias.alias_name).all()}
            
            local_aliases = self.local_db.query(TagAlias).all()
            for la in local_aliases:
                if la.alias_name not in shared_alias_names:
                    local_target = self.local_db.query(Tag).filter(
                        Tag.id == la.target_tag_id
                    ).first()
                    
                    if local_target and local_target.name in shared_tag_map:
                        new_alias = SharedTagAlias(
                            alias_name=la.alias_name,
                            target_tag_id=shared_tag_map[local_target.name]
                        )
                        self.shared_db.add(new_alias)
                        result.aliases_exported += 1
            
            self.shared_db.commit()
            
        except Exception as e:
            result.errors.append(str(e))
            self.shared_db.rollback()
        
        return result
    
    def full_sync(self) -> SyncResult:
        """Perform bidirectional sync: import from shared, then export to shared"""
        import_result = self.sync_from_shared()
        export_result = self.sync_to_shared()
        
        return SyncResult(
            tags_imported=import_result.tags_imported,
            tags_exported=export_result.tags_exported,
            aliases_imported=import_result.aliases_imported,
            aliases_exported=export_result.aliases_exported,
            conflicts_resolved=import_result.conflicts_resolved,
            errors=import_result.errors + export_result.errors
        )
    
    def _import_shared_tag(self, shared_tag):
        """Import a shared tag to local database"""
        from ..models import Tag
        
        local_tag = Tag(
            name=shared_tag.name,
            category=shared_tag.category,
            post_count=0
        )
        self.local_db.add(local_tag)
        self.local_db.commit()
        self.local_db.refresh(local_tag)
        return local_tag
    
    def _shared_to_local_tag_view(self, shared_tag):
        """Create a read-only view of a shared tag in local format"""
        # Create a simple namespace object that looks like a local tag
        class TagView:
            def __init__(self, st):
                self.id = None  # Shared tags don't have local IDs
                self.name = st.name
                self.category = st.category
                self.post_count = 0
                self.created_at = st.created_at
                self._is_shared = True
        
        return TagView(shared_tag)

def get_shared_tag_service(local_db: Session, shared_db: Optional[Session] = None) -> SharedTagService:
    """Factory function to create SharedTagService instance"""
    return SharedTagService(local_db, shared_db)
