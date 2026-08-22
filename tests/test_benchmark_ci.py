from __future__ import annotations

from pathlib import Path
from runpy import run_path

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

    assert url == "http://user%40example.com:p%2Fa%3Ass@pr.oxylabs.io:7777"


def test_proxy_url_rejects_missing_credentials() -> None:
    with pytest.raises(ValueError, match="not configured"):
        proxy_url("oxylabs", {})
