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


@pytest.mark.parametrize("provider", ["direct", "oxylabs"])
def test_obscura_shares_generated_token_with_service_probe_and_client(
    monkeypatch: Any, provider: str
) -> None:
    monkeypatch.setenv("OXYLABS_PROXIES_USERNAME", "user")
    monkeypatch.setenv("OXYLABS_PROXIES_PASSWORD", "password")
    driver = run_path(str(Path(__file__).parents[1] / "scripts/benchmark_ci.py"))
    calls: list[tuple[Any, Any]] = []
    probes: list[tuple[str, Any]] = []
    execute = driver["execute"]
    execute.__globals__["run_command"] = lambda command, **kwargs: calls.append(
        (command, kwargs.get("env"))
    )
    execute.__globals__["wait_for_service"] = lambda url, **kwargs: probes.append(
        (url, kwargs.get("token"))
    )
    execute.__globals__["print_service_diagnostics"] = lambda: None
    execute(argparse.Namespace(scraper=f"obscura-{provider}", limit="1"))
    container, service_env = next(
        (cmd, env) for cmd, env in calls if cmd[:2] == ["docker", "run"]
    )
    token = service_env["OBSCURA_CDP_TOKEN"]
    assert len(token.encode()) >= 32
    assert container[container.index("OBSCURA_CDP_TOKEN") - 1] == "-e"
    assert token not in " ".join(container)
    assert probes == [("http://127.0.0.1:9222/json/version", token)]
    assert calls[-1][1]["OBSCURA_CDP_TOKEN"] == token


def test_service_probe_sends_bearer_header(monkeypatch: Any) -> None:
    from unittest.mock import MagicMock

    driver = run_path(str(Path(__file__).parents[1] / "scripts/benchmark_ci.py"))
    response = MagicMock()
    response.__enter__.return_value.status = 200
    urlopen = MagicMock(return_value=response)
    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    driver["wait_for_service"]("http://localhost:9222/json/version", token="secret")
    request = urlopen.call_args.args[0]
    assert request.get_header("Authorization") == "Bearer secret"


@pytest.mark.parametrize("suffix", ["", "-filter-medium"])
def test_nodemaven_service_url_matches_client_settings(
    monkeypatch: pytest.MonkeyPatch, suffix: str
) -> None:
    from scrapingarena.settings import configured_proxy

    environ = {
        "NODEMAVEN_USERNAME": f"user@example.com-country-us-sid-abc123{suffix}",
        "NODEMAVEN_PASSWORD": "p/a:ss",
    }
    for key, value in environ.items():
        monkeypatch.setenv(key, value)
    proxy = configured_proxy("nodemaven")
    assert proxy is not None
    assert proxy_url("nodemaven", environ) == proxy.url


@pytest.mark.parametrize(
    "environ", [{}, {"NODEMAVEN_USERNAME": "user"}, {"NODEMAVEN_PASSWORD": "pass"}]
)
def test_nodemaven_service_rejects_incomplete_credentials(
    environ: dict[str, str],
) -> None:
    with pytest.raises(ValueError, match=r"not configured|must be set together"):
        proxy_url("nodemaven", environ)


def test_nodemaven_matrix_has_separate_variants() -> None:
    driver = run_path(str(Path(__file__).parents[1] / "scripts/benchmark_ci.py"))
    direct = driver["configurations"]("direct")
    nodemaven = driver["configurations"]("nodemaven")
    assert {item["scraper"] for item in nodemaven} == {
        item["scraper"] for item in direct
    }
    assert all(item["slug"] == f"{item['scraper']}-nodemaven" for item in nodemaven)
