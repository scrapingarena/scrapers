from __future__ import annotations

import time
from typing import Any

from scrapingarena.models import ScrapeRequest, ScrapeResponse
from scrapingarena.scrapers.base import BaseScraper, ScraperMetadata
from scrapingarena.settings import ProxySettings


class CurlCffiScraper(BaseScraper):
    supports_proxy = True
    metadata = ScraperMetadata(
        slug="curl-cffi",
        name="curl_cffi",
        kind="http",
        homepage="https://github.com/lexiforest/curl_cffi",
    )

    def __init__(self, proxy: ProxySettings | None = None) -> None:
        super().__init__(proxy)
        try:
            from curl_cffi.requests import AsyncSession
        except ImportError as exc:
            raise RuntimeError(
                "curl-cffi requires the 'curl-cffi' project extra"
            ) from exc
        self._session: Any = AsyncSession(impersonate="chrome")

    async def close(self) -> None:
        await self._session.close()

    async def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        started = time.perf_counter()
        try:
            response = await self._session.get(
                request.target.url_string,
                timeout=request.timeout_seconds,
                allow_redirects=True,
                proxy=request.proxy.url if request.proxy else None,
            )
            return ScrapeResponse(
                requested_url=request.target.url_string,
                final_url=str(response.url),
                status_code=response.status_code,
                headers={key.lower(): value for key, value in response.headers.items()},
                html=response.text,
                duration_ms=(time.perf_counter() - started) * 1000,
            )
        except Exception as exc:
            return ScrapeResponse(
                requested_url=request.target.url_string,
                duration_ms=(time.perf_counter() - started) * 1000,
                error=f"{type(exc).__name__}: {exc}",
            )
