from __future__ import annotations

import os
import time
from typing import Any

from scrapingarena.models import ScrapeRequest, ScrapeResponse
from scrapingarena.scrapers.base import BaseScraper, ScraperMetadata


class SteelScraper(BaseScraper):
    metadata = ScraperMetadata(
        slug="steel",
        name="Steel Browser",
        kind="agent-browser",
        homepage="https://github.com/steel-dev/steel-browser",
    )

    def __init__(self) -> None:
        try:
            from steel import AsyncSteel
        except ImportError as exc:
            raise RuntimeError("steel requires the 'steel' project extra") from exc

        self._client: Any = AsyncSteel(
            steel_api_key=os.getenv("STEEL_API_KEY"),
            base_url=os.getenv("STEEL_BASE_URL", "http://127.0.0.1:3000"),
        )

    async def close(self) -> None:
        await self._client.close()

    async def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        started = time.perf_counter()
        try:
            response = await self._client.scrape(
                url=request.target.url_string,
                format=["html"],
                timeout=request.timeout_seconds,
            )
            return ScrapeResponse(
                requested_url=request.target.url_string,
                final_url=response.metadata.url_source or request.target.url_string,
                status_code=response.metadata.status_code,
                html=response.content.html or "",
                duration_ms=(time.perf_counter() - started) * 1000,
            )
        except Exception as exc:
            return ScrapeResponse(
                requested_url=request.target.url_string,
                duration_ms=(time.perf_counter() - started) * 1000,
                error=f"{type(exc).__name__}: {exc}",
            )
