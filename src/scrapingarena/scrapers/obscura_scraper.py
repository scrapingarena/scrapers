from __future__ import annotations

from scrapingarena.models import ScrapeRequest, ScrapeResponse
from scrapingarena.scrapers.base import ScraperMetadata
from scrapingarena.scrapers.playwright_cdp import PlaywrightCdpScraper


class ObscuraScraper(PlaywrightCdpScraper):
    """Connect to Obscura, whose proxy is configured when its server starts."""

    metadata = ScraperMetadata(
        slug="obscura",
        name="Obscura",
        kind="agent-browser",
        homepage="https://github.com/h4ckf0r0day/obscura",
    )

    async def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        # Obscura applies OBSCURA_PROXY process-wide. Avoid asking its partial CDP
        # implementation to create a context with Chromium-only proxy parameters.
        return await super().scrape(request.model_copy(update={"proxy": None}))
