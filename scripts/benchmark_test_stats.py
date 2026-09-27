"""Fetch benchmark test logs and print a Markdown table; never publish results."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

SUMMARY = re.compile(
    r"([\w-]+): (\d+/\d+) success \(([\d.]+)%\), "
    r"median-total=(None|[\d.]+)ms, proxy-connect-failures=(\d+)"
)


def parse_summary(log: str, benchmark: str) -> list[str]:
    matches = [m for m in SUMMARY.finditer(log) if m[1] == benchmark]
    if not matches:
        return ["—", "—", "—", "—"]
    match = matches[-1]
    return [match[2], match[3] + "%", "—" if match[4] == "None" else match[4], match[5]]


def token() -> str | None:
    credential = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
    if not credential and shutil.which("gh"):
        result = subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True, check=False
        )
        if result.returncode == 0:
            credential = result.stdout.strip()
    return credential


def fetch(path: str, credential: str | None) -> str:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "benchmark-stats"}
    request = urllib.request.Request("https://api.github.com" + path, headers=headers)
    if credential:
        # Log downloads redirect to a signed storage URL that authenticates itself.
        # Forwarding GitHub Bearer auth there can cause a storage-service 401.
        request.add_unredirected_header("Authorization", f"Bearer {credential}")
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", errors="replace")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_url")
    args = parser.parse_args()
    match = re.fullmatch(
        r"https://github\.com/([^/]+/[^/]+)/actions/runs/(\d+)/?(?:\?.*)?", args.run_url
    )
    if not match:
        parser.error("Expected https://github.com/OWNER/REPO/actions/runs/RUN_ID")
    repo, run_id = match.groups()
    credential = token()
    jobs = []
    page = 1
    try:
        while True:
            batch = json.loads(
                fetch(
                    f"/repos/{repo}/actions/runs/{run_id}/jobs"
                    f"?filter=latest&per_page=100&page={page}",
                    credential,
                )
            )["jobs"]
            jobs.extend(batch)
            if len(batch) < 100:
                break
            page += 1
    except (urllib.error.URLError, TimeoutError) as exc:
        parser.exit(1, f"Cannot fetch jobs: {exc}\n")
    rows = []
    for job in jobs:
        if not job["name"].startswith("test-"):
            continue
        name = job["name"].removeprefix("test-")
        variant = next(
            (
                v
                for v in (
                    "nodemaven-filtered",
                    "nodemaven-unfiltered",
                    "direct",
                    "oxylabs",
                )
                if name.endswith("-" + v)
            ),
            None,
        )
        if variant is None:
            continue
        scraper = name[: -len(variant) - 1]
        provider = "nodemaven" if variant.startswith("nodemaven-") else variant
        status = job.get("conclusion") or job["status"]
        stats = ["—"] * 4
        if job["status"] == "completed":
            try:
                log = fetch(f"/repos/{repo}/actions/jobs/{job['id']}/logs", credential)
                stats = parse_summary(log, f"{scraper}-{provider}")
                if stats[0] == "—":
                    status += "; no summary"
            except urllib.error.HTTPError as exc:
                if exc.code in {401, 403}:
                    try:
                        detail = json.loads(exc.read()).get("message", exc.reason)
                    except (ValueError, UnicodeDecodeError):
                        detail = exc.reason
                    parser.exit(
                        1,
                        f"GitHub refused job logs (HTTP {exc.code}): {detail}\n"
                        "No statistics were downloaded. Authenticate with an account "
                        "allowed to download these logs (gh auth login or GH_TOKEN), "
                        "then retry.\n",
                    )
                status += f"; logs HTTP {exc.code}"
            except (urllib.error.URLError, TimeoutError):
                status += "; logs unavailable"
        if stats[1] == "—":
            print(f"{scraper} / {variant}: {status}", file=sys.stderr)
        rows.append([scraper, variant, stats[1]])
    if not rows:
        parser.exit(1, "No benchmark test jobs found.\n")
    print(f"Run: https://github.com/{repo}/actions/runs/{run_id}\n")
    print("| Scraper | Proxy type | Success rate |")
    print("| --- | --- | --- |")
    for row in sorted(rows):
        print(
            "| "
            + " | ".join(v.replace("|", "\\|").replace("\n", " ") for v in row)
            + " |"
        )


if __name__ == "__main__":
    main()
