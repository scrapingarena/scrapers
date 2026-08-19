from __future__ import annotations

import time
from typing import Any

from scrapingarena.models import ScrapeRequest, ScrapeResponse
from scrapingarena.scrapers.base import BaseScraper, ScraperMetadata


class NiquestsScraper(BaseScraper):
    metadata = ScraperMetadata(
        slug="niquests",
        name="Niquests",
        kind="http",
        homepage="https://github.com/jawah/niquests",
    )

    def __init__(self) -> None:
        try:
            from niquests import AsyncSession
        except ImportError as exc:
            raise RuntimeError(
                "niquests requires the 'niquests' project extra"
            ) from exc
        self._session: Any = AsyncSession()

    async def close(self) -> None:
        await self._session.close()

    async def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        started = time.perf_counter()
        try:
            response = await self._session.get(
                request.target.url_string,
                timeout=request.timeout_seconds,
                allow_redirects=True,
                proxies=(
                    {"http": request.proxy.url, "https": request.proxy.url}
                    if request.proxy
                    else None
                ),
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
