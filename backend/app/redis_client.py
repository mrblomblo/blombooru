import redis
from .config import settings
from typing import Optional, Any
import json

class RedisClient:
    def __init__(self):
        self._client: Optional[redis.Redis] = None
        self._enabled = settings.REDIS_ENABLED

    @property
    def client(self) -> Optional[redis.Redis]:
        if not self._enabled:
            return None
        
        if self._client is None:
            self.connect()
            
        return self._client

    def connect(self):
        """Initialize Redis connection"""
        if not self._enabled:
            return

        try:
            self._client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                password=settings.REDIS_PASSWORD,
                decode_responses=True,
                socket_connect_timeout=2
            )
            # Test connection
            self._client.ping()
            print(f"Connected to Redis at {settings.REDIS_HOST}:{settings.REDIS_PORT}")
        except Exception as e:
            print(f"Failed to connect to Redis: {e}")
            self._client = None
            # Don't disable globally, might be a temporary connection issue

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        c = self.client
        if not c:
            return None
        
        try:
            data = c.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            print(f"Redis get error: {e}")
        return None

    def set(self, key: str, value: Any, expire: int = 3600):
        """Set value in cache"""
        c = self.client
        if not c:
            return
        
        try:
            c.set(key, json.dumps(value), ex=expire)
        except Exception as e:
            print(f"Redis set error: {e}")

    def delete(self, key: str):
        """Delete key from cache"""
        c = self.client
        if not c:
            return
        
        try:
            c.delete(key)
        except Exception as e:
            print(f"Redis delete error: {e}")

    def flush_all(self):
        """Clear all cache"""
        c = self.client
        if not c:
            return
        
        try:
            c.flushdb()
            print("Redis cache flushed")
        except Exception as e:
            print(f"Redis flush error: {e}")

    def is_available(self) -> bool:
        """Check if Redis is enabled and reachable"""
        if not self._enabled:
            return False
            
        try:
            if self._client is None:
                self.connect()
            return self._client.ping() if self._client else False
        except:
            return False

# Global instance
redis_cache = RedisClient()
