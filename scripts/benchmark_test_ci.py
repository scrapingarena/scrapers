"""Manual benchmark experiments; results exist only in a temporary directory."""

from __future__ import annotations

import argparse
import json
import os
import re
from tempfile import TemporaryDirectory
from typing import Any

from benchmark_ci import configurations, execute

PROXY_VARIANTS = {
    "direct": "direct",
    "oxylabs": "oxylabs",
    "nodemaven-unfiltered": "nodemaven",
    "nodemaven-filtered": "nodemaven",
}


def selection(value: str, available: set[str]) -> list[str]:
    selected = list(dict.fromkeys(part.strip() for part in value.split(",")))
    if not selected or any(name not in available for name in selected):
        raise ValueError(
            f"Choose comma-separated values from: {', '.join(sorted(available))}"
        )
    return selected


def test_matrix(scrapers: str, proxies: str) -> list[dict[str, Any]]:
    configs = configurations()
    available = {item["scraper"] for item in configs}
    names = (
        sorted(available)
        if scrapers.strip() == "all"
        else selection(scrapers, available)
    )
    variants = selection(proxies, set(PROXY_VARIANTS))
    matrix = []
    for name in names:
        for variant in variants:
            provider = PROXY_VARIANTS[variant]
            config = next(
                (
                    item
                    for item in configs
                    if item["scraper"] == name and item["proxy"] == provider
                ),
                None,
            )
            if config is None:
                raise ValueError(f"{name} does not support {provider}")
            matrix.append(
                {
                    "scraper": name,
                    "variant": variant,
                    "slug": config["slug"],
                    "cache_paths": config["cache_paths"],
                }
            )
    return matrix


def nodemaven_username(username: str, variant: str) -> str:
    """Change only filtering; preserve the chosen country and sticky session."""
    if not re.search(r"-country-[a-zA-Z]{2}(?:-|$)", username):
        raise ValueError("NODEMAVEN_USERNAME must include a country, e.g. -country-us")
    if not re.search(r"-sid-[a-zA-Z0-9]+(?:-|$)", username):
        raise ValueError("NODEMAVEN_USERNAME must include a sticky session: -sid-<id>")
    username = re.sub(r"-filter-[^-]+", "", username)
    return username + "-filter-medium" if variant == "nodemaven-filtered" else username


def run_test(scraper: str, variant: str, limit: str) -> None:
    # Validate even when invoked directly, before installing dependencies.
    config = test_matrix(scraper, variant)[0]
    if variant.startswith("nodemaven-"):
        username = nodemaven_username(os.environ.get("NODEMAVEN_USERNAME", ""), variant)
        if os.getenv("GITHUB_ACTIONS") == "true":
            print(f"::add-mask::{username}", flush=True)
        os.environ["NODEMAVEN_USERNAME"] = username
    with TemporaryDirectory(prefix="benchmark-test-") as output_dir:
        execute(
            argparse.Namespace(
                scraper=config["slug"],
                limit=limit,
                output_dir=output_dir,
            )
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    matrix = commands.add_parser("matrix")
    matrix.add_argument("--scrapers", required=True)
    matrix.add_argument("--proxies", required=True)
    run = commands.add_parser("execute")
    run.add_argument("--scraper", required=True)
    run.add_argument("--variant", choices=PROXY_VARIANTS, required=True)
    run.add_argument("--limit", default="")
    args = parser.parse_args()
    if args.command == "matrix":
        print(
            json.dumps(test_matrix(args.scrapers, args.proxies), separators=(",", ":"))
        )
    else:
        run_test(args.scraper, args.variant, args.limit)


if __name__ == "__main__":
    main()
