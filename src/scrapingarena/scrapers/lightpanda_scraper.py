from __future__ import annotations

from scrapingarena.scrapers.base import ScraperMetadata
from scrapingarena.scrapers.playwright_cdp import PlaywrightCdpScraper


class LightpandaScraper(PlaywrightCdpScraper):
    metadata = ScraperMetadata(
        slug="lightpanda",
        name="Lightpanda",
        kind="agent-browser",
        homepage="https://github.com/lightpanda-io/browser",
    )
