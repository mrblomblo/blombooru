from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from urllib.parse import quote
import base64
from .config import settings
from .database import get_db

class AuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware to conditionally enforce authentication based on settings.REQUIRE_AUTH.
    Supports multiple authentication methods for maximum client compatibility.
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        
        self.public_paths = {
            "/login",
            "/favicon.ico",
            "/api/admin/login",
            "/api/admin/logout",
            "/api/admin/first-run",
            "/api/admin/onboarding",
            "/api/admin/current-theme",
        }
        
        self.public_prefixes = (
            "/static/",
            "/shared/",
            "/api/shared/",
        )
    
        # Danbooru API routes - these handle their own auth
        self.danbooru_routes = {
            "/posts.json",
            "/tags.json",
            "/artists.json",
            "/pools.json",
            "/users.json",
            "/autocomplete.json",
            "/related_tag.json",
            "/comments.json",
            "/forum_topics.json",
            "/artist_commentaries.json",
            "/post_versions.json",
            "/post_votes.json",
            "/profile.json",
            "/dmails.json",
            "/user_name_change_requests.json",
            "/favorite_groups.json",
        }
        
        self.danbooru_prefixes = (
            "/posts/",
            "/tags/",
            "/artists/",
            "/pools/",
            "/explore/",
            "/counts/",
            "/wiki_pages/",
            "/users/",
            "/api/media/",
        )

    def is_public_route(self, path: str) -> bool:
        if path in self.public_paths:
            return True
        if any(path.startswith(prefix) for prefix in self.public_prefixes):
            return True
        return False
    
    def is_danbooru_route(self, path: str) -> bool:
        if path in self.danbooru_routes:
            return True
        if any(path.startswith(prefix) for prefix in self.danbooru_prefixes):
            return True
        return False
    
    def extract_basic_auth_credentials(self, auth_header: str) -> tuple[str | None, str | None]:
        try:
            if not auth_header.startswith("Basic "):
                return None, None
            
            encoded = auth_header[6:]
            decoded = base64.b64decode(encoded).decode('utf-8')
            
            if ':' not in decoded:
                return None, None
            
            username, password = decoded.split(':', 1)
            return username, password
        except Exception:
            return None, None
    
    def verify_auth(self, request: Request, db) -> bool:
        from .auth import verify_api_key, get_current_user
        
        auth_header = request.headers.get("Authorization", "")
        path = request.url.path

        def can_use_api_key():
            if self.is_danbooru_route(path):
                return True
            return False
        
        # Method 1: Bearer token
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

            if token.startswith("blom_"):
                if can_use_api_key():
                    user = verify_api_key(db, token)
                    if user:
                        return True
            else:
                return False
        
        # Method 2: Direct API key
        elif auth_header.startswith("blom_"):

            if can_use_api_key():
                user = verify_api_key(db, auth_header)
                if user:
                    return True
            else:
                return False
        
        # Method 3: HTTP Basic Auth
        elif auth_header.startswith("Basic "):
            username, password = self.extract_basic_auth_credentials(auth_header)
            is_blom_password = password.startswith('blom_') if password else False
            
            if password:
                if is_blom_password and not can_use_api_key():
                    return False
                else:
                    user = verify_api_key(db, password)
                    if user:
                        if not username or username == user.username:
                            return True
                        else:
                            return False
                    else:
                        return False
        
        # Method 4: Query parameters
        api_key = request.query_params.get("api_key")
        if api_key:            
            if api_key.startswith("blom_") and not can_use_api_key():
                return False
            else:
                user = verify_api_key(db, api_key)
                if user:
                    login = request.query_params.get("login")
                    if not login or login == user.username:
                        return True
        
        # Method 5: Session cookie (Admin/Site Auth) - Always allowed if valid
        admin_token = request.cookies.get("admin_token")
        if admin_token:
            try:
                user = get_current_user(token=admin_token, admin_token=admin_token, db=db)
                if user:
                    return True
            except Exception:
                return False
        
        return False
    
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        
        if self.is_public_route(path):
            return await call_next(request)
        
        if self.is_danbooru_route(path):
            return await call_next(request)

        if not settings.REQUIRE_AUTH:
            return await call_next(request)
        
        try:
            db = next(get_db())
            try:
                if self.verify_auth(request, db):
                    return await call_next(request)
                else:
                    return self.handle_unauthenticated(request)
            finally:
                db.close()
        except HTTPException:
            raise
        except Exception:
            return self.handle_unauthenticated(request)
    
    def handle_unauthenticated(self, request: Request):
        path = request.url.path
        
        if path.startswith("/api/"):
            raise HTTPException(
                status_code=401,
                detail="Authentication required",
                headers={"WWW-Authenticate": 'Basic realm="API"'}
            )
        
        return_url = quote(str(request.url.path))
        if request.url.query:
            return_url += f"?{request.url.query}"
        
        return RedirectResponse(url=f"/login?return={return_url}", status_code=302)
