"""Small security helpers: login throttling and response headers."""
import threading
import time
from collections import defaultdict, deque

from flask import Flask, request

CSP = "; ".join(
    [
        "default-src 'self'",
        "img-src 'self' data:",
        "style-src 'self' 'unsafe-inline'",  # inline style="" attributes (progress bars) only
        "script-src 'self'",
        "font-src 'self'",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)


class LoginThrottle:
    """In-memory sliding-window limiter for failed logins.

    Good enough for a single process / small deployment. With several gunicorn
    workers each keeps its own counters (the effective limit becomes N x limit);
    use Redis + Flask-Limiter if you need a shared counter.
    """

    def __init__(self) -> None:
        self._failures: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    @staticmethod
    def key(identifier: str) -> str:
        return f"{request.remote_addr}|{(identifier or '').strip().lower()}"

    def _prune(self, bucket: deque, window: int, now: float) -> None:
        while bucket and now - bucket[0] > window:
            bucket.popleft()

    def retry_after(self, key: str, limit: int, window: int) -> int:
        """Seconds to wait before another attempt is allowed (0 = allowed)."""
        now = time.monotonic()
        with self._lock:
            bucket = self._failures.get(key)
            if not bucket:
                return 0
            self._prune(bucket, window, now)
            if len(bucket) < limit:
                return 0
            return max(1, int(window - (now - bucket[0])))

    def register_failure(self, key: str) -> None:
        with self._lock:
            self._failures[key].append(time.monotonic())

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)

    def clear_all(self) -> None:
        with self._lock:
            self._failures.clear()


login_throttle = LoginThrottle()


def register_security(app: Flask) -> None:
    if app.config.get("TRUST_PROXY"):
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    @app.after_request
    def set_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), camera=(), microphone=()")
        response.headers.setdefault("Content-Security-Policy", CSP)
        if request.is_secure:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        # Dynamic, user-specific pages must not be cached by shared proxies.
        if not request.path.startswith("/static/"):
            response.headers.setdefault("Cache-Control", "no-store" if request.method != "GET" else "private, no-cache")
        return response
