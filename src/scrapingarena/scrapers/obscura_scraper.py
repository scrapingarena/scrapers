from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from scrapingarena.models import ScrapeRequest, ScrapeResponse
from scrapingarena.scrapers.base import ScraperMetadata
from scrapingarena.scrapers.playwright_cdp import PlaywrightCdpScraper


class ObscuraScraper(PlaywrightCdpScraper):
    """Connect to Obscura, whose proxy is configured when its server starts."""

    isolate_context = True

    def _cdp_connect_options(self) -> dict[str, Any]:
        token = os.getenv("OBSCURA_CDP_TOKEN")
        if not token:
            return {}
        return {"headers": {"Authorization": f"Bearer {token}"}}

    async def __aenter__(self) -> ObscuraScraper:
        # Connect inside the attempt so an unavailable service is recorded as a
        # failed attempt instead of aborting the entire corpus at session entry.
        return self

    metadata = ScraperMetadata(
        slug="obscura",
        name="Obscura",
        kind="agent-browser",
        homepage="https://github.com/h4ckf0r0day/obscura",
    )

    async def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        started = time.perf_counter()
        try:
            if self._browser is None:
                async with asyncio.timeout(request.timeout_seconds):
                    await super().__aenter__()
            remaining = request.timeout_seconds - (time.perf_counter() - started)
            if remaining <= 0:
                raise TimeoutError("CDP deadline exceeded while connecting")
            # Proxy routing belongs to the server; the disposable context owns
            # even targets whose new_page() never returned to Playwright.
            response = await super().scrape(
                request.model_copy(update={"proxy": None, "timeout_seconds": remaining})
            )
            if response.error:
                # A cancelled CDP call does not cancel the server operation.
                # Drop the damaged client; the next attempt connects afresh.
                await self.close()
            return response
        except Exception as exc:
            await self.close()
            detail = str(exc) or "CDP connection deadline exceeded"
            return ScrapeResponse(
                requested_url=request.target.url_string,
                duration_ms=(time.perf_counter() - started) * 1000,
                error=f"{type(exc).__name__}: {detail}",
            )
