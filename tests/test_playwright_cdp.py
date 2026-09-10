from __future__ import annotations

import asyncio
import sys
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


async def test_cdp_scraper_stops_playwright_when_connection_fails(
    monkeypatch: Any,
) -> None:
    class Chromium:
        async def connect_over_cdp(self, _endpoint: str) -> None:
            raise ConnectionRefusedError("CDP service is unavailable")

    class Playwright:
        chromium = Chromium()

        def __init__(self) -> None:
            self.stopped = False

        async def stop(self) -> None:
            self.stopped = True

    playwright = Playwright()

    class Manager:
        async def start(self) -> Playwright:
            return playwright

    fake_module = type(
        "FakePlaywrightModule",
        (),
        {"async_playwright": staticmethod(lambda: Manager())},
    )()
    monkeypatch.setitem(sys.modules, "playwright.async_api", fake_module)

    scraper = LightpandaScraper()
    try:
        await scraper.__aenter__()
    except ConnectionRefusedError:
        pass
    else:
        raise AssertionError("connection failure was not propagated")

    assert playwright.stopped
    assert scraper._playwright is None


async def test_capture_retries_navigation_race_within_attempt() -> None:
    class NavigatingPage(FakePage):
        calls = 0

        async def goto(self, *_args: Any, **kwargs: Any) -> FakeResponse:
            assert 0 < kwargs["timeout"] < 1000
            return FakeResponse()

        async def content(self) -> str:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError(
                    "Unable to retrieve content because the "
                    "page is navigating and changing the content."
                )
            return "<html>ready</html>"

    context = FakeContext()
    page = NavigatingPage()
    context.page = page
    scraper = LightpandaScraper()
    scraper._browser = FakeBrowser([context])
    response = await scraper.scrape(
        ScrapeRequest(
            target=Target.model_validate(
                {
                    "id": "example",
                    "name": "Example",
                    "url": "https://example.com",
                    "category": "test",
                }
            ),
            timeout_seconds=1,
        )
    )
    assert response.html == "<html>ready</html>"
    assert response.status_code == 200
    assert page.calls == 2
    assert page.closed


async def test_capture_race_is_bounded_and_preserves_http_status() -> None:
    class NavigatingPage(FakePage):
        async def content(self) -> str:
            raise RuntimeError("page is navigating and changing the content")

    context = FakeContext()
    context.page = NavigatingPage()
    scraper = LightpandaScraper()
    scraper._browser = FakeBrowser([context])
    response = await scraper.scrape(
        ScrapeRequest(
            target=Target.model_validate(
                {
                    "id": "example",
                    "name": "Example",
                    "url": "https://example.com",
                    "category": "test",
                }
            ),
            timeout_seconds=0.02,
        )
    )
    assert response.error == "TimeoutError: CDP deadline exceeded while capturing page"
    assert response.status_code == 200
    assert context.page.closed
