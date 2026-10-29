from __future__ import annotations

import asyncio
import json
from typing import Annotated, Any

import typer

from scrapingarena.mrscraper import MrScraperClient, MrScraperError

app = typer.Typer(
    no_args_is_help=True, help="MrScraper Account, scraperAPI, webSearch."
)


def _run(operation: str, **kwargs: Any) -> None:
    async def invoke() -> dict[str, Any]:
        async with MrScraperClient() as client:
            if operation == "account":
                return await client.account(**kwargs)
            if operation == "web_search":
                return await client.web_search(**kwargs)
            payload, _ = await client.scraper_api(**kwargs)
            return payload

    try:
        result = asyncio.run(invoke())
    except MrScraperError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from None
    typer.echo(json.dumps(result, indent=2))


@app.command()
def account() -> None:
    """Read account identity, subscription, token usage, and remaining quota."""
    _run("account")


@app.command("scraper-api")
def scraper_api(
    url: Annotated[str, typer.Argument(help="Public HTTP(S) page URL.")],
    html: Annotated[bool, typer.Option("--html/--no-html")] = True,
    markdown: Annotated[bool, typer.Option("--markdown")] = False,
    screenshot: Annotated[bool, typer.Option("--screenshot")] = False,
    render_js: Annotated[bool, typer.Option("--render-js")] = False,
    timeout: Annotated[float, typer.Option(min=1, max=300)] = 120,
) -> None:
    """Fetch HTML, Markdown, a base64 JPEG screenshot, or a combination as JSON."""
    _run(
        "scraper_api",
        url=url,
        html=html,
        markdown=markdown,
        screenshot=screenshot,
        browser_rendering=True if render_js else None,
        timeout=timeout,
    )


@app.command("web-search")
def web_search(
    query: Annotated[str, typer.Argument(help="Search keywords.")],
    region: str = "us",
    language: str = "en",
    page: Annotated[int, typer.Option(min=1)] = 1,
    render_js: Annotated[bool, typer.Option("--render-js")] = False,
    timeout: Annotated[float, typer.Option(min=1, max=600)] = 600,
) -> None:
    """Search for URLs, titles, descriptions, and related questions as JSON."""
    _run(
        "web_search",
        query=query,
        region=region,
        language=language,
        page=page,
        render_js=render_js,
        timeout=timeout,
    )
