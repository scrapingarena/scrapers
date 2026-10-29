from __future__ import annotations

import time

from scrapingarena.models import ScrapeRequest, ScrapeResponse
from scrapingarena.mrscraper import MrScraperClient
from scrapingarena.scrapers.base import BaseScraper, ScraperMetadata
from scrapingarena.settings import ProxySettings


class MrScraperScraper(BaseScraper):
    supports_proxy = True
    metadata = ScraperMetadata(
        slug="mrscraper",
        name="MrScraper",
        kind="http",
        homepage="https://mrscraper.com",
    )

    def __init__(self, proxy: ProxySettings | None = None) -> None:
        super().__init__(proxy)
        self._client = MrScraperClient()

    async def close(self) -> None:
        await self._client.close()

    async def __aenter__(self) -> MrScraperScraper:
        return self

    async def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        started = time.perf_counter()
        try:
            payload, headers = await self._client.scraper_api(
                request.target.url_string,
                browser_rendering=True,
                timeout=request.timeout_seconds,
                use_proxy=request.proxy is not None,
                proxy=(
                    request.proxy.url.removeprefix("http://") if request.proxy else None
                ),
            )
            # The gateway's HTTP 200 is not the target's HTTP status.
            target_status = headers.get("x-status-code", "")
            status = int(target_status) if target_status.isdigit() else None
            return ScrapeResponse(
                requested_url=request.target.url_string,
                status_code=status
                if status is not None and 100 <= status <= 599
                else None,
                html=payload["html"],
                headers={"content-type": "text/html"},
                duration_ms=(time.perf_counter() - started) * 1000,
            )
        except Exception as exc:
            # Do not copy arbitrary exception strings containing signed URLs.
            from scrapingarena.mrscraper import MrScraperError

            error = str(exc) if isinstance(exc, MrScraperError) else type(exc).__name__
            error = self._client.redact(error)
            if request.proxy:
                error = request.proxy.redact(error)
            return ScrapeResponse(
                requested_url=request.target.url_string,
                duration_ms=(time.perf_counter() - started) * 1000,
                error=error,
            )
