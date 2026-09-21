from __future__ import annotations

import argparse
from pathlib import Path
from runpy import run_path
from typing import Any

import pytest

proxy_url = run_path(str(Path(__file__).parents[1] / "scripts/benchmark_ci.py"))[
    "proxy_url"
]


def test_proxy_url_is_available_to_system_python_driver() -> None:
    url = proxy_url(
        "oxylabs",
        {
            "OXYLABS_RESIDENTIAL_PROXIES_USERNAME": "user@example.com",
            "OXYLABS_RESIDENTIAL_PROXIES_PASSWORD": "p/a:ss",
        },
    )

    assert url == ("http://user%40example.com:p%2Fa%3Ass@pr.oxylabs.io:7777")


def test_proxy_url_rejects_missing_credentials() -> None:
    with pytest.raises(ValueError, match="not configured"):
        proxy_url("oxylabs", {})


@pytest.mark.parametrize("provider", ["direct", "oxylabs"])
def test_vercel_agent_browser_smoke_precedes_benchmark(provider: str) -> None:
    driver = run_path(str(Path(__file__).parents[1] / "scripts/benchmark_ci.py"))
    calls: list[tuple[Any, Any]] = []

    def record(command: Any, **kwargs: Any) -> None:
        calls.append((command, kwargs.get("env")))

    execute = driver["execute"]
    execute.__globals__["run_command"] = record
    execute(argparse.Namespace(scraper=f"vercel-agent-browser-{provider}", limit="1"))
    assert calls[1][0] == "npm install --global agent-browser@0.37.1"
    assert calls[2][0] == "agent-browser install --with-deps"
    assert calls[3][0] == [
        "uv",
        "run",
        "python",
        "scripts/smoke_vercel_agent_browser.py",
        "--proxy",
        provider,
    ]
    assert calls[4][0][:6] == [
        "uv",
        "run",
        "scrapingarena",
        "benchmark",
        "--scraper",
        "vercel-agent-browser",
    ]
    assert calls[3][1] == calls[4][1]


@pytest.mark.parametrize("scraper", ["patchright", "moli"])
@pytest.mark.parametrize("provider", ["direct", "oxylabs"])
def test_native_browser_smoke_precedes_benchmark(scraper: str, provider: str) -> None:
    driver = run_path(str(Path(__file__).parents[1] / "scripts/benchmark_ci.py"))
    calls: list[Any] = []
    execute = driver["execute"]
    execute.__globals__["run_command"] = lambda command, **kwargs: calls.append(command)
    execute(argparse.Namespace(scraper=f"{scraper}-{provider}", limit="1"))
    prefix = ["xvfb-run", "-a"] if scraper == "patchright" else []
    assert calls[-2] == [
        *prefix,
        "uv",
        "run",
        "python",
        "scripts/smoke_browser.py",
        "--scraper",
        scraper,
        "--proxy",
        provider,
    ]
    assert calls[-1][: len(prefix) + 6] == [
        *prefix,
        "uv",
        "run",
        "scrapingarena",
        "benchmark",
        "--scraper",
        scraper,
    ]
