"""Structured HTTP browser layer."""

from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

BROWSER_CAPABILITIES = {"fetch": True, "navigate": False, "interactive": False, "status": "http-capable"}


def browser_capabilities() -> dict[str, Any]:
    return BROWSER_CAPABILITIES


@dataclass
class FetchResult:
    url: str
    status_code: int
    headers: dict[str, str]
    body: str
    content_type: str
    fetched_at: float = field(default_factory=time.time)
    duration_ms: float = 0.0
    error: str | None = None

    @property
    def is_ok(self) -> bool:
        return 200 <= self.status_code < 300

    @property
    def is_html(self) -> bool:
        return "text/html" in self.content_type


class BrowserSession:
    DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (compatible; MAA-X/1.0)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    def __init__(self, default_headers: dict[str, str] | None = None, timeout: float = 10.0, max_response_size: int = 2 * 1024 * 1024) -> None:
        self._cookies: dict[str, str] = {}
        self._headers = dict(self.DEFAULT_HEADERS)
        if default_headers:
            self._headers.update(default_headers)
        self._timeout = timeout
        self._max_size = max_response_size
        self._last_request_time: dict[str, float] = {}
        self._request_count: dict[str, int] = {}

    def set_header(self, key: str, value: str) -> None:
        self._headers[key] = value

    def set_cookie(self, name: str, value: str) -> None:
        self._cookies[name] = value

    def clear_cookies(self) -> None:
        self._cookies.clear()

    def fetch(self, url: str, method: str = "GET", body: str | None = None) -> FetchResult:
        start = time.time()
        try:
            parsed = urllib.parse.urlparse(url)
            domain = parsed.netloc
            if domain in self._last_request_time:
                elapsed = time.time() - self._last_request_time[domain]
                if elapsed < 1.0:
                    time.sleep(1.0 - elapsed)
            self._last_request_time[domain] = time.time()
            self._request_count[domain] = self._request_count.get(domain, 0) + 1
            headers = dict(self._headers)
            if self._cookies:
                headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in self._cookies.items())
            req = urllib.request.Request(url, method=method, headers=headers)
            if body:
                req.data = body.encode("utf-8")
            with urllib.request.urlopen(req, timeout=self._timeout) as response:
                raw_body = response.read(self._max_size + 1)
                if len(raw_body) > self._max_size:
                    raw_body = raw_body[: self._max_size]
                body_str = raw_body.decode("utf-8", errors="replace")
                content_type = response.headers.get("Content-Type", "")
                duration = (time.time() - start) * 1000
                return FetchResult(url, response.status, dict(response.headers), body_str, content_type, duration_ms=duration)
        except urllib.error.HTTPError as e:
            return FetchResult(url, e.code, {}, "", "", duration_ms=(time.time() - start) * 1000, error=f"HTTP {e.code}: {e.reason}")
        except urllib.error.URLError as e:
            return FetchResult(url, 0, {}, "", "", duration_ms=(time.time() - start) * 1000, error=f"URL error: {e.reason}")
        except Exception as e:
            return FetchResult(url, 0, {}, "", "", duration_ms=(time.time() - start) * 1000, error=str(e))

    def get(self, url: str) -> FetchResult:
        return self.fetch(url, "GET")

    def post(self, url: str, data: str) -> FetchResult:
        return self.fetch(url, "POST", data)

    def stats(self) -> dict[str, Any]:
        return {"cookies_count": len(self._cookies), "request_count": sum(self._request_count.values()), "by_domain": dict(self._request_count)}


_global_session = BrowserSession()


def fetch(url: str, method: str = "GET", body: str | None = None) -> FetchResult:
    return _global_session.fetch(url, method, body)


def get(url: str) -> FetchResult:
    return _global_session.get(url)


def post(url: str, data: str) -> FetchResult:
    return _global_session.post(url, data)


def browser_stats() -> dict[str, Any]:
    return _global_session.stats()
