from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .utils.logger import logger

engine = None
SessionLocal = None
Base = declarative_base()

shared_engine = None
SharedSessionLocal = None
_shared_db_available = False
_shared_db_error = None

def init_engine():
    """Initialize database engine"""
    global engine, SessionLocal
    from .config import settings
    
    if settings.IS_FIRST_RUN:
        return None
    
    engine = create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_size=20,
        max_overflow=200,
        pool_recycle=3600,
        pool_timeout=10,
        connect_args={
            "connect_timeout": 10,
            "options": "-c statement_timeout=300000"
        }
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return engine

def init_shared_engine():
    """Initialize shared tag database engine if enabled"""
    global shared_engine, SharedSessionLocal, _shared_db_available, _shared_db_error
    from .config import settings
    
    if not settings.SHARED_TAGS_ENABLED:
        _shared_db_available = False
        return None
    
    try:
        shared_engine = create_engine(
            settings.SHARED_TAG_DATABASE_URL,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            pool_recycle=3600,
            connect_args={
                "connect_timeout": 5,
                "options": "-c statement_timeout=30000"
            }
        )
        SharedSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=shared_engine)
        
        # Test connection
        with shared_engine.connect() as conn:
            from sqlalchemy import text
            conn.execute(text("SELECT 1"))
        
        _shared_db_available = True
        _shared_db_error = None
        logger.info(f"Shared tag database connected: {settings.SHARED_TAG_DB_HOST}:{settings.SHARED_TAG_DB_PORT}/{settings.SHARED_TAG_DB_NAME}")
        return shared_engine
        
    except Exception as e:
        _shared_db_available = False
        _shared_db_error = str(e)
        logger.warning(f"Warning: Could not connect to shared tag database: {e}")
        logger.warning("Continuing with local tags only...")
        return None

def is_shared_db_available() -> bool:
    """Check if shared database is currently available"""
    return _shared_db_available

def get_shared_db_error() -> str:
    """Get the last error message from shared DB connection attempt"""
    return _shared_db_error

def reconnect_shared_db():
    """Attempt to reconnect to the shared database"""
    global shared_engine, SharedSessionLocal, _shared_db_available
    
    # Dispose old engine if exists
    if shared_engine:
        try:
            shared_engine.dispose()
        except Exception:
            pass
    
    shared_engine = None
    SharedSessionLocal = None
    _shared_db_available = False
    
    return init_shared_engine()

def get_db():
    """Get database session"""
    global SessionLocal
    
    if SessionLocal is None:
        init_engine()
    
    if SessionLocal is None:
        raise RuntimeError("Database not initialized. Please complete onboarding first.")
    
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_shared_db():
    """Get shared database session (yields None if not available)"""
    global SharedSessionLocal, _shared_db_available
    
    if not _shared_db_available or SharedSessionLocal is None:
        yield None
        return
    
    db = SharedSessionLocal()
    try:
        yield db
    finally:
        try:
            db.close()
        except Exception:
            pass

def init_db():
    """Initialize database schema"""
    global engine
    
    if engine is None:
        init_engine()
    
    from . import models
    
    Base.metadata.create_all(bind=engine)
    
    check_and_migrate_schema(engine)
    init_shared_db()

def init_shared_db():
    """Initialize shared tag database schema if enabled"""
    global shared_engine, _shared_db_available
    
    from .config import settings
    
    if not settings.SHARED_TAGS_ENABLED:
        return
    
    if shared_engine is None:
        init_shared_engine()
    
    if shared_engine is None or not _shared_db_available:
        return
    
    try:
        from .shared_tag_models import SharedBase
        SharedBase.metadata.create_all(bind=shared_engine)
        logger.info("Shared tag database schema initialized")
    except Exception as e:
        logger.warning(f"Warning: Could not initialize shared tag database schema: {e}")

def check_and_migrate_schema(engine):
    """Run schema migrations"""
    from sqlalchemy import inspect, text
    
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    
    if 'blombooru_media' not in tables:
        return
    
    migrations = [
        migrate_add_parent_id,
        migrate_add_share_language,
        migrate_add_description,
        migrate_add_implication_patterns,
        migrate_implication_patterns_to_jsonb,
        migrate_file_size_to_bigint,
        migrate_remove_duplicate_tag_aliases,
        migrate_add_api_key_permission,
        migrate_add_transcoded_path,
        migrate_add_album_indexes,
        migrate_add_album_cached_columns,
    ]
    
    for migration in migrations:
        migration(engine, inspector)

def migrate_remove_duplicate_tag_aliases(engine, inspector):
    """Remove tag aliases whose alias_name already exists as a tag in blombooru_tags."""
    from sqlalchemy import text

    tables = inspector.get_table_names()
    if 'blombooru_tags' not in tables or 'blombooru_tag_aliases' not in tables:
        return

    with engine.connect() as conn:
        result = conn.execute(text(
            "DELETE FROM blombooru_tag_aliases WHERE alias_name IN (SELECT name FROM blombooru_tags)"
        ))
        if result.rowcount and result.rowcount > 0:
            logger.info(f"Removed {result.rowcount} duplicate tag alias(es) that also existed as tags.")
        conn.commit()

def migrate_add_parent_id(engine, inspector):
    """Add parent_id column and index to media table"""
    from sqlalchemy import text
    
    columns = [c['name'] for c in inspector.get_columns('blombooru_media')]
    
    if 'parent_id' in columns:
        return
    
    logger.info("Adding parent_id column to blombooru_media...")
    is_sqlite = engine.dialect.name == 'sqlite'
    
    with engine.connect() as conn:
        if is_sqlite:
            conn.execute(text(
                "ALTER TABLE blombooru_media ADD COLUMN parent_id INTEGER"
            ))
        else:
            conn.execute(text(
                "ALTER TABLE blombooru_media ADD COLUMN parent_id INTEGER "
                "REFERENCES blombooru_media(id) ON DELETE SET NULL"
            ))
        
        conn.execute(text(
            "CREATE INDEX ix_blombooru_media_parent_id ON blombooru_media(parent_id)"
        ))
        conn.commit()

def migrate_add_share_language(engine, inspector):
    """Add share_language column to media table"""
    from sqlalchemy import text
    
    columns = [c['name'] for c in inspector.get_columns('blombooru_media')]
    
    if 'share_language' in columns:
        return
    
    logger.info("Adding share_language column to blombooru_media...")
    
    with engine.connect() as conn:
        conn.execute(text(
            "ALTER TABLE blombooru_media ADD COLUMN share_language VARCHAR(10)"
        ))
        conn.commit()

def migrate_add_description(engine, inspector):
    """Add description column to media table"""
    from sqlalchemy import text
    
    columns = [c['name'] for c in inspector.get_columns('blombooru_media')]
    
    if 'description' in columns:
        return
    
    logger.info("Adding description column to blombooru_media...")
    
    with engine.connect() as conn:
        conn.execute(text(
            "ALTER TABLE blombooru_media ADD COLUMN description TEXT"
        ))
        conn.commit()

def migrate_add_implication_patterns(engine, inspector):
    """Add target_tag_patterns JSON column to blombooru_tag_implications table"""
    from sqlalchemy import text

    tables = inspector.get_table_names()
    if 'blombooru_tag_implications' not in tables:
        return

    columns = [c['name'] for c in inspector.get_columns('blombooru_tag_implications')]
    if 'target_tag_patterns' in columns:
        return

    logger.info("Adding target_tag_patterns column to blombooru_tag_implications...")

    is_sqlite = engine.dialect.name == 'sqlite'
    with engine.connect() as conn:
        if is_sqlite:
            conn.execute(text(
                "ALTER TABLE blombooru_tag_implications ADD COLUMN target_tag_patterns TEXT"
            ))
        else:
            conn.execute(text(
                "ALTER TABLE blombooru_tag_implications ADD COLUMN target_tag_patterns JSONB"
            ))
        conn.commit()

def migrate_implication_patterns_to_jsonb(engine, inspector):
    """Convert target_tag_patterns column from JSON to JSONB on PostgreSQL."""
    from sqlalchemy import text

    if engine.dialect.name == 'sqlite':
        return

    tables = inspector.get_table_names()
    if 'blombooru_tag_implications' not in tables:
        return

    columns = inspector.get_columns('blombooru_tag_implications')
    for col in columns:
        if col['name'] == 'target_tag_patterns':
            if 'JSONB' in str(col['type']).upper():
                return
            break
    else:
        return

    logger.info("Migrating target_tag_patterns column from JSON to JSONB...")
    with engine.connect() as conn:
        conn.execute(text(
            "ALTER TABLE blombooru_tag_implications "
            "ALTER COLUMN target_tag_patterns TYPE JSONB "
            "USING target_tag_patterns::jsonb"
        ))
        conn.commit()

def migrate_file_size_to_bigint(engine, inspector):
    """Widen file_size from INTEGER to BIGINT to support files larger than 2 GiB."""
    from sqlalchemy import text

    if engine.dialect.name == 'sqlite':
        return

    columns = inspector.get_columns('blombooru_media')
    for col in columns:
        if col['name'] == 'file_size':
            type_name = str(col['type']).upper()
            if 'BIGINT' in type_name:
                return
            break
    else:
        return

    logger.info("Migrating file_size column to BIGINT...")
    with engine.connect() as conn:
        conn.execute(text(
            "ALTER TABLE blombooru_media ALTER COLUMN file_size TYPE BIGINT"
        ))
        conn.commit()

def migrate_add_api_key_permission(engine, inspector):
    """Add permission column to blombooru_api_keys table with default 'admin' for existing keys"""
    from sqlalchemy import text
    
    tables = inspector.get_table_names()
    if 'blombooru_api_keys' not in tables:
        return
    
    columns = [c['name'] for c in inspector.get_columns('blombooru_api_keys')]
    if 'permission' in columns:
        return
    
    logger.info("Adding permission column to blombooru_api_keys...")
    with engine.connect() as conn:
        conn.execute(text(
            "ALTER TABLE blombooru_api_keys ADD COLUMN permission VARCHAR(32) DEFAULT 'admin' NOT NULL"
        ))
        conn.commit()

def migrate_add_transcoded_path(engine, inspector):
    """Add transcoded_path column to blombooru_media table"""
    from sqlalchemy import text
    
    columns = [c['name'] for c in inspector.get_columns('blombooru_media')]
    if 'transcoded_path' in columns:
        return
    
    logger.info("Adding transcoded_path column to blombooru_media...")
    with engine.connect() as conn:
        conn.execute(text(
            "ALTER TABLE blombooru_media ADD COLUMN transcoded_path VARCHAR(500)"
        ))
        conn.commit()

def migrate_add_album_indexes(engine, inspector):
    """Add indexes to blombooru_album_hierarchy(child_album_id) and blombooru_album_media(media_id)"""
    from sqlalchemy import text
    
    tables = inspector.get_table_names()
    if 'blombooru_album_hierarchy' in tables:
        indexes = [idx['name'] for idx in inspector.get_indexes('blombooru_album_hierarchy')]
        if 'ix_blombooru_album_hierarchy_child_album_id' not in indexes:
            logger.info("Adding index ix_blombooru_album_hierarchy_child_album_id...")
            with engine.connect() as conn:
                conn.execute(text(
                    "CREATE INDEX ix_blombooru_album_hierarchy_child_album_id ON blombooru_album_hierarchy(child_album_id)"
                ))
                conn.commit()

    if 'blombooru_album_media' in tables:
        indexes = [idx['name'] for idx in inspector.get_indexes('blombooru_album_media')]
        if 'ix_blombooru_album_media_media_id' not in indexes:
            logger.info("Adding index ix_blombooru_album_media_media_id...")
            with engine.connect() as conn:
                conn.execute(text(
                    "CREATE INDEX ix_blombooru_album_media_media_id ON blombooru_album_media(media_id)"
                ))
                conn.commit()

def migrate_add_album_cached_columns(engine, inspector):
    """Add cached_rating, cached_media_count, cached_direct_media_count to blombooru_albums and backfill."""
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker
    
    tables = inspector.get_table_names()
    if 'blombooru_albums' not in tables:
        return
        
    columns = [c['name'] for c in inspector.get_columns('blombooru_albums')]
    newly_added = False

    with engine.connect() as conn:
        if 'cached_rating' not in columns:
            logger.info("Adding cached_rating column to blombooru_albums...")
            if engine.dialect.name == 'postgresql':
                conn.execute(text("ALTER TABLE blombooru_albums ADD COLUMN cached_rating ratingenum DEFAULT 'safe'"))
            else:
                conn.execute(text("ALTER TABLE blombooru_albums ADD COLUMN cached_rating VARCHAR(20) DEFAULT 'safe'"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_blombooru_albums_cached_rating ON blombooru_albums(cached_rating)"))
            newly_added = True

        if 'cached_media_count' not in columns:
            logger.info("Adding cached_media_count column to blombooru_albums...")
            conn.execute(text("ALTER TABLE blombooru_albums ADD COLUMN cached_media_count INTEGER DEFAULT 0"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_blombooru_albums_cached_media_count ON blombooru_albums(cached_media_count)"))
            newly_added = True

        if 'cached_direct_media_count' not in columns:
            logger.info("Adding cached_direct_media_count column to blombooru_albums...")
            conn.execute(text("ALTER TABLE blombooru_albums ADD COLUMN cached_direct_media_count INTEGER DEFAULT 0"))
            newly_added = True

        conn.commit()

    logger.info("Synchronizing and ensuring cached metrics for blombooru_albums...")
    try:
        from .utils.album_utils import recalculate_all_album_metrics
        from .utils.cache import invalidate_album_cache
        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            recalculate_all_album_metrics(db)
        finally:
            db.close()
        invalidate_album_cache()
        logger.info("Album metrics synchronization completed successfully.")
    except Exception as e:
        logger.error(f"Error synchronizing album metrics during migration: {e}")
