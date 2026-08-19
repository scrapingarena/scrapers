from __future__ import annotations

import pytest

from scrapingarena.settings import configured_proxy


def test_configured_proxies_loads_oxylabs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OXYLABS_RESIDENTIAL_PROXIES_USERNAME", "user@example.com")
    monkeypatch.setenv("OXYLABS_RESIDENTIAL_PROXIES_PASSWORD", "p/a:ss")

    proxy = configured_proxy("oxylabs")

    assert proxy is not None
    assert proxy.provider_name == "oxylabs"
    assert proxy.host == "pr.oxylabs.io"
    assert proxy.port == 7777
    assert proxy.url == "http://user%40example.com:p%2Fa%3Ass@pr.oxylabs.io:7777"


def test_configured_proxies_rejects_partial_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OXYLABS_RESIDENTIAL_PROXIES_USERNAME", "user")
    monkeypatch.delenv("OXYLABS_RESIDENTIAL_PROXIES_PASSWORD", raising=False)

    with pytest.raises(ValueError, match="must be set together"):
        configured_proxy("oxylabs")


def test_direct_needs_no_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OXYLABS_RESIDENTIAL_PROXIES_USERNAME", raising=False)
    monkeypatch.delenv("OXYLABS_RESIDENTIAL_PROXIES_PASSWORD", raising=False)

    assert configured_proxy("direct") is None


def test_proxy_redacts_raw_and_encoded_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OXYLABS_RESIDENTIAL_PROXIES_USERNAME", "user@example.com")
    monkeypatch.setenv("OXYLABS_RESIDENTIAL_PROXIES_PASSWORD", "p/a:ss")
    proxy = configured_proxy("oxylabs")

    assert proxy is not None
    error = f"failed via {proxy.url}; login user@example.com with p/a:ss"
    redacted = proxy.redact(error)
    assert "user@example.com" not in redacted
    assert "user%40example.com" not in redacted
    assert "p/a:ss" not in redacted
    assert "p%2Fa%3Ass" not in redacted
