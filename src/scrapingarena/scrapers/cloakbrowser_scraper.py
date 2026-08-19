from __future__ import annotations

import asyncio
import time
from typing import Any

from scrapingarena.models import ScrapeRequest, ScrapeResponse
from scrapingarena.scrapers.base import BaseScraper, ScraperMetadata
from scrapingarena.settings import ProxySettings


class CloakBrowserScraper(BaseScraper):
    supports_proxy = True
    metadata = ScraperMetadata(
        slug="cloakbrowser",
        name="CloakBrowser",
        kind="antibot-browser",
        homepage="https://github.com/CloakHQ/CloakBrowser",
    )

    def __init__(self, proxy: ProxySettings | None = None) -> None:
        super().__init__(proxy)
        try:
            from cloakbrowser import launch
        except ImportError as exc:
            raise RuntimeError(
                "cloakbrowser requires the 'cloakbrowser' project extra"
            ) from exc
        self._launch: Any = launch

    async def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        return await asyncio.to_thread(self._scrape_sync, request)

    def _scrape_sync(self, request: ScrapeRequest) -> ScrapeResponse:
        started = time.perf_counter()
        browser = None
        try:
            options: dict[str, Any] = {"headless": True}
            if self._proxy:
                options["proxy"] = {
                    "server": f"http://{self._proxy.host}:{self._proxy.port}",
                    "username": self._proxy.username,
                    "password": self._proxy.password,
                }
            browser = self._launch(**options)
            page = browser.new_page()
            response = page.goto(
                request.target.url_string,
                wait_until="domcontentloaded",
                timeout=request.timeout_seconds * 1000,
            )
            return ScrapeResponse(
                requested_url=request.target.url_string,
                final_url=page.url,
                status_code=response.status if response else None,
                headers=response.all_headers() if response else {},
                html=page.content(),
                duration_ms=(time.perf_counter() - started) * 1000,
            )
        except Exception as exc:
            return ScrapeResponse(
                requested_url=request.target.url_string,
                duration_ms=(time.perf_counter() - started) * 1000,
                error=f"{type(exc).__name__}: {exc}",
            )
        finally:
            if browser is not None:
                browser.close()
