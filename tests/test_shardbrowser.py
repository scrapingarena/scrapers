from __future__ import annotations

from typing import Any

from scrapingarena.scrapers.shardbrowser_scraper import ShardBrowserScraper
from scrapingarena.settings import ProxySettings


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
    scraper._proxy = None

    await scraper.__aenter__()

    assert scraper._sdk.session_kwargs["headless"] is False
    assert scraper._sdk.session_kwargs["extra_args"] == [
        "--no-sandbox",
        "--disable-dev-shm-usage",
    ]


async def test_shardbrowser_passes_proxy_to_session() -> None:
    scraper = object.__new__(ShardBrowserScraper)
    scraper._sdk = FakeSdk()
    scraper._manager = None
    scraper._browser = None
    scraper._profile = None
    scraper._proxy = ProxySettings(
        host="proxy.example.com",
        port=8080,
        username="user",
        password="secret",
        provider_name="proxy",
        provider_url="https://example.com/proxy",
    )

    await scraper.__aenter__()

    assert (
        scraper._sdk.session_kwargs["proxy"]
        == "http://user:secret@proxy.example.com:8080"
    )
