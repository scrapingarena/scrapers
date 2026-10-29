from __future__ import annotations

import asyncio
import math
import os
from typing import Any
from urllib.parse import quote, urlsplit


class MrScraperError(RuntimeError):
    """A MrScraper failure safe to include in CLI output and reports."""


class MrScraperClient:
    """REST client shared by the benchmark adapter and the utility commands."""

    def __init__(self) -> None:
        self._api_key = os.getenv("MRSCRAPER_API_KEY", "").strip()
        if not self._api_key:
            raise MrScraperError("MRSCRAPER_API_KEY is required")
        try:
            import httpx
        except ImportError as exc:
            raise MrScraperError(
                "MrScraper requires the 'mrscraper' project extra"
            ) from exc
        self._client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "x-api-token": self._api_key,
                "Accept": "application/json",
            },
            # Do not follow redirects carrying credentials to another origin.
            follow_redirects=False,
            trust_env=False,
        )

    async def __aenter__(self) -> MrScraperClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    def redact(self, message: str) -> str:
        for secret in (quote(self._api_key, safe=""), self._api_key):
            message = message.replace(secret, "***")
        return message

    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
        timeout: float,
        params: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, str]]:
        try:
            # httpx timeouts apply per I/O operation; the benchmark needs a
            # total deadline even if the service keeps sending small chunks.
            async with asyncio.timeout(timeout):
                response = await self._client.request(
                    method, endpoint, params=params, json=body, timeout=timeout
                )
        except Exception as exc:
            # Transport exceptions can include the signed URL and proxy. Do
            # not copy their message into a public benchmark report.
            raise MrScraperError(
                f"MrScraper request failed ({type(exc).__name__})"
            ) from None
        if not 200 <= response.status_code < 300:
            raise MrScraperError(f"MrScraper HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError:
            raise MrScraperError("MrScraper returned invalid JSON") from None
        if not isinstance(payload, dict):
            raise MrScraperError("MrScraper returned a non-object JSON response")
        return payload, {key.lower(): value for key, value in response.headers.items()}

    async def scraper_api(
        self,
        url: str,
        *,
        html: bool = True,
        markdown: bool = False,
        screenshot: bool = False,
        browser_rendering: bool | None = None,
        timeout: float = 30,
        use_proxy: bool = True,
        proxy: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, str]]:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise MrScraperError("A public HTTP(S) URL is required")
        if not any((html, markdown, screenshot)):
            raise MrScraperError("Select HTML, Markdown, or screenshot output")
        params = {
            "token": self._api_key,
            "html": str(html).lower(),
            "markdown": str(markdown).lower(),
            "screenshot": str(screenshot).lower(),
            "timeout": str(max(1, min(300, math.ceil(timeout)))),
            "useProxy": str(use_proxy).lower(),
        }
        if browser_rendering is not None or screenshot:
            params["browserRendering"] = str(
                bool(browser_rendering) or screenshot
            ).lower()
        if proxy:
            params["proxy"] = proxy
        payload, headers = await self._request(
            "POST",
            os.getenv("MRSCRAPER_FETCH_URL", "https://api.mrscraper.com/"),
            params=params,
            # The benchmark runner owns retries, including service retries.
            body={"url": url, "maxRetries": 0},
            timeout=timeout,
        )
        if payload.get("error"):
            raise MrScraperError("MrScraper reported a page retrieval error")
        for field, requested in (
            ("html", html),
            ("markdown", markdown),
            ("screenshot", screenshot),
        ):
            if requested and (
                not isinstance(payload.get(field), str) or not payload[field].strip()
            ):
                raise MrScraperError(f"MrScraper response is missing {field} content")
        return payload, headers

    async def web_search(
        self,
        query: str,
        *,
        region: str = "us",
        language: str = "en",
        page: int = 1,
        render_js: bool = False,
        timeout: float = 600,
    ) -> dict[str, Any]:
        if not query.strip() or page < 1:
            raise MrScraperError("Search requires a nonempty query and page >= 1")
        payload, _ = await self._request(
            "POST",
            os.getenv(
                "MRSCRAPER_SEARCH_URL",
                "https://sync.scraper.mrscraper.com/api/google/serp/v2/sync",
            ),
            body={
                "query": query,
                "region": region,
                "language": language,
                "page": page,
                "format": "json",
                "renderJs": render_js,
            },
            timeout=timeout,
        )
        if payload.get("success") is not True:
            raise MrScraperError("MrScraper reported a search error")
        data = payload.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("organic"), list):
            raise MrScraperError("MrScraper response is missing organic search results")
        # Preserve snippets, related questions, and pagination without inventing
        # fields for sections the service did not return for this query.
        return payload

    async def account(self, *, timeout: float = 30) -> dict[str, Any]:
        payload, _ = await self._request(
            "GET",
            os.getenv(
                "MRSCRAPER_ACCOUNT_URL",
                "https://api.app.mrscraper.com/api/v1/subscription-accounts",
            ),
            timeout=timeout,
        )
        data = payload.get("data")
        if not isinstance(data, dict):
            raise MrScraperError("MrScraper response is missing account data")
        limit, usage = data.get("tokenLimit"), data.get("tokenUsage")
        remaining = None
        if type(limit) is int and type(usage) is int and limit >= 0 and usage >= 0:
            remaining = max(0, limit - usage)
        user = data.get("user")
        user = user if isinstance(user, dict) else {}
        # The raw account record can contain billing IDs and credentials.
        return {
            "subscription_status": data.get("stripeStatus"),
            "token_limit": limit,
            "token_usage": usage,
            "token_remaining": remaining,
            "rate_limit": data.get("rateLimit"),
            "rate_ttl": data.get("rateTtl"),
            "auto_renew": data.get("isAutoRenew"),
            "ends_at": data.get("endsAt"),
            "enterprise": data.get("isEnterprise"),
            "user": {
                "name": user.get("name"),
                "email": user.get("email"),
                "verified": user.get("isVerified"),
            },
        }
