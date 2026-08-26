from __future__ import annotations

import asyncio
import contextlib
import os
import time
from typing import Any

from scrapingarena.models import ScrapeRequest, ScrapeResponse
from scrapingarena.scrapers.base import BaseScraper
from scrapingarena.settings import ProxySettings


class PlaywrightCdpScraper(BaseScraper):
    """Drive a browser service over CDP while isolating every target."""

    supports_proxy = True
    endpoint_env = "SCRAPINGARENA_CDP_ENDPOINT"

    def __init__(self, proxy: ProxySettings | None = None) -> None:
        super().__init__(proxy)
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
        try:
            self._browser = await self._playwright.chromium.connect_over_cdp(endpoint)
        except BaseException:
            # __aexit__ is not called when __aenter__ fails. Stop the Playwright
            # driver here so repeated connection failures do not leak processes.
            await self._close_bounded(self._playwright)
            self._playwright = None
            raise
        return self

    async def close(self) -> None:
        if self._browser is not None:
            await self._close_bounded(self._browser)
            self._browser = None
        if self._playwright is not None:
            await self._close_bounded(self._playwright)
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
                if request.proxy:
                    context = await self._browser.new_context(
                        proxy={
                            "server": (
                                f"http://{request.proxy.host}:{request.proxy.port}"
                            ),
                            "username": request.proxy.username,
                            "password": request.proxy.password,
                        }
                    )
                    owns_context = True
                elif self._browser.contexts:
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
            close = getattr(resource, "close", None) or resource.stop
            await asyncio.wait_for(close(), timeout=5)
