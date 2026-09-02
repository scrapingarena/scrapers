from scrapingarena.scrapers.base import ScraperMetadata
from scrapingarena.scrapers.playwright_cdp import PlaywrightCdpScraper


class FortressScraper(PlaywrightCdpScraper):
    """Drive the official Fortress container over its raw CDP endpoint."""

    metadata = ScraperMetadata(
        slug="fortress",
        name="Fortress",
        kind="antibot-browser",
        homepage="https://github.com/tiliondev/fortress",
    )

    endpoint_env = "FORTRESS_CDP_URL"
    default_endpoint = "http://127.0.0.1:9222"
