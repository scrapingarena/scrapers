from __future__ import annotations

from typing import Any

from scrapingarena.models import ScrapeRequest, Target
from scrapingarena.scrapers.obscura_scraper import ObscuraScraper
from scrapingarena.settings import ProxySettings


async def test_obscura_uses_server_proxy_and_default_context() -> None:
    class Page:
        url = "https://example.com"

        async def goto(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        async def content(self) -> str:
            return "<html></html>"

        async def close(self) -> None:
            pass

    class Context:
        async def new_page(self) -> Page:
            return Page()

    class Browser:
        def __init__(self) -> None:
            self.contexts = [Context()]

        async def new_context(self, **_kwargs: Any) -> None:
            raise AssertionError("Obscura proxy must not be configured over CDP")

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
