from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from typer.testing import CliRunner

from scrapingarena.cli import app
from scrapingarena.models import ScrapeRequest, Target
from scrapingarena.mrscraper import MrScraperClient, MrScraperError
from scrapingarena.scrapers.mrscraper_scraper import MrScraperScraper
from scrapingarena.settings import ProxySettings

API_KEY = "synthetic-key/keep-private"
TARGET = Target.model_validate(
    {
        "id": "example",
        "name": "Example",
        "url": "https://example.com/list",
        "category": "test",
    }
)


@pytest.fixture
def transport(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[Callable[[httpx.Request], httpx.Response]], list[httpx.Request]]:
    monkeypatch.setenv("MRSCRAPER_API_KEY", API_KEY)
    for name in ("FETCH", "SEARCH", "ACCOUNT"):
        monkeypatch.delenv(f"MRSCRAPER_{name}_URL", raising=False)
    client_class = httpx.AsyncClient

    def install(
        handler: Callable[[httpx.Request], httpx.Response],
    ) -> list[httpx.Request]:
        calls: list[httpx.Request] = []

        def handle(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            assert request.headers["authorization"] == f"Bearer {API_KEY}"
            assert request.headers["x-api-token"] == API_KEY
            return handler(request)

        monkeypatch.setattr(
            httpx,
            "AsyncClient",
            lambda **kwargs: client_class(
                **kwargs, transport=httpx.MockTransport(handle)
            ),
        )
        return calls

    return install


@pytest.mark.parametrize("proxied", [False, True])
@pytest.mark.parametrize("target_status", ["200", "403", "invalid", "999", ""])
async def test_benchmark_contract_and_cleanup(
    transport: Any, proxied: bool, target_status: str
) -> None:
    calls = transport(
        lambda request: httpx.Response(
            200,
            json={"html": "<html>Listings</html>", "error": None},
            headers={"X-Status-Code": target_status, "Set-Cookie": "private"},
        )
    )
    proxy = (
        ProxySettings(
            host="proxy.example.com",
            port=8080,
            username="user@example.com",
            password="p/a:ss",
            provider_name="test",
            provider_url="https://example.com",
        )
        if proxied
        else None
    )
    async with MrScraperScraper(proxy) as scraper:
        client = scraper._client._client
        result = await scraper.scrape(
            ScrapeRequest(target=TARGET, timeout_seconds=17.5, proxy=proxy)
        )
    assert client.is_closed
    assert len(calls) == 1
    request = calls[0]
    assert request.url.host == "api.mrscraper.com"
    assert request.method == "POST"
    import json

    assert json.loads(request.content) == {"url": TARGET.url_string, "maxRetries": 0}
    params = request.url.params
    assert params["token"] == API_KEY
    assert params["html"] == "true"
    assert params["markdown"] == "false"
    assert params["browserRendering"] == "true"
    assert params["timeout"] == "18"
    assert params["useProxy"] == str(proxied).lower()
    if proxy:
        assert params["proxy"] == proxy.url.removeprefix("http://")
    else:
        assert "proxy" not in params
    assert result.status_code == (
        int(target_status) if target_status in {"200", "403"} else None
    )
    assert result.html == "<html>Listings</html>"
    assert result.headers == {"content-type": "text/html"}
    assert result.error is None


@pytest.mark.parametrize("status", [401, 429, 500])
async def test_api_errors_are_not_retried_or_leaked(
    transport: Any, status: int
) -> None:
    calls = transport(lambda request: httpx.Response(status, text=f"secret={API_KEY}"))
    async with MrScraperScraper() as scraper:
        result = await scraper.scrape(ScrapeRequest(target=TARGET))
    assert len(calls) == 1
    assert result.error == f"MrScraper HTTP {status}"
    assert API_KEY not in result.model_dump_json()


@pytest.mark.parametrize(
    "payload", [{"html": ""}, {"html": 123}, {"error": "private"}, ["bad shape"]]
)
async def test_incomplete_fetch_is_an_attempt_error(
    transport: Any, payload: Any
) -> None:
    transport(lambda request: httpx.Response(200, json=payload))
    async with MrScraperScraper() as scraper:
        result = await scraper.scrape(ScrapeRequest(target=TARGET))
    assert result.error
    assert result.html == ""


async def test_transport_failure_is_safe_and_client_closes(transport: Any) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout(f"failed: {request.url}", request=request)

    calls = transport(fail)
    async with MrScraperScraper() as scraper:
        result = await scraper.scrape(ScrapeRequest(target=TARGET))
    assert len(calls) == 1
    assert scraper._client._client.is_closed
    assert result.error == "MrScraper request failed (ReadTimeout)"
    assert API_KEY not in result.model_dump_json()


async def test_fetch_output_combinations_and_screenshot_rendering(
    transport: Any,
) -> None:
    calls = transport(
        lambda request: httpx.Response(
            200, json={"markdown": "# Page", "screenshot": "base64-jpeg"}
        )
    )
    async with MrScraperClient() as client:
        payload, _ = await client.scraper_api(
            TARGET.url_string,
            html=False,
            markdown=True,
            screenshot=True,
            browser_rendering=False,
        )
    assert payload["markdown"] == "# Page"
    assert calls[0].url.params["browserRendering"] == "true"
    assert calls[0].url.params["html"] == "false"


async def test_search_retains_results_questions_and_pagination(transport: Any) -> None:
    import json

    payload = {
        "success": True,
        "data": {
            "organic": [
                {
                    "title": "Example",
                    "link": TARGET.url_string,
                    "description": "Example listing",
                }
            ],
            "people_also_ask": [{"question": "What is scraping?"}],
            "pagination": {"current_page": 2},
        },
        "tokenUsage": 1,
    }
    calls = transport(lambda request: httpx.Response(200, json=payload))
    async with MrScraperClient() as client:
        result = await client.web_search(
            "web scraping", region="id", language="id", page=2, render_js=True
        )
    assert result == payload
    request = calls[0]
    assert str(request.url) == (
        "https://sync.scraper.mrscraper.com/api/google/serp/v2/sync"
    )
    assert json.loads(request.content) == {
        "query": "web scraping",
        "region": "id",
        "language": "id",
        "page": 2,
        "format": "json",
        "renderJs": True,
    }


@pytest.mark.parametrize("quota", [(100, 25, 75), (100, 125, 0), (None, None, None)])
async def test_account_selects_public_fields_and_preserves_unknown_quota(
    transport: Any, quota: tuple[int | None, int | None, int | None]
) -> None:
    limit, used, remaining = quota
    calls = transport(
        lambda request: httpx.Response(
            200,
            json={
                "data": {
                    "tokenLimit": limit,
                    "tokenUsage": used,
                    "stripeStatus": "active",
                    "rateLimit": None,
                    "apiToken": API_KEY,
                    "billingId": "private",
                    "user": {
                        "name": "Example",
                        "email": "user@example.com",
                        "isVerified": True,
                        "apiToken": API_KEY,
                    },
                }
            },
        )
    )
    async with MrScraperClient() as client:
        result = await client.account()
    assert calls[0].method == "GET"
    assert calls[0].content == b""
    assert not calls[0].url.query
    assert str(calls[0].url) == (
        "https://api.app.mrscraper.com/api/v1/subscription-accounts"
    )
    assert result["token_remaining"] == remaining
    assert result["rate_limit"] is None
    assert result["user"]["verified"] is True
    assert "private" not in str(result)
    assert API_KEY not in str(result)


@pytest.mark.parametrize("operation", ["account", "web_search", "scraper_api"])
async def test_invalid_json_is_a_safe_error(transport: Any, operation: str) -> None:
    transport(lambda request: httpx.Response(200, text="not-json"))
    async with MrScraperClient() as client:
        with pytest.raises(MrScraperError, match="invalid JSON"):
            if operation == "account":
                await client.account()
            elif operation == "web_search":
                await client.web_search("query")
            else:
                await client.scraper_api(TARGET.url_string)


@pytest.mark.parametrize("payload", [{"success": False}, {"success": True, "data": {}}])
async def test_search_payload_failure(transport: Any, payload: Any) -> None:
    transport(lambda request: httpx.Response(200, json=payload))
    async with MrScraperClient() as client:
        with pytest.raises(MrScraperError):
            await client.web_search("query")


def test_missing_key_is_clear_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MRSCRAPER_API_KEY", raising=False)
    result = CliRunner().invoke(app, ["mrscraper", "account"])
    assert result.exit_code == 1
    assert "MRSCRAPER_API_KEY is required" in result.output


@pytest.mark.parametrize(
    ("args", "method", "payload"),
    [
        (["account"], "account", {"subscription_status": "active"}),
        (["web-search", "query"], "web_search", {"success": True}),
        (
            ["scraper-api", "https://example.com", "--markdown", "--screenshot"],
            "scraper_api",
            ({"html": "page"}, {}),
        ),
    ],
)
def test_cli_commands(
    monkeypatch: pytest.MonkeyPatch, args: list[str], method: str, payload: Any
) -> None:
    monkeypatch.setenv("MRSCRAPER_API_KEY", API_KEY)
    call = AsyncMock(return_value=payload)
    monkeypatch.setattr(MrScraperClient, method, call)
    result = CliRunner().invoke(app, ["mrscraper", *args])
    assert result.exit_code == 0, result.output
    call.assert_awaited_once()
