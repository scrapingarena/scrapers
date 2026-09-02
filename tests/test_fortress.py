from scrapingarena.scrapers.fortress_scraper import FortressScraper


def test_fortress_uses_official_cdp_endpoint() -> None:
    assert FortressScraper.supports_proxy is True
    assert FortressScraper.endpoint_env == "FORTRESS_CDP_URL"
    assert FortressScraper.default_endpoint == "http://127.0.0.1:9222"
