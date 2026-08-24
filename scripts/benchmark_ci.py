from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(__file__).parents[1]
CONFIG_PATH = ROOT / "benchmark-scrapers.json"


def proxy_url(provider: str, environ: dict[str, str]) -> str:
    """Build a proxy URL without importing the uv-managed project package."""
    if provider != "oxylabs":
        raise ValueError(f"unknown proxy provider: {provider}")
    username = environ.get("OXYLABS_RESIDENTIAL_PROXIES_USERNAME")
    password = environ.get("OXYLABS_RESIDENTIAL_PROXIES_PASSWORD")
    if not username or not password:
        raise ValueError("Oxylabs proxy credentials are not configured")
    return (
        f"http://{quote(username, safe='')}:{quote(password, safe='')}"
        "@pr.oxylabs.io:7777"
    )


def configurations(proxy_filter: str | None = None) -> list[dict[str, Any]]:
    grouped = json.loads(CONFIG_PATH.read_text())
    configurations = []
    for category, items in grouped.items():
        for item in items:
            for proxy in item["proxy_providers"]:
                if proxy_filter is not None and proxy != proxy_filter:
                    continue
                workflow_fields = {
                    "slug": f"{item['slug']}-{proxy}",
                    "scraper": item["slug"],
                    "proxy": proxy,
                    "category": category,
                    "cache_paths": "\n".join(item["cache_paths"]),
                }
                configurations.append(item | workflow_fields)
    return configurations


def configuration(slug: str) -> dict[str, Any]:
    try:
        return next(item for item in configurations() if item["slug"] == slug)
    except StopIteration as exc:
        raise SystemExit(f"unknown scraper configuration: {slug}") from exc


def run_command(
    command: str | list[str],
    *,
    env: dict[str, str] | None = None,
    redact_values: tuple[str, ...] = (),
) -> None:
    arguments = shlex.split(command) if isinstance(command, str) else command
    display_command = shlex.join(arguments)
    for value in redact_values:
        display_command = display_command.replace(value, "***")
    print(f"+ {display_command}", flush=True)
    subprocess.run(arguments, cwd=ROOT, env=env, check=True)


def wait_for_service(url: str) -> None:
    for _ in range(60):
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status < 400:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(1)
    run_command(["docker", "logs", "scrapingarena-browser"])
    raise SystemExit(f"service did not become healthy: {url}")


def print_service_diagnostics() -> None:
    """Leave useful evidence when a service dies without failing the job."""
    subprocess.run(
        [
            "docker",
            "inspect",
            "--format",
            "{{json .State}}",
            "scrapingarena-browser",
        ],
        cwd=ROOT,
        check=False,
    )
    subprocess.run(
        ["docker", "logs", "--tail", "200", "scrapingarena-browser"],
        cwd=ROOT,
        check=False,
    )


def execute(args: argparse.Namespace) -> None:
    config = configuration(args.scraper)
    install_command = shlex.split(config["install_command"])
    install_command.extend(("--extra", "openai"))
    run_command(install_command)

    env = os.environ | {"CLOAKBROWSER_AUTO_UPDATE": "false"}
    if config["scraper"] == "obscura" and config["proxy"] != "direct":
        env["OBSCURA_PROXY"] = proxy_url(config["proxy"], env)
    for command in config["setup_commands"]:
        run_command(command, env=env)

    for command in config["service_commands"]:
        arguments = shlex.split(command)
        redact_values: tuple[str, ...] = ()
        if config["scraper"] == "lightpanda" and config["proxy"] != "direct":
            upstream_proxy = proxy_url(config["proxy"], env)
            arguments.extend(("--http-proxy", upstream_proxy))
            redact_values = (upstream_proxy,)
        run_command(arguments, env=env, redact_values=redact_values)
    if config["service_commands"]:
        wait_for_service(config["health_url"])
        if config["proxy"] == "direct":
            env["SCRAPINGARENA_RESOURCE_CONTAINER"] = "scrapingarena-browser"

    command = [
        *shlex.split(config["benchmark_command"]),
        "--proxy",
        config["proxy"],
        "--concurrency",
        str(config["concurrency"]),
        "--retries",
        "3",
        "--output-dir",
        f"shard-results/{args.scraper}",
    ]
    if args.limit:
        command.extend(("--limit", args.limit))
    try:
        run_command(command, env=env)
    finally:
        if config["service_commands"]:
            print_service_diagnostics()


def aggregate(args: argparse.Namespace) -> None:
    run_command(["uv", "sync", "--locked"])
    shards = sorted(ROOT.glob("downloaded-shards/*/latest.json"))
    if not shards:
        raise SystemExit("no downloaded scraper shards found")
    run_command(
        [
            "uv",
            "run",
            "scrapingarena",
            "merge",
            *(str(path) for path in shards),
            "--run-id",
            args.run_id,
            "--output-dir",
            "results",
        ]
    )
    if args.limit:
        return

    run_command(["git", "config", "user.name", "scrapingarena-bot"])
    run_command(
        [
            "git",
            "config",
            "user.email",
            "scrapingarena-bot@users.noreply.github.com",
        ]
    )
    run_command(
        ["git", "add", "results/latest.json", "results/index.json", "results/runs/"]
    )
    changed = subprocess.run(
        ["git", "diff", "--cached", "--quiet"], cwd=ROOT, check=False
    )
    if changed.returncode == 0:
        return
    if changed.returncode != 1:
        raise SystemExit(changed.returncode)
    message = f"results: benchmark run {args.run_id} [skip ci]"
    run_command(["git", "commit", "-m", message])
    run_command(["git", "pull", "--rebase", "origin", args.ref])
    run_command(["git", "push", "origin", f"HEAD:{args.ref}"])


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    matrix_parser = subparsers.add_parser("matrix")
    matrix_parser.add_argument("--proxy")

    execute_parser = subparsers.add_parser("execute")
    execute_parser.add_argument("--scraper", required=True)
    execute_parser.add_argument("--limit", default="")

    aggregate_parser = subparsers.add_parser("aggregate")
    aggregate_parser.add_argument("--run-id", required=True)
    aggregate_parser.add_argument("--ref", required=True)
    aggregate_parser.add_argument("--limit", default="")

    args = parser.parse_args()
    if args.command == "matrix":
        print(json.dumps(configurations(args.proxy), separators=(",", ":")))
    elif args.command == "execute":
        execute(args)
    else:
        aggregate(args)


if __name__ == "__main__":
    main()
