from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from scrapingarena.models import ScrapeRequest, Target
from scrapingarena.scrapers.steel_scraper import SteelScraper
from scrapingarena.settings import ProxySettings


@pytest.mark.parametrize("proxied", [False, True])
async def test_steel_uses_quick_scrape_for_both_modes(
    monkeypatch: pytest.MonkeyPatch,
    proxied: bool,
) -> None:
    scrape = AsyncMock(
        return_value=SimpleNamespace(
            metadata=SimpleNamespace(
                url_source="https://example.com/", status_code=200
            ),
            content=SimpleNamespace(html="<html>result</html>"),
        )
    )
    close = AsyncMock()

    class Client:
        def __init__(self, **kwargs: Any) -> None:
            self.scrape = scrape
            self.close = close
            # No sessions API: entering and leaving must not relaunch Steel.

    monkeypatch.setitem(sys.modules, "steel", SimpleNamespace(AsyncSteel=Client))
    proxy = (
        ProxySettings(
            host="proxy.example.com",
            port=8080,
            username="user@example.com",
            password="p@ss:word",
            provider_name="test",
            provider_url="https://example.com",
        )
        if proxied
        else None
    )
    request = ScrapeRequest(
        target=Target.model_validate(
            {
                "id": "example",
                "name": "Example",
                "url": "https://example.com/",
                "category": "test",
            }
        ),
        proxy=proxy,
    )
    async with SteelScraper(proxy) as scraper:
        result = await scraper.scrape(request)
    scrape.assert_awaited_once_with(
        url=request.target.url_string,
        format=["html"],
        delay=2000,
        timeout=request.timeout_seconds,
        extra_body={
            "proxyUrl": "http://user%40example.com:p%40ss%3Aword@proxy.example.com:8080"
            if proxied
            else None
        },
    )
    assert result.status_code == 200
    assert result.html == "<html>result</html>"
    close.assert_awaited_once()


async def test_steel_api_failure_is_reported_as_attempt_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = SimpleNamespace(
        scrape=AsyncMock(side_effect=RuntimeError("proxy failed")), close=AsyncMock()
    )
    monkeypatch.setitem(
        sys.modules, "steel", SimpleNamespace(AsyncSteel=lambda **kwargs: client)
    )
    async with SteelScraper() as scraper:
        result = await scraper.scrape(
            ScrapeRequest(
                target=Target.model_validate(
                    {
                        "id": "example",
                        "name": "Example",
                        "url": "https://example.com/",
                        "category": "test",
                    }
                )
            )
        )
    assert result.error == "RuntimeError: proxy failed"
    client.close.assert_awaited_once()
