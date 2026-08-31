from scrapingarena.scrapers.fortress_scraper import fortress_context_options
from scrapingarena.settings import ProxySettings


def test_fortress_uses_authenticated_proxy_in_browser_context() -> None:
    proxy = ProxySettings(
        host="proxy.example",
        port=7777,
        username="user",
        password="secret",
        provider_name="test",
        provider_url="https://proxy.example",
    )

    assert fortress_context_options(proxy) == {
        "proxy": {
            "server": "http://proxy.example:7777",
            "username": "user",
            "password": "secret",
        }
    }


def test_fortress_direct_context_has_no_proxy() -> None:
    assert fortress_context_options(None) == {}
