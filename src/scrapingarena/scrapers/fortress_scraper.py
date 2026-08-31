from __future__ import annotations

import asyncio
import time
from typing import Any

from scrapingarena.models import ScrapeRequest, ScrapeResponse
from scrapingarena.scrapers.base import BaseScraper, ScraperMetadata
from scrapingarena.settings import ProxySettings


def fortress_context_options(proxy: ProxySettings | None) -> dict[str, Any]:
    if proxy is None:
        return {}
    return {
        "proxy": {
            "server": f"http://{proxy.host}:{proxy.port}",
            "username": proxy.username,
            "password": proxy.password,
        }
    }


class FortressScraper(BaseScraper):
    supports_proxy = True
    metadata = ScraperMetadata(
        slug="fortress",
        name="Fortress",
        kind="antibot-browser",
        homepage="https://github.com/tiliondev/fortress",
    )

    def __init__(self, proxy: ProxySettings | None = None) -> None:
        super().__init__(proxy)
        try:
            from playwright.sync_api import sync_playwright
            from tilion_fortress import Fortress
        except ImportError as exc:
            raise RuntimeError(
                "fortress requires the 'fortress' project extra"
            ) from exc
        self._fortress: Any = Fortress
        self._sync_playwright: Any = sync_playwright

    async def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        return await asyncio.to_thread(self._scrape_sync, request)

    def _scrape_sync(self, request: ScrapeRequest) -> ScrapeResponse:
        started = time.perf_counter()
        engine = None
        playwright = None
        browser = None
        context = None
        try:
            # Fortress documents headed mode as the normal browser path. CI
            # supplies a display with Xvfb, matching the other headed adapters.
            engine = self._fortress(headless=False)
            engine.start()
            playwright = self._sync_playwright().start()
            browser = playwright.chromium.connect_over_cdp(engine.cdp_url)
            context = browser.new_context(**fortress_context_options(self._proxy))
            page = context.new_page()
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
            if context is not None:
                context.close()
            if browser is not None:
                browser.close()
            if playwright is not None:
                playwright.stop()
            if engine is not None:
                engine.close()
