from __future__ import annotations

import time
from typing import Any

from scrapingarena.models import ScrapeRequest, ScrapeResponse
from scrapingarena.scrapers.base import BaseScraper, ScraperMetadata


class CamoufoxScraper(BaseScraper):
    package_extra = "camoufox"

    def __init__(self) -> None:
        try:
            from camoufox.async_api import AsyncCamoufox
        except ImportError as exc:
            raise RuntimeError(
                f"{self.metadata.slug} requires the '{self.package_extra}' extra"
            ) from exc
        self._manager: Any = AsyncCamoufox(headless=True)
        self._browser: Any = None

    async def __aenter__(self) -> CamoufoxScraper:
        self._browser = await self._manager.__aenter__()
        return self

    async def close(self) -> None:
        if self._browser is not None:
            await self._manager.__aexit__(None, None, None)
            self._browser = None

    async def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        if self._browser is None:
            raise RuntimeError(f"{self.metadata.slug} browser is not running")

        started = time.perf_counter()
        page = await self._browser.new_page()
        try:
            response = await page.goto(
                request.target.url_string,
                wait_until="domcontentloaded",
                timeout=request.timeout_seconds * 1000,
            )
            return ScrapeResponse(
                requested_url=request.target.url_string,
                final_url=page.url,
                status_code=response.status if response else None,
                headers=await response.all_headers() if response else {},
                html=await page.content(),
                duration_ms=(time.perf_counter() - started) * 1000,
            )
        except Exception as exc:
            return ScrapeResponse(
                requested_url=request.target.url_string,
                duration_ms=(time.perf_counter() - started) * 1000,
                error=f"{type(exc).__name__}: {exc}",
            )
        finally:
            await page.close()


class CamoufoxOriginalScraper(CamoufoxScraper):
    package_extra = "camoufox-original"
    metadata = ScraperMetadata(
        slug="camoufox-original",
        name="Camoufox (original)",
        kind="antibot-browser",
        homepage="https://github.com/daijro/camoufox",
    )


class CamoufoxForkScraper(CamoufoxScraper):
    package_extra = "camoufox-fork"
    metadata = ScraperMetadata(
        slug="camoufox-fork",
        name="Camoufox (CloverLabs fork)",
        kind="antibot-browser",
        homepage="https://github.com/CloverLabsAI/camoufox",
    )
