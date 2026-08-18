import json
from pathlib import Path

from scrapingarena.scrapers.registry import scraper_names


def test_expected_scrapers_are_registered() -> None:
    assert scraper_names() == [
        "camoufox-original",
        "cloakbrowser",
        "curl-cffi",
        "lightpanda",
        "niquests",
        "obscura",
        "shardbrowser",
        "steel",
        "wreq",
    ]


def test_benchmark_matrix_matches_registry() -> None:
    config_path = Path(__file__).parents[1] / "benchmark-scrapers.json"
    grouped = json.loads(config_path.read_text())
    configurations = [item for items in grouped.values() for item in items]

    assert sorted(item["slug"] for item in configurations) == scraper_names()
    required_fields = {
        "slug",
        "install_command",
        "benchmark_command",
        "cache_paths",
        "setup_commands",
        "service_commands",
        "health_url",
        "concurrency",
    }
    assert all(item.keys() == required_fields for item in configurations)
    assert all(item["concurrency"] > 0 for item in configurations)
    assert all(
        item["health_url"] for item in configurations if item["service_commands"]
    )
