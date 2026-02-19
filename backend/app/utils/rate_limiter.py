import time
from typing import Dict, Tuple

from fastapi import HTTPException, Request

class SimpleRateLimiter:
    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self.requests: Dict[str, list] = {}
        
    def check(self, request: Request, raise_exception: bool = True) -> bool:
        client_ip = request.client.host
        now = time.time()
        
        # Initialize or clean up old requests
        if client_ip not in self.requests:
            self.requests[client_ip] = []
        
        # Filter out requests older than 1 minute
        self.requests[client_ip] = [req_time for req_time in self.requests[client_ip] if now - req_time < 60]
        
        # Check limit
        if len(self.requests[client_ip]) >= self.requests_per_minute:
            if raise_exception:
                raise HTTPException(status_code=429, detail="Too many requests")
            return False
            
        # Add current request
        self.requests[client_ip].append(now)
        return True

# Global instance
shared_limiter = SimpleRateLimiter(requests_per_minute=60)
