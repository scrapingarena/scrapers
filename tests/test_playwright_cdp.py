from __future__ import annotations

import asyncio
from typing import Any

from scrapingarena.models import ScrapeRequest, Target
from scrapingarena.scrapers.base import ScraperMetadata
from scrapingarena.scrapers.lightpanda_scraper import LightpandaScraper
from scrapingarena.scrapers.playwright_cdp import PlaywrightCdpScraper
from scrapingarena.settings import ProxySettings


class ProxyContextScraper(PlaywrightCdpScraper):
    metadata = ScraperMetadata(
        slug="proxy-context",
        name="Proxy context",
        kind="browser",
        homepage="https://example.com",
    )


class FakeResponse:
    status = 200

    async def all_headers(self) -> dict[str, str]:
        return {"content-type": "text/html"}


class FakePage:
    url = "https://example.com/final"

    def __init__(self) -> None:
        self.closed = False

    async def goto(self, *_args: Any, **_kwargs: Any) -> FakeResponse:
        return FakeResponse()

    async def content(self) -> str:
        return "<html>example</html>"

    async def close(self) -> None:
        self.closed = True


class FakeContext:
    def __init__(self) -> None:
        self.page = FakePage()
        self.closed = False

    async def new_page(self) -> FakePage:
        return self.page

    async def close(self) -> None:
        self.closed = True


class FakeBrowser:
    def __init__(self, contexts: list[FakeContext]) -> None:
        self.contexts = contexts
        self.created_context: FakeContext | None = None
        self.proxy: dict[str, str] | None = None

    async def new_context(self, *, proxy: dict[str, str] | None = None) -> FakeContext:
        self.proxy = proxy
        self.created_context = FakeContext()
        return self.created_context


async def test_cdp_scraper_reuses_default_context_and_closes_only_page() -> None:
    context = FakeContext()
    browser = type("FakeBrowser", (), {"contexts": [context]})()
    scraper = LightpandaScraper()
    scraper._browser = browser
    request = ScrapeRequest(
        target=Target.model_validate(
            {
                "id": "example",
                "name": "Example",
                "url": "https://example.com",
                "category": "test",
            }
        )
    )

    response = await scraper.scrape(request)

    assert response.status_code == 200
    assert response.final_url == "https://example.com/final"
    assert context.page.closed
    assert not context.closed


async def test_cdp_scraper_creates_context_when_server_has_no_default() -> None:
    browser = FakeBrowser([])
    scraper = LightpandaScraper()
    scraper._browser = browser
    request = ScrapeRequest(
        target=Target.model_validate(
            {
                "id": "example",
                "name": "Example",
                "url": "https://example.com",
                "category": "test",
            }
        )
    )

    response = await scraper.scrape(request)

    assert response.status_code == 200
    assert browser.created_context is not None
    assert browser.created_context.page.closed
    assert browser.created_context.closed


async def test_cdp_scraper_times_out_when_cdp_operation_hangs() -> None:
    class HangingContext(FakeContext):
        async def new_page(self) -> FakePage:
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

    scraper = LightpandaScraper()
    scraper._browser = FakeBrowser([HangingContext()])
    request = ScrapeRequest(
        target=Target.model_validate(
            {
                "id": "example",
                "name": "Example",
                "url": "https://example.com",
                "category": "test",
            }
        ),
        timeout_seconds=0.01,
    )

    response = await scraper.scrape(request)

    assert response.error is not None
    assert response.error.startswith("TimeoutError:")


async def test_cdp_scraper_creates_isolated_proxy_context() -> None:
    browser = FakeBrowser([FakeContext()])
    scraper = ProxyContextScraper()
    scraper._browser = browser
    proxy = ProxySettings(
        host="proxy.example.com",
        port=8080,
        username="user",
        password="secret",
        provider_name="proxy",
        provider_url="https://example.com/proxy",
    )
    request = ScrapeRequest(
        target=Target.model_validate(
            {
                "id": "example",
                "name": "Example",
                "url": "https://example.com",
                "category": "test",
            }
        ),
        proxy=proxy,
    )

    response = await scraper.scrape(request)

    assert response.status_code == 200
    assert browser.proxy == {
        "server": "http://proxy.example.com:8080",
        "username": "user",
        "password": "secret",
    }
    assert browser.created_context is not None
    assert browser.created_context.closed
