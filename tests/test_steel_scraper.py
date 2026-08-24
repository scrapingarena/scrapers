from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

import pytest

from scrapingarena.scrapers.steel_scraper import SteelScraper
from scrapingarena.settings import ProxySettings


class AsyncContextManager:
    async def close(self) -> None:
        pass


@pytest.mark.asyncio
async def test_steel_uses_structured_byop_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_arguments: dict[str, Any] = {}

    class Sessions:
        async def create(self, **kwargs: Any) -> Any:
            create_arguments.update(kwargs)
            return SimpleNamespace(id="session-id", websocket_url="ws://127.0.0.1:3000")

        async def release(self, session_id: str) -> None:
            assert session_id == "session-id"

    class Client:
        def __init__(self, **kwargs: Any) -> None:
            self.sessions = Sessions()

        async def close(self) -> None:
            pass

    class Playwright(AsyncContextManager):
        def __init__(self) -> None:
            self.chromium = SimpleNamespace(connect_over_cdp=self.connect_over_cdp)

        async def start(self) -> Playwright:
            return self

        async def connect_over_cdp(self, endpoint: str) -> AsyncContextManager:
            assert endpoint == "ws://127.0.0.1:3000"
            return AsyncContextManager()

        async def stop(self) -> None:
            pass

    playwright = Playwright()
    monkeypatch.setitem(sys.modules, "steel", SimpleNamespace(AsyncSteel=Client))
    monkeypatch.setitem(
        sys.modules,
        "playwright.async_api",
        SimpleNamespace(async_playwright=lambda: playwright),
    )
    proxy = ProxySettings(
        host="proxy.example.com",
        port=8080,
        username="user@example.com",
        password="p@ss:word",
        provider_name="test",
        provider_url="https://proxy.example.com",
    )

    async with SteelScraper(proxy):
        pass

    assert create_arguments == {
        "use_proxy": {
            "server": ("http://user%40example.com:p%40ss%3Aword@proxy.example.com:8080")
        },
        "api_timeout": 120_000,
        "timeout": 150.0,
    }
