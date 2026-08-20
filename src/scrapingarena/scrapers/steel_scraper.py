from __future__ import annotations

import os
import time
from typing import Any

from scrapingarena.models import ScrapeRequest, ScrapeResponse
from scrapingarena.scrapers.base import BaseScraper, ScraperMetadata
from scrapingarena.settings import ProxySettings


class SteelScraper(BaseScraper):
    supports_proxy = True
    metadata = ScraperMetadata(
        slug="steel",
        name="Steel Browser",
        kind="agent-browser",
        homepage="https://github.com/steel-dev/steel-browser",
    )

    def __init__(self, proxy: ProxySettings | None = None) -> None:
        super().__init__(proxy)
        try:
            from steel import AsyncSteel
        except ImportError as exc:
            raise RuntimeError("steel requires the 'steel' project extra") from exc

        self._client: Any = AsyncSteel(
            steel_api_key=os.getenv("STEEL_API_KEY"),
            base_url=os.getenv("STEEL_BASE_URL", "http://127.0.0.1:3000"),
        )
        self._session: Any = None
        self._playwright: Any = None
        self._browser: Any = None

    async def __aenter__(self) -> SteelScraper:
        if not self._proxy:
            return self
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError(
                "proxied steel requires the 'cdp' project extra"
            ) from exc

        try:
            self._session = await self._client.sessions.create(
                proxy_url=self._proxy.url,
                api_timeout=120_000,
            )
            self._playwright = await async_playwright().start()
            endpoint = self._session.websocket_url
            api_key = os.getenv("STEEL_API_KEY")
            if api_key:
                separator = "&" if "?" in endpoint else "?"
                endpoint = f"{endpoint}{separator}apiKey={api_key}"
            self._browser = await self._playwright.chromium.connect_over_cdp(endpoint)
        except BaseException:
            await self.close()
            raise
        return self

    async def close(self) -> None:
        try:
            if self._browser is not None:
                await self._browser.close()
            if self._playwright is not None:
                await self._playwright.stop()
            if self._session is not None:
                await self._client.sessions.release(self._session.id)
        finally:
            self._browser = None
            self._playwright = None
            self._session = None
            await self._client.close()

    async def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        started = time.perf_counter()
        try:
            if request.proxy:
                if self._browser is None:
                    raise RuntimeError("steel proxy session is not connected")
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
                finally:
                    await page.close()
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
