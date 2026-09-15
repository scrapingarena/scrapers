"""Fail CI before benchmarking if the pinned runtime or US proxy is broken."""

from __future__ import annotations

import argparse
import asyncio
import json
from html.parser import HTMLParser

from scrapingarena.models import ScrapeRequest, Target
from scrapingarena.scrapers.vercel_agent_browser_scraper import (
    VercelAgentBrowserScraper,
)
from scrapingarena.settings import configured_proxy


class PageText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.in_pre = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "pre":
            self.in_pre = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "pre":
            self.in_pre = False

    def handle_data(self, data: str) -> None:
        if self.in_pre:
            self.parts.append(data)


async def serve(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        request = await reader.readuntil(b"\r\n\r\n")
        if request.startswith(b"GET /redirect "):
            reply = (
                b"HTTP/1.1 302 Found\r\nLocation: /page\r\nContent-Length: 0\r\n\r\n"
            )
        else:
            body = (
                b"<!doctype html><html><body><main id='result'>waiting</main>"
                b"<script>setTimeout(()=>document.querySelector('#result').textContent="
                b"'arena-hydrated',100)</script></body></html>"
            )
            reply = (
                b"HTTP/1.1 201 Created\r\nContent-Type: text/html\r\n"
                b"X-Arena-Smoke: passed\r\nContent-Length: "
                + str(len(body)).encode()
                + b"\r\n\r\n"
                + body
            )
        writer.write(reply)
        await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


async def smoke(provider: str) -> None:
    server = await asyncio.start_server(serve, "127.0.0.1", 0)
    async with server:
        port = server.sockets[0].getsockname()[1]
        scraper = VercelAgentBrowserScraper()
        response = await scraper.scrape(
            ScrapeRequest(
                target=Target(
                    id="smoke",
                    name="Smoke",
                    category="test",
                    url=f"http://127.0.0.1:{port}/redirect",
                ),
            )
        )
        assert response.error is None, response.error
        assert response.status_code == 201, response.status_code
        assert response.final_url == f"http://127.0.0.1:{port}/page"
        assert {k.lower(): v for k, v in response.headers.items()}[
            "x-arena-smoke"
        ] == "passed"
        assert '<main id="result">arena-hydrated</main>' in response.html
        assert scraper._process is None
    print(
        "agent-browser direct smoke passed (redirect, status, headers, rendered HTML)"
    )

    if provider == "oxylabs":
        proxy = configured_proxy(provider)
        response = await VercelAgentBrowserScraper().scrape(
            ScrapeRequest(
                target=Target(
                    id="proxy-smoke",
                    name="Proxy smoke",
                    category="test",
                    url="https://ip.oxylabs.io/location",
                ),
                proxy=proxy,
                timeout_seconds=60,
            )
        )
        assert response.error is None, response.error
        assert response.status_code == 200, response.status_code
        text = PageText()
        text.feed(response.html)
        location = json.loads("".join(text.parts))
        countries = {
            data["country"]
            for data in location["providers"].values()
            if data.get("country")
        }
        assert countries == {"US"}, f"Expected US proxy exit, received {countries!r}"
        print("agent-browser Oxylabs smoke passed (authenticated HTTPS, US exit)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--proxy", choices=["direct", "oxylabs"], default="direct")
    asyncio.run(smoke(parser.parse_args().proxy))
