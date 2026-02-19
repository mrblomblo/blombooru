from datetime import datetime, timedelta, timezone
from typing import Dict, Tuple

from fastapi import HTTPException, Request

class LoginRateLimiter:
    """
    Rate limiter for login attempts to prevent brute force attacks.
    Tracks failed login attempts by IP address and temporarily bans IPs that exceed the limit.
    """
    
    def __init__(self, max_attempts: int = 5, ban_duration_minutes: int = 15):
        """
        Initialize the rate limiter.
        """
        self.max_attempts = max_attempts
        self.ban_duration = timedelta(minutes=ban_duration_minutes)
        self.failed_attempts: Dict[str, Tuple[int, datetime]] = {}
        self.banned_ips: Dict[str, datetime] = {}
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request, considering proxies"""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host
        
        return "unknown"
    
    def _cleanup_expired(self):
        """Remove expired bans and old failed attempts"""
        now = datetime.now(timezone.utc)
        
        expired_bans = [ip for ip, expiry in self.banned_ips.items() if now >= expiry]
        for ip in expired_bans:
            del self.banned_ips[ip]
            if ip in self.failed_attempts:
                del self.failed_attempts[ip]
        
        expired_attempts = [
            ip for ip, (_, first_attempt) in self.failed_attempts.items()
            if now - first_attempt > self.ban_duration
        ]
        for ip in expired_attempts:
            del self.failed_attempts[ip]
    
    def check_rate_limit(self, request: Request):
        """
        Check if the request should be rate limited.
        
        Raises:
            HTTPException: If the IP is banned or rate limit exceeded
        """
        self._cleanup_expired()
        
        ip = self._get_client_ip(request)
        now = datetime.now(timezone.utc)
        
        if ip in self.banned_ips:
            ban_expiry = self.banned_ips[ip]
            remaining_seconds = int((ban_expiry - now).total_seconds())
            remaining_minutes = max(1, remaining_seconds // 60)
            
            raise HTTPException(
                status_code=429,
                detail=f"Too many failed login attempts. Please try again in {remaining_minutes} minute(s)."
            )
    
    def record_failed_attempt(self, request: Request):
        """
        Record a failed login attempt.
        If max attempts exceeded, ban the IP.
        """
        self._cleanup_expired()
        
        ip = self._get_client_ip(request)
        now = datetime.now(timezone.utc)
        
        if ip in self.failed_attempts:
            count, first_attempt = self.failed_attempts[ip]
            
            if now - first_attempt <= self.ban_duration:
                count += 1
                self.failed_attempts[ip] = (count, first_attempt)
                
                if count >= self.max_attempts:
                    self.banned_ips[ip] = now + self.ban_duration
                    print(f"IP {ip} banned for {self.ban_duration.total_seconds() / 60} minutes after {count} failed attempts")
            else:
                self.failed_attempts[ip] = (1, now)
        else:
            self.failed_attempts[ip] = (1, now)
    
    def clear_failed_attempts(self, request: Request):
        """Clear failed attempts for an IP (called on successful login)"""
        ip = self._get_client_ip(request)
        if ip in self.failed_attempts:
            del self.failed_attempts[ip]
        if ip in self.banned_ips:
            del self.banned_ips[ip]
    
    def get_remaining_attempts(self, request: Request) -> int:
        """Get the number of remaining login attempts for an IP"""
        self._cleanup_expired()
        
        ip = self._get_client_ip(request)
        
        if ip in self.banned_ips:
            return 0
        
        if ip in self.failed_attempts:
            count, _ = self.failed_attempts[ip]
            return max(0, self.max_attempts - count)
        
        return self.max_attempts

login_rate_limiter = LoginRateLimiter(max_attempts=5, ban_duration_minutes=15)
