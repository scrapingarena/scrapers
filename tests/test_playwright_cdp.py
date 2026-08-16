from __future__ import annotations

from typing import Any

from scrapingarena.models import ScrapeRequest, Target
from scrapingarena.scrapers.playwright_cdp import LightpandaScraper


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

    async def new_page(self) -> FakePage:
        return self.page


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
