"""
MAA Protocol — Browser Interaction Layer
=========================================
Structured browser automation for MAA agents.

Capabilities:
- Page fetch (GET requests with headers, timeout, follow-redirects)
- Element extraction (text, links, metadata from fetched content)
- Session management (cookies, headers across requests)
- Navigation state tracking
- Rate limiting per domain

Not a full browser automation (no Selenium/Playwright) — works with raw HTTP.
For real browser automation with JS rendering, use the clawd browser plugin.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import urllib.request
import urllib.parse
import urllib.error

# ── Capability flags ──────────────────────────────────────────────────────────

BROWSER_CAPABILITIES = {
    "fetch": True,
    "navigate": False,       # requires real browser automation
    "interactive": False,    # requires JS rendering
    "status": "http-capable",  # current implementation level
}


def browser_capabilities() -> dict[str, Any]:
    return BROWSER_CAPABILITIES


# ── Fetch result ──────────────────────────────────────────────────────────────

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


# ── Session ───────────────────────────────────────────────────────────────────

class BrowserSession:
    """
    HTTP session with cookie jar, default headers, and rate limiting.

    Usage:
        session = BrowserSession()
        result = session.fetch("https://example.com")
        if result.is_ok:
            print(result.body[:200])
    """

    DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (compatible; MAA/1.0; +https://openclaw.ai)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    def __init__(
        self,
        default_headers: dict[str, str] | None = None,
        timeout: float = 10.0,
        max_response_size: int = 2 * 1024 * 1024,  # 2MB cap
    ) -> None:
        self._cookies: dict[str, str] = {}
        self._headers = dict(self.DEFAULT_HEADERS)
        if default_headers:
            self._headers.update(default_headers)
        self._timeout = timeout
        self._max_size = max_response_size
        self._last_request_time: dict[str, float] = {}  # domain → last fetch time
        self._request_count: dict[str, int] = {}  # domain → count

    def set_header(self, key: str, value: str) -> None:
        self._headers[key] = value

    def set_cookie(self, name: str, value: str) -> None:
        self._cookies[name] = value

    def clear_cookies(self) -> None:
        self._cookies.clear()

    def fetch(self, url: str, method: str = "GET", body: str | None = None) -> FetchResult:
        """Fetch a URL. Returns FetchResult."""
        start = time.time()

        try:
            parsed = urllib.parse.urlparse(url)
            domain = parsed.netloc

            # Rate limit: 1 request per second per domain
            if domain in self._last_request_time:
                elapsed = time.time() - self._last_request_time[domain]
                if elapsed < 1.0:
                    time.sleep(1.0 - elapsed)

            self._last_request_time[domain] = time.time()
            self._request_count[domain] = self._request_count.get(domain, 0) + 1

            # Build request
            headers = dict(self._headers)
            if self._cookies:
                cookie_str = "; ".join(f"{k}={v}" for k, v in self._cookies.items())
                headers["Cookie"] = cookie_str

            req = urllib.request.Request(url, method=method, headers=headers)
            if body:
                req.data = body.encode("utf-8")

            # Execute
            with urllib.request.urlopen(req, timeout=self._timeout) as response:
                raw_body = response.read(self._max_size + 1)
                if len(raw_body) > self._max_size:
                    raw_body = raw_body[:self._max_size]

                body_str = raw_body.decode("utf-8", errors="replace")
                content_type = response.headers.get("Content-Type", "")

                # Collect response cookies
                for header_name, header_value in response.headers.items():
                    if header_name.lower() == "set-cookie":
                        for part in header_value.split(";"):
                            if "=" in part:
                                k, v = part.strip().split("=", 1)
                                self._cookies[k.strip()] = v.strip()

                duration = (time.time() - start) * 1000

                return FetchResult(
                    url=url,
                    status_code=response.status,
                    headers=dict(response.headers),
                    body=body_str,
                    content_type=content_type,
                    duration_ms=duration,
                )

        except urllib.error.HTTPError as e:
            duration = (time.time() - start) * 1000
            return FetchResult(
                url=url, status_code=e.code, headers={}, body="",
                content_type="", duration_ms=duration,
                error=f"HTTP {e.code}: {e.reason}",
            )
        except urllib.error.URLError as e:
            duration = (time.time() - start) * 1000
            return FetchResult(
                url=url, status_code=0, headers={}, body="",
                content_type="", duration_ms=duration,
                error=f"URL error: {e.reason}",
            )
        except Exception as e:
            duration = (time.time() - start) * 1000
            return FetchResult(
                url=url, status_code=0, headers={}, body="",
                content_type="", duration_ms=duration,
                error=str(e),
            )

    def get(self, url: str) -> FetchResult:
        return self.fetch(url, "GET")

    def post(self, url: str, data: str) -> FetchResult:
        return self.fetch(url, "POST", data)

    def stats(self) -> dict[str, Any]:
        return {
            "cookies_count": len(self._cookies),
            "request_count": sum(self._request_count.values()),
            "by_domain": dict(self._request_count),
        }


# ── Convenience API ────────────────────────────────────────────────────────────

_global_session = BrowserSession()


def fetch(url: str, method: str = "GET", body: str | None = None) -> FetchResult:
    return _global_session.fetch(url, method, body)


def get(url: str) -> FetchResult:
    return _global_session.get(url)


def post(url: str, data: str) -> FetchResult:
    return _global_session.post(url, data)


def browser_stats() -> dict[str, Any]:
    return _global_session.stats()