from __future__ import annotations

import asyncio
import contextlib
import os
import time
from typing import Any

from scrapingarena.models import ScrapeRequest, ScrapeResponse
from scrapingarena.scrapers.base import BaseScraper, ScraperMetadata


class PlaywrightCdpScraper(BaseScraper):
    """Drive a browser service over CDP while isolating every target."""

    endpoint_env = "SCRAPINGARENA_CDP_ENDPOINT"

    def __init__(self) -> None:
        self._playwright: Any = None
        self._browser: Any = None

    async def __aenter__(self) -> PlaywrightCdpScraper:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError(
                f"{self.metadata.slug} requires the 'cdp' project extra"
            ) from exc

        self._playwright = await async_playwright().start()
        endpoint = os.getenv(self.endpoint_env, "http://127.0.0.1:9222")
        self._browser = await self._playwright.chromium.connect_over_cdp(endpoint)
        return self

    async def close(self) -> None:
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    async def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        if self._browser is None:
            raise RuntimeError(f"{self.metadata.slug} browser is not connected")

        started = time.perf_counter()
        context = None
        owns_context = False
        page = None
        try:
            async with asyncio.timeout(request.timeout_seconds):
                if self._browser.contexts:
                    context = self._browser.contexts[0]
                else:
                    context = await self._browser.new_context()
                    owns_context = True
                page = await context.new_page()
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
            if page is not None:
                await self._close_bounded(page)
            if owns_context and context is not None:
                await self._close_bounded(context)

    @staticmethod
    async def _close_bounded(resource: Any) -> None:
        # A wedged CDP connection must not hold the entire benchmark open.
        with contextlib.suppress(Exception):
            await asyncio.wait_for(resource.close(), timeout=5)


class ObscuraScraper(PlaywrightCdpScraper):
    metadata = ScraperMetadata(
        slug="obscura",
        name="Obscura",
        kind="agent-browser",
        homepage="https://github.com/h4ckf0r0day/obscura",
    )


class LightpandaScraper(PlaywrightCdpScraper):
    metadata = ScraperMetadata(
        slug="lightpanda",
        name="Lightpanda",
        kind="agent-browser",
        homepage="https://github.com/lightpanda-io/browser",
    )
