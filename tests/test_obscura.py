from __future__ import annotations

from typing import Any

from pydantic import HttpUrl

from scrapingarena.models import ScrapeRequest, Target
from scrapingarena.scrapers.obscura_scraper import ObscuraScraper
from scrapingarena.settings import ProxySettings


async def test_obscura_uses_server_proxy_and_disposable_context() -> None:
    class Page:
        url = "https://example.com"

        async def goto(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        async def content(self) -> str:
            return "<html></html>"

        async def close(self) -> None:
            pass

    closed = []

    class Context:
        async def new_page(self) -> Page:
            return Page()

        async def close(self) -> None:
            closed.append(True)

    class Browser:
        def __init__(self) -> None:
            self.contexts = [Context()]

        async def new_context(self, **kwargs: Any) -> Context:
            assert not kwargs
            return Context()

    proxy = ProxySettings(
        host="proxy.example.com",
        port=8080,
        username="user",
        password="secret",
        provider_name="proxy",
        provider_url="https://example.com/proxy",
    )
    scraper = ObscuraScraper(proxy=proxy)
    scraper._browser = Browser()
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

    assert response.status_code is None
    assert response.html == "<html></html>"
    assert closed == [True]


async def test_page_creation_timeout_disposes_context_and_reconnects(
    monkeypatch: Any,
) -> None:
    import asyncio

    from scrapingarena.scrapers.playwright_cdp import PlaywrightCdpScraper

    closed: list[str] = []

    class Page:
        url = "https://example.com"

        async def goto(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        async def content(self) -> str:
            return "recovered"

        async def close(self) -> None:
            closed.append("page")

    class Context:
        def __init__(self, hang: bool) -> None:
            self.hang = hang

        async def new_page(self) -> Page:
            if self.hang:
                await asyncio.Event().wait()
            return Page()

        async def close(self) -> None:
            closed.append("context")

    class Browser:
        def __init__(self, hang: bool) -> None:
            self.hang = hang
            self.contexts: list[Any] = []

        async def new_context(self) -> Context:
            return Context(self.hang)

        async def close(self) -> None:
            closed.append("browser")

    connections = 0

    async def connect(self: PlaywrightCdpScraper) -> PlaywrightCdpScraper:
        nonlocal connections
        connections += 1
        self._browser = Browser(connections == 1)
        return self

    monkeypatch.setattr(PlaywrightCdpScraper, "__aenter__", connect)
    request = ScrapeRequest(
        target=Target(
            id="example",
            name="Example",
            url=HttpUrl("https://example.com"),
            category="test",
        ),
        timeout_seconds=0.02,
    )
    async with ObscuraScraper() as scraper:
        failed = await scraper.scrape(request)
        assert failed.error == "TimeoutError: CDP deadline exceeded while creating page"
        assert closed == ["context", "browser"]
        assert scraper._browser is None
        recovered = await scraper.scrape(request)
        assert recovered.html == "recovered"
        assert recovered.error is None
        assert connections == 2
    assert closed == ["context", "browser", "page", "context", "browser"]


async def test_connection_failure_is_an_attempt_result(monkeypatch: Any) -> None:
    from scrapingarena.scrapers.playwright_cdp import PlaywrightCdpScraper

    async def connect(self: PlaywrightCdpScraper) -> PlaywrightCdpScraper:
        raise ConnectionRefusedError("service unavailable")

    monkeypatch.setattr(PlaywrightCdpScraper, "__aenter__", connect)
    request = ScrapeRequest(
        target=Target(
            id="example",
            name="Example",
            url=HttpUrl("https://example.com"),
            category="test",
        ),
    )
    async with ObscuraScraper() as scraper:
        for _ in range(2):
            response = await scraper.scrape(request)
            assert response.error == "ConnectionRefusedError: service unavailable"


async def test_connection_deadline_is_bounded(monkeypatch: Any) -> None:
    import asyncio

    from scrapingarena.scrapers.playwright_cdp import PlaywrightCdpScraper

    async def connect(self: PlaywrightCdpScraper) -> PlaywrightCdpScraper:
        await asyncio.Event().wait()
        return self

    monkeypatch.setattr(PlaywrightCdpScraper, "__aenter__", connect)
    request = ScrapeRequest(
        target=Target(
            id="example",
            name="Example",
            url=HttpUrl("https://example.com"),
            category="test",
        ),
        timeout_seconds=0.02,
    )
    async with ObscuraScraper() as scraper:
        response = await asyncio.wait_for(scraper.scrape(request), timeout=1)
        assert response.error == "TimeoutError: CDP connection deadline exceeded"


async def test_obscura_authenticates_cdp_connection(monkeypatch: Any) -> None:
    import sys
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from scrapingarena.scrapers.playwright_cdp import PlaywrightCdpScraper

    token = "test-token-" * 4
    monkeypatch.setenv("OBSCURA_CDP_TOKEN", token)
    monkeypatch.setenv("SCRAPINGARENA_CDP_ENDPOINT", "http://localhost:9222")
    connect = AsyncMock()
    driver = SimpleNamespace(
        chromium=SimpleNamespace(connect_over_cdp=connect), stop=AsyncMock()
    )
    monkeypatch.setitem(
        sys.modules,
        "playwright.async_api",
        SimpleNamespace(
            async_playwright=lambda: SimpleNamespace(
                start=AsyncMock(return_value=driver)
            )
        ),
    )
    scraper = ObscuraScraper()
    await PlaywrightCdpScraper.__aenter__(scraper)
    connect.assert_awaited_once_with(
        "http://localhost:9222", headers={"Authorization": f"Bearer {token}"}
    )
    await scraper.close()
    # Other CDP services must not receive Obscura's credential.
    assert PlaywrightCdpScraper()._cdp_connect_options() == {}
    monkeypatch.delenv("OBSCURA_CDP_TOKEN")
    assert scraper._cdp_connect_options() == {}
