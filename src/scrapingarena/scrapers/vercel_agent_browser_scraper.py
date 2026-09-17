from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import tempfile
import time
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import uuid4

import psutil

from scrapingarena.models import ScrapeRequest, ScrapeResponse
from scrapingarena.scrapers.agent_browser_proxy import ProxyBridge
from scrapingarena.scrapers.base import BaseScraper, ScraperMetadata
from scrapingarena.settings import ProxySettings


def us_proxy_username(username: str) -> str:
    """Keep explicit US/session options; reject conflicting country routing."""
    country = re.search(r"-cc-([^-]+)", username, re.IGNORECASE)
    if country:
        if country.group(1).upper() != "US":
            raise ValueError("agent-browser requires Oxylabs US country routing")
        return username
    return f"{username}-cc-US"


class VercelAgentBrowserScraper(BaseScraper):
    """Drive the pinned agent-browser daemon, independently of Playwright.

    The owned child keeps Chrome visible to the arena's resource monitor.
    The version-specific newline JSON protocol is covered by a CI smoke test.
    """

    supports_proxy = True
    metadata = ScraperMetadata(
        slug="agent-browser",
        name="Vercel Agent Browser",
        kind="agent-browser",
        homepage="https://github.com/vercel-labs/agent-browser",
    )

    def __init__(self, proxy: ProxySettings | None = None) -> None:
        super().__init__(proxy)
        self._process: asyncio.subprocess.Process | None = None
        self._directory: tempfile.TemporaryDirectory[str] | None = None
        self._socket: Path | None = None
        self._proxy_bridge: ProxyBridge | None = None

    async def _start(self) -> None:
        # Short Unix socket paths also work on macOS (104-byte path limit).
        self._directory = tempfile.TemporaryDirectory(prefix="ab-", dir="/tmp")
        self._socket = Path(self._directory.name) / "arena.sock"
        env = {
            k: v for k, v in os.environ.items() if not k.startswith("AGENT_BROWSER_")
        }
        env.update(
            AGENT_BROWSER_DAEMON="1",
            AGENT_BROWSER_SESSION="arena",
            AGENT_BROWSER_SOCKET_DIR=self._directory.name,
            AGENT_BROWSER_ENGINE="chrome",
            AGENT_BROWSER_IDLE_TIMEOUT_MS="60000",
        )
        self._process = await asyncio.create_subprocess_exec(
            os.getenv("SCRAPINGARENA_AGENT_BROWSER_BINARY", "agent-browser"),
            env=env,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        while not self._socket.exists():
            if self._process.returncode is not None:
                raise RuntimeError("agent-browser daemon exited before becoming ready")
            await asyncio.sleep(0.02)

    async def _command(self, action: str, **parameters: Any) -> dict[str, Any]:
        if self._socket is None:
            raise RuntimeError("agent-browser daemon is not started")
        reader, writer = await asyncio.open_unix_connection(
            str(self._socket), limit=64 * 1024 * 1024
        )
        try:
            command = {"id": uuid4().hex, "action": action, **parameters}
            writer.write(json.dumps(command).encode() + b"\n")
            await writer.drain()
            response = json.loads(await reader.readline())
            if response.get("success") is not True:
                raise RuntimeError(
                    str(response.get("error", "agent-browser command failed"))
                )
            data = response.get("data", {})
            if not isinstance(data, dict):
                raise RuntimeError("agent-browser returned invalid response data")
            return data
        finally:
            writer.close()
            await writer.wait_closed()

    async def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        started = time.perf_counter()
        proxy = request.proxy or self._proxy
        try:
            async with asyncio.timeout(request.timeout_seconds):
                launch: dict[str, Any] = {"headless": True}
                if proxy:
                    username = (
                        us_proxy_username(proxy.username)
                        if proxy.provider_name == "oxylabs"
                        else proxy.username
                    )
                    # v0.37.1 can stall Page.navigate with Fetch proxy auth.
                    # Authenticate upstream in an owned loopback bridge instead.
                    self._proxy_bridge = ProxyBridge(replace(proxy, username=username))
                    launch["proxy"] = {"server": await self._proxy_bridge.start()}
                await self._start()
                await self._command("launch", **launch)
                # Tracking must be enabled before navigation to capture status/headers.
                await self._command("requests")
                await self._command(
                    "navigate",
                    url=request.target.url_string,
                    waitUntil="domcontentloaded",
                )
                await asyncio.sleep(2)
                content = await self._command("content")
                final_url = str(content["origin"])
                network = await self._command("requests", type="document")
                # Match the captured document, excluding unrelated iframe responses.
                documents = [
                    item
                    for item in network.get("requests", [])
                    if item["url"].split("#", 1)[0] == final_url.split("#", 1)[0]
                    and item.get("status") is not None
                ]
                document = documents[-1] if documents else {}
                return ScrapeResponse(
                    requested_url=request.target.url_string,
                    final_url=final_url,
                    status_code=document.get("status"),
                    headers=document.get("responseHeaders") or {},
                    html=content["html"],
                    duration_ms=(time.perf_counter() - started) * 1000,
                )
        except Exception as exc:
            detail = str(exc) or "agent-browser attempt deadline exceeded"
            error = f"{type(exc).__name__}: {detail}"
            return ScrapeResponse(
                requested_url=request.target.url_string,
                duration_ms=(time.perf_counter() - started) * 1000,
                error=proxy.redact(error) if proxy else error,
            )
        finally:
            await self.close()

    async def close(self) -> None:
        process, self._process = self._process, None
        descendants = []
        if process is not None and process.returncode is None:
            with contextlib.suppress(psutil.Error):
                descendants = psutil.Process(process.pid).children(recursive=True)
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._command("close"), timeout=2)
            # Also clean up a wedged daemon and Chrome's separately grouped children.
            for child in reversed(descendants):
                with contextlib.suppress(psutil.Error):
                    child.kill()
            if process.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    process.kill()
            await process.wait()
        if self._directory is not None:
            self._directory.cleanup()
            self._directory = None
        self._socket = None
        if self._proxy_bridge is not None:
            await self._proxy_bridge.close()
            self._proxy_bridge = None
