from __future__ import annotations

import asyncio
import tempfile
import time
from typing import Any

from scrapingarena.models import ScrapeRequest, ScrapeResponse
from scrapingarena.scrapers.base import BaseScraper, ScraperMetadata
from scrapingarena.scrapers.playwright_cdp import PlaywrightCdpScraper


class PatchrightScraper(BaseScraper):
    """Use upstream's headed Chrome configuration with a fresh profile per attempt."""

    supports_proxy = True
    metadata = ScraperMetadata(
        slug="patchright",
        name="Patchright",
        kind="antibot-browser",
        homepage="https://github.com/Kaliiiiiiiiii-Vinyzu/patchright",
    )

    async def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        started = time.perf_counter()
        proxy = request.proxy or self._proxy
        driver: Any = None
        context: Any = None
        profile = tempfile.TemporaryDirectory(prefix="arena-patchright-")
        try:
            async with asyncio.timeout(request.timeout_seconds):
                from patchright.async_api import async_playwright

                driver = await async_playwright().start()
                options: dict[str, Any] = {
                    "channel": "chrome",
                    "headless": False,
                    "no_viewport": True,
                    "timeout": request.timeout_seconds * 1000,
                }
                if proxy:
                    options["proxy"] = {
                        "server": f"http://{proxy.host}:{proxy.port}",
                        "username": proxy.username,
                        "password": proxy.password,
                    }
                context = await driver.chromium.launch_persistent_context(
                    profile.name,
                    **options,
                )
                page = await context.new_page()
                response = await page.goto(
                    request.target.url_string,
                    wait_until="domcontentloaded",
                    timeout=request.timeout_seconds * 1000,
                )
                await page.wait_for_timeout(2000)
                return ScrapeResponse(
                    requested_url=request.target.url_string,
                    final_url=page.url,
                    status_code=response.status if response else None,
                    headers=await response.all_headers() if response else {},
                    html=await PlaywrightCdpScraper._page_content(page),
                    duration_ms=(time.perf_counter() - started) * 1000,
                )
        except Exception as exc:
            error = (
                f"{type(exc).__name__}: {str(exc) or 'Patchright attempt timed out'}"
            )
            return ScrapeResponse(
                requested_url=request.target.url_string,
                duration_ms=(time.perf_counter() - started) * 1000,
                error=proxy.redact(error) if proxy else error,
            )
        finally:
            if context is not None:
                await PlaywrightCdpScraper._close_bounded(context)
            if driver is not None:
                await PlaywrightCdpScraper._close_bounded(driver)
            profile.cleanup()
