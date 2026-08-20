from __future__ import annotations

from scrapingarena.scrapers.camoufox_scraper import camoufox_launch_options
from scrapingarena.settings import ProxySettings


def test_camoufox_proxy_configuration_matches_exit_ip() -> None:
    proxy = ProxySettings(
        host="proxy.example.com",
        port=8080,
        username="user",
        password="secret",
        provider_name="proxy",
        provider_url="https://example.com/proxy",
    )

    options = camoufox_launch_options(proxy)

    assert options["proxy"] == {
        "server": "http://proxy.example.com:8080",
        "username": "user",
        "password": "secret",
    }
    assert options["geoip"] is True


def test_camoufox_direct_mode_does_not_perform_geoip_lookup() -> None:
    options = camoufox_launch_options(None)

    assert "proxy" not in options
    assert "geoip" not in options
