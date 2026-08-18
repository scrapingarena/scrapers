from __future__ import annotations

from typing import Any

from scrapingarena.scrapers.shardbrowser_scraper import ShardBrowserScraper


class FakeManager:
    async def __aenter__(self) -> object:
        return object()


class FakeSdk:
    def __init__(self) -> None:
        self.session_kwargs: dict[str, Any] = {}

    def create_profile(self, template: str) -> object:
        return type("FakeProfile", (), {"id": template})()

    def session(self, _profile: object, **kwargs: Any) -> FakeManager:
        self.session_kwargs = kwargs
        return FakeManager()


async def test_shardbrowser_uses_ci_safe_chromium_flags() -> None:
    scraper = object.__new__(ShardBrowserScraper)
    scraper._sdk = FakeSdk()
    scraper._manager = None
    scraper._browser = None
    scraper._profile = None

    await scraper.__aenter__()

    assert scraper._sdk.session_kwargs["extra_args"] == [
        "--no-sandbox",
        "--disable-dev-shm-usage",
    ]
