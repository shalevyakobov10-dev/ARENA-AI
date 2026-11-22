"""HTTP client קטן: rate limit, retry עם backoff, לוגים."""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

import requests

log = logging.getLogger(__name__)

UA = "pmmb/0.1 (+https://github.com/; momentum bot)"


class RateLimiter:
    """token bucket פשוט — מכבד rate_limit_rps."""

    def __init__(self, rps: float) -> None:
        self.rps = max(rps, 0.1)
        self._min_interval = 1.0 / self.rps
        self._next = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            wait = self._next - now
            if wait > 0:
                time.sleep(wait)
                now = time.monotonic()
            self._next = now + self._min_interval


class HttpClient:
    def __init__(
        self,
        base_url: str,
        timeout: float = 15.0,
        max_retries: int = 3,
        rate_limit_rps: float = 8.0,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.limiter = RateLimiter(rate_limit_rps)
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": UA, "Accept": "application/json"})
        self.stats = {"requests": 0, "errors": 0, "retries": 0}

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            self.limiter.acquire()
            self.stats["requests"] += 1
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise requests.HTTPError(f"HTTP {resp.status_code}", response=resp)
                resp.raise_for_status()
                return resp.json()
            except (requests.RequestException, ValueError) as exc:
                last_exc = exc
                self.stats["errors"] += 1
                if attempt >= self.max_retries:
                    break
                self.stats["retries"] += 1
                backoff = min(2 ** (attempt - 1) * 0.5, 8.0)
                log.warning("בקשה נכשלה (%s %s), ניסיון %d/%d, sleep %.1fs",
                            url, exc, attempt, self.max_retries, backoff)
                time.sleep(backoff)
        raise ConnectionError(f"בקשה נכשלה אחרי {self.max_retries} ניסיונות: {url} ({last_exc})")

    def close(self) -> None:
        self.session.close()
