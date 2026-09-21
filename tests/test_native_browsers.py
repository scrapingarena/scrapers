from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import HttpUrl

from scrapingarena.models import ScrapeRequest, Target
from scrapingarena.scrapers.moli_scraper import MoliScraper
from scrapingarena.scrapers.patchright_scraper import PatchrightScraper
from scrapingarena.settings import ProxySettings


def request(proxy: ProxySettings | None = None) -> ScrapeRequest:
    return ScrapeRequest(
        target=Target(
            id="test", name="Test", category="test", url=HttpUrl("https://example.com")
        ),
        proxy=proxy,
    )


async def test_patchright_uses_fresh_profile_raw_credentials_and_captures_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proxy = ProxySettings(
        "proxy.test", 7777, "raw-user-cc-DE", "p/@:%ss", "oxylabs", "url"
    )
    response = SimpleNamespace(
        status=403, all_headers=AsyncMock(return_value={"x-test": "yes"})
    )
    page = SimpleNamespace(
        goto=AsyncMock(return_value=response),
        wait_for_timeout=AsyncMock(),
        content=AsyncMock(return_value="<html>blocked</html>"),
        url="https://example.com/final",
    )
    context = SimpleNamespace(new_page=AsyncMock(return_value=page), close=AsyncMock())
    launch = AsyncMock(return_value=context)
    driver = SimpleNamespace(
        chromium=SimpleNamespace(launch_persistent_context=launch), stop=AsyncMock()
    )
    monkeypatch.setitem(
        sys.modules,
        "patchright.async_api",
        SimpleNamespace(
            async_playwright=lambda: SimpleNamespace(
                start=AsyncMock(return_value=driver)
            ),
        ),
    )
    scraper = PatchrightScraper()
    for _ in range(2):
        result = await scraper.scrape(request(proxy))
        assert result.error is None
        assert result.status_code == 403
        assert result.headers == {"x-test": "yes"}
        assert result.final_url == page.url
        assert result.html == "<html>blocked</html>"
    options = launch.call_args.kwargs
    assert options["channel"] == "chrome"
    assert options["headless"] is False
    assert options["no_viewport"] is True
    assert options["proxy"] == {
        "server": "http://proxy.test:7777",
        "username": proxy.username,
        "password": proxy.password,
    }
    profiles = [call.args[0] for call in launch.call_args_list]
    assert profiles[0] != profiles[1]
    assert all(not Path(path).exists() for path in profiles)
    assert context.close.await_count == driver.stop.await_count == 2


async def test_patchright_timeout_stops_driver(monkeypatch: pytest.MonkeyPatch) -> None:
    async def hang(*args: object, **kwargs: object) -> None:
        await asyncio.Event().wait()

    driver = SimpleNamespace(
        chromium=SimpleNamespace(launch_persistent_context=hang), stop=AsyncMock()
    )
    monkeypatch.setitem(
        sys.modules,
        "patchright.async_api",
        SimpleNamespace(
            async_playwright=lambda: SimpleNamespace(
                start=AsyncMock(return_value=driver)
            ),
        ),
    )
    result = await PatchrightScraper().scrape(
        request().model_copy(update={"timeout_seconds": 0.01})
    )
    assert result.error and result.error.startswith("TimeoutError:")
    driver.stop.assert_awaited_once()


async def test_moli_captures_json_and_keeps_credentials_out_of_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proxy = ProxySettings("proxy.test", 7777, "raw-user", "p/@:%ss", "oxylabs", "url")
    data = {
        "final_url": "https://example.com/final",
        "status": 429,
        "headers": [{"name": "Retry-After", "value": "60"}],
        "html": "<html>wait</html>",
    }
    process = SimpleNamespace(
        returncode=0,
        communicate=AsyncMock(return_value=(json.dumps(data).encode(), b"")),
    )
    spawn = AsyncMock(return_value=process)
    bridge = SimpleNamespace(
        start=AsyncMock(return_value="http://127.0.0.1:12345"),
        error=None,
        close=AsyncMock(),
    )
    factory = MagicMock(return_value=bridge)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr("scrapingarena.scrapers.moli_scraper.ProxyBridge", factory)
    monkeypatch.setenv("HTTPS_PROXY", "http://unwanted.test:8080")
    monkeypatch.setenv("NO_PROXY", "*")
    monkeypatch.setenv("MOLI_LAYOUT", "1")
    result = await MoliScraper(proxy).scrape(request())
    assert result.error is None
    assert result.status_code == 429
    assert result.headers == {"Retry-After": "60"}
    assert result.html == data["html"]
    assert result.final_url == data["final_url"]
    assert factory.call_args.args[0] is proxy
    arguments = spawn.call_args.args
    assert "http://127.0.0.1:12345" in arguments
    assert proxy.username not in " ".join(arguments)
    assert proxy.password not in " ".join(arguments)
    assert (
        not {"HTTPS_PROXY", "NO_PROXY", "MOLI_LAYOUT"}
        & spawn.call_args.kwargs["env"].keys()
    )
    bridge.close.assert_awaited_once()


async def test_moli_timeout_kills_and_reaps_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def communicate() -> tuple[bytes, bytes]:
        if process.returncode is None:
            await asyncio.Event().wait()
        return b"", b""

    def kill() -> None:
        process.returncode = -9

    process = SimpleNamespace(
        returncode=None,
        communicate=AsyncMock(side_effect=communicate),
        kill=MagicMock(side_effect=kill),
    )
    monkeypatch.setattr(
        asyncio, "create_subprocess_exec", AsyncMock(return_value=process)
    )
    result = await MoliScraper().scrape(
        request().model_copy(update={"timeout_seconds": 0.01})
    )
    assert result.error and result.error.startswith("TimeoutError:")
    process.kill.assert_called_once()
    assert process.communicate.await_count == 2
