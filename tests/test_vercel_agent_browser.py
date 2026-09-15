from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pydantic import HttpUrl

from scrapingarena.models import ScrapeRequest, Target
from scrapingarena.scrapers.vercel_agent_browser_scraper import (
    VercelAgentBrowserScraper,
    us_proxy_username,
)
from scrapingarena.settings import ProxySettings


def request(proxy: ProxySettings | None = None) -> ScrapeRequest:
    return ScrapeRequest(
        target=Target(
            id="test",
            name="Test",
            category="test",
            url=HttpUrl("https://example.com/start"),
        ),
        proxy=proxy,
    )


@pytest.mark.parametrize("username", ["customer-test", "customer-test-sessid-abc"])
def test_us_routing_is_added(username: str) -> None:
    assert us_proxy_username(username) == username + "-cc-US"


def test_explicit_country_routing() -> None:
    assert us_proxy_username("customer-test-cc-us-sessid-abc") == (
        "customer-test-cc-us-sessid-abc"
    )
    with pytest.raises(ValueError, match="US country"):
        us_proxy_username("customer-test-cc-DE")


async def test_capture_uses_final_document_and_raw_proxy_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proxy = ProxySettings(
        "pr.oxylabs.io",
        7777,
        "customer-test",
        "p/@:%ss",
        "oxylabs",
        "https://oxylabs.io",
    )
    scraper = VercelAgentBrowserScraper()
    command = AsyncMock(
        side_effect=[
            {},
            {},
            {},
            {
                "origin": "https://example.com/final#section",
                "html": "<html>done</html>",
            },
            {
                "requests": [
                    {"url": "https://example.com/start", "status": 302},
                    {
                        "url": "https://example.com/final",
                        "status": 403,
                        "responseHeaders": {"server": "test"},
                    },
                    {"url": "https://other.example/iframe", "status": 200},
                ]
            },
        ]
    )
    close = AsyncMock()
    monkeypatch.setattr(scraper, "_start", AsyncMock())
    monkeypatch.setattr(scraper, "_command", command)
    monkeypatch.setattr(scraper, "close", close)
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    result = await scraper.scrape(request(proxy))
    assert result.error is None
    assert result.status_code == 403
    assert result.headers == {"server": "test"}
    assert result.html == "<html>done</html>"
    assert command.call_args_list[0].kwargs["proxy"] == {
        "server": "http://pr.oxylabs.io:7777",
        "username": "customer-test-cc-US",
        "password": "p/@:%ss",
    }
    assert command.call_args_list[1].args == ("requests",)
    assert command.call_args_list[2].kwargs["waitUntil"] == "domcontentloaded"
    close.assert_awaited_once()


async def test_timeout_closes_resources(monkeypatch: pytest.MonkeyPatch) -> None:
    scraper = VercelAgentBrowserScraper()
    close = AsyncMock()

    async def hang() -> None:
        await asyncio.Event().wait()

    monkeypatch.setattr(scraper, "_start", hang)
    monkeypatch.setattr(scraper, "close", close)
    result = await scraper.scrape(
        request().model_copy(update={"timeout_seconds": 0.01})
    )
    assert result.error and "TimeoutError" in result.error
    close.assert_awaited_once()


async def test_errors_redact_proxy_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    proxy = ProxySettings("host", 7777, "customer-test", "secret", "oxylabs", "url")
    scraper = VercelAgentBrowserScraper()
    monkeypatch.setattr(
        scraper,
        "_start",
        AsyncMock(side_effect=RuntimeError("failed customer-test-cc-US secret")),
    )
    result = await scraper.scrape(request(proxy))
    assert result.error and "customer-test" not in result.error
    assert "secret" not in result.error


async def test_protocol_handles_large_html_and_command_errors() -> None:
    # Fake daemon exercises actual framing/decoding rather than mocked commands.
    directory = tempfile.TemporaryDirectory(prefix="ab-test-", dir="/tmp")
    socket = Path(directory.name) / "daemon.sock"
    received: list[dict[str, Any]] = []
    html = "<html>" + "x" * 100_000 + "</html>"

    async def serve(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        received.append(json.loads(await reader.readline()))
        response = (
            {"success": True, "data": {"html": html}}
            if received[-1]["action"] == "content"
            else {"success": False, "error": "navigation failed"}
        )
        writer.write(json.dumps(response).encode() + b"\n")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_unix_server(serve, path=socket)
    async with server:
        scraper = VercelAgentBrowserScraper()
        scraper._socket = socket
        assert (await scraper._command("content"))["html"] == html
        with pytest.raises(RuntimeError, match="navigation failed"):
            await scraper._command("navigate", url="https://example.com")
    directory.cleanup()
    assert received[1]["url"] == "https://example.com"
    assert received[0]["id"] != received[1]["id"]
