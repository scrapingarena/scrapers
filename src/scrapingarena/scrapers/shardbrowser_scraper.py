from __future__ import annotations

import os
import time
from typing import Any

from scrapingarena.models import ScrapeRequest, ScrapeResponse
from scrapingarena.scrapers.base import BaseScraper, ScraperMetadata


class ShardBrowserScraper(BaseScraper):
    metadata = ScraperMetadata(
        slug="shardbrowser",
        name="ShardBrowser (ShardX)",
        kind="antibot-browser",
        homepage="https://github.com/ProxyShard/ShardBrowser",
    )

    def __init__(self) -> None:
        try:
            from shardx import ShardX
        except ImportError as exc:
            raise RuntimeError(
                "shardbrowser requires the 'shardbrowser' project extra"
            ) from exc

        self._sdk: Any = ShardX()
        self._manager: Any = None
        self._browser: Any = None
        self._profile: Any = None

    async def __aenter__(self) -> ShardBrowserScraper:
        template = os.getenv("SHARDX_PROFILE", "linux-gt1030")
        self._profile = self._sdk.create_profile(template)
        self._manager = self._sdk.session(self._profile, headless=True)
        try:
            self._browser = await self._manager.__aenter__()
        except BaseException:
            self._sdk.delete_profile(self._profile.id)
            self._profile = None
            self._manager = None
            raise
        return self

    async def close(self) -> None:
        try:
            if self._browser is not None:
                await self._manager.__aexit__(None, None, None)
        finally:
            self._browser = None
            self._manager = None
            if self._profile is not None:
                self._sdk.delete_profile(self._profile.id)
                self._profile = None

    async def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        if self._browser is None:
            raise RuntimeError(f"{self.metadata.slug} browser is not running")

        started = time.perf_counter()
        context = self._browser.contexts[0]
        page = await context.new_page()
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
