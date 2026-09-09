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
async def test_steel_uses_self_hosted_proxy_url(
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
        "proxy_url": "http://user%40example.com:p%40ss%3Aword@proxy.example.com:8080",
        "timeout": 150.0,
    }


@pytest.mark.asyncio
async def test_steel_cleanup_releases_session_when_cdp_close_fails() -> None:
    from unittest.mock import AsyncMock

    scraper = object.__new__(SteelScraper)
    scraper._browser = SimpleNamespace(
        close=AsyncMock(side_effect=RuntimeError("disconnected"))
    )
    stop = AsyncMock()
    release = AsyncMock()
    close = AsyncMock()
    scraper._playwright = SimpleNamespace(stop=stop)
    scraper._session = SimpleNamespace(id="session-id")
    scraper._client = SimpleNamespace(
        sessions=SimpleNamespace(release=release), close=close
    )

    with pytest.raises(RuntimeError, match="disconnected"):
        await scraper.close()

    stop.assert_awaited_once()
    release.assert_awaited_once_with("session-id")
    close.assert_awaited_once()
    assert scraper._browser is None
    assert scraper._session is None
    assert scraper._playwright is None
