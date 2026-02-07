from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

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
        pool_size=10,
        max_overflow=20,
        pool_recycle=3600,
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
        print(f"Shared tag database connected: {settings.SHARED_TAG_DB_HOST}:{settings.SHARED_TAG_DB_PORT}/{settings.SHARED_TAG_DB_NAME}")
        return shared_engine
        
    except Exception as e:
        _shared_db_available = False
        _shared_db_error = str(e)
        print(f"Warning: Could not connect to shared tag database: {e}")
        print("Continuing with local tags only...")
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
        except:
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
    except Exception as e:
        print(f"Error with shared DB session: {e}")
        yield None
    finally:
        try:
            db.close()
        except:
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
        print("Shared tag database schema initialized")
    except Exception as e:
        print(f"Warning: Could not initialize shared tag database schema: {e}")

def check_and_migrate_schema(engine):
    """Run schema migrations"""
    from sqlalchemy import text, inspect
    
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    
    if 'blombooru_media' not in tables:
        return
    
    migrations = [
        migrate_add_parent_id,
        migrate_add_share_language,
    ]
    
    for migration in migrations:
        migration(engine, inspector)


def migrate_add_parent_id(engine, inspector):
    """Add parent_id column and index to media table"""
    from sqlalchemy import text
    
    columns = [c['name'] for c in inspector.get_columns('blombooru_media')]
    
    if 'parent_id' in columns:
        return
    
    print("Adding parent_id column to blombooru_media...")
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
    
    print("Adding share_language column to blombooru_media...")
    
    with engine.connect() as conn:
        conn.execute(text(
            "ALTER TABLE blombooru_media ADD COLUMN share_language VARCHAR(10)"
        ))
        conn.commit()
