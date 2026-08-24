from __future__ import annotations

from scrapingarena.models import ScrapeRequest, ScrapeResponse
from scrapingarena.scrapers.base import ScraperMetadata
from scrapingarena.scrapers.playwright_cdp import PlaywrightCdpScraper


class LightpandaScraper(PlaywrightCdpScraper):
    """Connect to Lightpanda, whose proxy is configured on ``serve``."""

    metadata = ScraperMetadata(
        slug="lightpanda",
        name="Lightpanda",
        kind="agent-browser",
        homepage="https://github.com/lightpanda-io/browser",
    )

    async def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        # The CI service starts Lightpanda with --http-proxy. Reuse that default
        # browser context instead of relying on partial CDP context proxy support.
        return await super().scrape(request.model_copy(update={"proxy": None}))
