from __future__ import annotations

from pathlib import Path
from runpy import run_path
from typing import Any

import pytest


@pytest.fixture
def driver(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    scripts = Path(__file__).parents[1] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    return run_path(str(scripts / "benchmark_test_ci.py"))


def test_selected_variants_only(driver: dict[str, Any]) -> None:
    matrix = driver["test_matrix"](
        "wreq,curl-cffi", "nodemaven-filtered,nodemaven-unfiltered"
    )
    assert len(matrix) == 4
    assert {item["scraper"] for item in matrix} == {"wreq", "curl-cffi"}
    assert {item["variant"] for item in matrix} == {
        "nodemaven-filtered",
        "nodemaven-unfiltered",
    }


@pytest.mark.parametrize(
    ("scrapers", "proxies"),
    [
        ("typo", "direct"),
        ("wreq", "typo"),
        ("", "direct"),
        ("wreq", ""),
    ],
)
def test_invalid_selection_fails(
    driver: dict[str, Any], scrapers: str, proxies: str
) -> None:
    with pytest.raises(ValueError):
        driver["test_matrix"](scrapers, proxies)


@pytest.mark.parametrize("suffix", ["", "-filter-medium", "-filter-high"])
def test_filter_switch_preserves_country_and_session(
    driver: dict[str, Any], suffix: str
) -> None:
    base = "user-country-us-region-california-sid-abc123"
    assert driver["nodemaven_username"](base + suffix, "nodemaven-filtered") == (
        base + "-filter-medium"
    )
    assert driver["nodemaven_username"](base + suffix, "nodemaven-unfiltered") == base


@pytest.mark.parametrize("username", ["user", "user-country-us", "user-sid-abc"])
def test_manual_nodemaven_requires_routing(
    driver: dict[str, Any], username: str
) -> None:
    with pytest.raises(ValueError):
        driver["nodemaven_username"](username, "nodemaven-filtered")


@pytest.mark.parametrize("fail", [False, True])
def test_reports_are_temporary_even_on_failure(
    driver: dict[str, Any], monkeypatch: pytest.MonkeyPatch, fail: bool
) -> None:
    output_dirs = []

    def execute(args: Any) -> None:
        output_dir = Path(args.output_dir)
        output_dirs.append(output_dir)
        assert output_dir.exists()
        (output_dir / "latest.json").write_text("{}")
        if fail:
            raise RuntimeError("test failure")

    run_test = driver["run_test"]
    monkeypatch.setitem(run_test.__globals__, "execute", execute)
    if fail:
        with pytest.raises(RuntimeError, match="test failure"):
            run_test("wreq", "direct", "5")
    else:
        run_test("wreq", "direct", "5")
    assert len(output_dirs) == 1
    assert not output_dirs[0].exists()
