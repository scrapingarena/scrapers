from __future__ import annotations

import asyncio
import contextlib
import json
import os
import time
from pathlib import Path

from scrapingarena.models import ScrapeRequest, ScrapeResponse
from scrapingarena.scrapers.base import BaseScraper, ScraperMetadata
from scrapingarena.scrapers.vercel_agent_browser_proxy import ProxyBridge


class MoliScraper(BaseScraper):
    """Run a fresh native Moli process for each measured attempt."""

    supports_proxy = True
    metadata = ScraperMetadata(
        slug="moli",
        name="Moli",
        kind="agent-browser",
        homepage="https://github.com/lexmount/moli",
    )

    async def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        started = time.perf_counter()
        proxy = request.proxy or self._proxy
        process = None
        bridge = None
        try:
            async with asyncio.timeout(request.timeout_seconds):
                binary = os.getenv(
                    "SCRAPINGARENA_MOLI_BINARY",
                    str(Path.home() / ".cache/scrapingarena/moli/1.1.9/moli"),
                )
                command = [
                    binary,
                    "fetch",
                    "--dump",
                    "json",
                    "--wait",
                    "domcontentloaded",
                    "--delay-ms",
                    "2000",
                    "--timeout",
                    str(max(1, int(request.timeout_seconds * 1000))),
                ]
                if proxy:
                    # Keep credentials out of process arguments. The shared bridge
                    # authenticates HTTP and opaque HTTPS CONNECT requests upstream.
                    bridge = ProxyBridge(proxy)
                    command.extend(("--http-proxy", await bridge.start()))
                command.append(request.target.url_string)
                env = {
                    key: value
                    for key, value in os.environ.items()
                    if key.lower()
                    not in {
                        "http_proxy",
                        "https_proxy",
                        "all_proxy",
                        "no_proxy",
                    }
                    and not key.startswith("MOLI_")
                }
                process = await asyncio.create_subprocess_exec(
                    *command,
                    env=env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await process.communicate()
                if bridge is not None and bridge.error:
                    raise RuntimeError(bridge.error)
                if process.returncode:
                    raise RuntimeError(
                        f"Moli exited with code {process.returncode}: "
                        + stderr.decode(errors="replace")[-2000:]
                    )
                data = json.loads(stdout)
                return ScrapeResponse(
                    requested_url=request.target.url_string,
                    final_url=data["final_url"],
                    status_code=data["status"],
                    headers={item["name"]: item["value"] for item in data["headers"]},
                    html=data["html"],
                    duration_ms=(time.perf_counter() - started) * 1000,
                )
        except Exception as exc:
            error = f"{type(exc).__name__}: {str(exc) or 'Moli attempt timed out'}"
            return ScrapeResponse(
                requested_url=request.target.url_string,
                duration_ms=(time.perf_counter() - started) * 1000,
                error=proxy.redact(error) if proxy else error,
            )
        finally:
            if process is not None and process.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    process.kill()
                await process.communicate()
            if bridge is not None:
                await bridge.close()
