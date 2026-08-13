from __future__ import annotations

from collections.abc import Callable

from scrapingarena.scrapers.base import BaseScraper
from scrapingarena.scrapers.camoufox_scraper import (
    CamoufoxForkScraper,
    CamoufoxOriginalScraper,
)
from scrapingarena.scrapers.cloakbrowser_scraper import CloakBrowserScraper
from scrapingarena.scrapers.curl_cffi_scraper import CurlCffiScraper
from scrapingarena.scrapers.playwright_cdp import LightpandaScraper, ObscuraScraper
from scrapingarena.scrapers.shardbrowser_scraper import ShardBrowserScraper
from scrapingarena.scrapers.steel_scraper import SteelScraper
from scrapingarena.scrapers.wreq_scraper import WreqScraper

ScraperFactory = Callable[[], BaseScraper]

_SCRAPERS: dict[str, ScraperFactory] = {
    scraper.metadata.slug: scraper
    for scraper in (
        CamoufoxForkScraper,
        CamoufoxOriginalScraper,
        CloakBrowserScraper,
        CurlCffiScraper,
        LightpandaScraper,
        ObscuraScraper,
        ShardBrowserScraper,
        SteelScraper,
        WreqScraper,
    )
}


def scraper_names() -> list[str]:
    return sorted(_SCRAPERS)


def create_scraper(name: str) -> BaseScraper:
    try:
        return _SCRAPERS[name]()
    except KeyError as exc:
        choices = ", ".join(scraper_names())
        raise ValueError(f"unknown scraper {name!r}; choose one of: {choices}") from exc
