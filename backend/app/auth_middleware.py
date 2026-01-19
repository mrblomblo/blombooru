from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from urllib.parse import quote
from .config import settings
from .auth import get_current_user
from .database import get_db

class AuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware to conditionally enforce authentication based on settings.REQUIRE_AUTH.
    Excludes public routes such as share links and static files.
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        
        # Public routes and paths that are always accessible
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
    
    def is_public_route(self, path: str) -> bool:
        """Check if the route is public and should bypass authentication"""
        if path in self.public_paths:
            return True
        if any(path.startswith(prefix) for prefix in self.public_prefixes):
            return True
        
        return False
    
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        
        if self.is_public_route(path):
            return await call_next(request)

        if settings.REQUIRE_AUTH:
            try:
                db = next(get_db())
                try:
                    admin_token = request.cookies.get("admin_token")
                    if not admin_token:
                        return self.handle_unauthenticated(request)
                    
                    from .auth import get_current_user as verify_user
                    user = verify_user(token=admin_token, admin_token=admin_token, db=db)
                    
                    if not user:
                        return self.handle_unauthenticated(request)
                finally:
                    db.close()
            except Exception as e:
                print(f"Auth middleware error: {e}")
                return self.handle_unauthenticated(request)
                
        return await call_next(request)
    
    def handle_unauthenticated(self, request: Request):
        """Handle unauthenticated requests"""
        path = request.url.path
        
        if path.startswith("/api/"):
            raise HTTPException(status_code=401, detail="Authentication required")
        
        return_url = quote(str(request.url.path))
        if request.url.query:
            return_url += f"?{request.url.query}"
        
        return RedirectResponse(url=f"/login?return={return_url}", status_code=302)
