from functools import wraps
from typing import Optional, Callable
from fastapi import Request
from fastapi.encoders import jsonable_encoder
from ..redis_client import redis_cache
import hashlib
import json

def cache_response(expire: int = 3600, key_prefix: str = "cache"):
    """
    FastAPI route decorator to cache JSON responses in Redis.
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request: Optional[Request] = kwargs.get("request")
            if not request:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break
            
            if not request or not redis_cache._enabled:
                return await func(*args, **kwargs)
            
            # Generate cache key based on URL and query params
            url = str(request.url)
            key = f"{key_prefix}:{hashlib.md5(url.encode()).hexdigest()}"
            
            cached_data = redis_cache.get(key)
            if cached_data:
                return cached_data
            
            result = await func(*args, **kwargs)
            
            # Store in cache
            try:
                serializable_result = jsonable_encoder(result)
                if isinstance(serializable_result, (dict, list)):
                    redis_cache.set(key, serializable_result, expire=expire)
            except Exception as e:
                print(f"Error encoding result for cache: {e}")
                
            return result
        return wrapper
    return decorator

def invalidate_cache(*prefixes: str):
    """
    Invalidate all keys starting with the given prefixes.
    """
    c = redis_cache.client
    if not c:
        return
        
    try:
        all_keys = []
        for prefix in prefixes:
            for key in c.scan_iter(f"{prefix}:*", count=100):
                all_keys.append(key)
        
        if all_keys:
            c.delete(*all_keys)
            print(f"Invalidated {len(all_keys)} cache keys for prefixes: {prefixes}")
    except Exception as e:
        print(f"Error invalidating cache: {e}")

def invalidate_media_cache():
    """Invalidate all media-related caches"""
    invalidate_cache("media_list", "media_detail", "search", "danbooru")

def invalidate_tag_cache():
    """Invalidate all tag-related caches"""
    invalidate_cache("tags", "tag_detail", "autocomplete", "danbooru", "media_list", "search")

def invalidate_album_cache():
    """Invalidate all album-related caches"""
    invalidate_cache("album_list", "album_contents", "danbooru")

def invalidate_media_item_cache(media_id: int):
    """
    Invalidate cache for a specific media item.
    This should be called when a single media item's properties change
    (like sharing status or parent relationships) that affect its display.
    """
    c = redis_cache.client
    if not c:
        return
    
    try:
        all_keys = list(c.scan_iter(f"media_detail:{media_id}:*", count=100))
        
        for prefix in ["media_list", "search", "danbooru"]:
            for key in c.scan_iter(f"{prefix}:*", count=100):
                all_keys.append(key)
        
        if all_keys:
            c.delete(*all_keys)
            print(f"Invalidated {len(all_keys)} cache keys for media ID {media_id}")
    except Exception as e:
        print(f"Error invalidating media item cache: {e}")
