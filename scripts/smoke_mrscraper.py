"""Exercise the real MrScraper HTTP client against the local Postman simulation."""

from __future__ import annotations

import argparse
import asyncio
import os
from urllib.parse import urlsplit

from scrapingarena.models import ScrapeRequest, Target
from scrapingarena.mrscraper import MrScraperClient, MrScraperError
from scrapingarena.scrapers.mrscraper_scraper import MrScraperScraper


async def smoke(base_url: str) -> None:
    if urlsplit(base_url).hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("The simulation must run on loopback")
    base_url = base_url.rstrip("/")
    os.environ.update(
        MRSCRAPER_API_KEY="synthetic-mrscraper-key",
        MRSCRAPER_FETCH_URL=f"{base_url}/",
        MRSCRAPER_SEARCH_URL=f"{base_url}/api/google/serp/v2/sync",
        MRSCRAPER_ACCOUNT_URL=f"{base_url}/api/v1/subscription-accounts",
    )
    async with MrScraperClient() as client:
        account = await client.account()
        assert account["token_remaining"] == 975
        assert "private-fixture" not in str(account)
        search = await client.web_search("web scraping")
        assert search["data"]["organic"][0]["description"] == "Example listings"
        assert search["data"]["people_also_ask"]
        fetch, _ = await client.scraper_api(
            "https://example.com/list", markdown=True, screenshot=True
        )
        assert fetch["html"] and fetch["markdown"] and fetch["screenshot"]
    async with MrScraperScraper() as scraper:
        response = await scraper.scrape(
            ScrapeRequest(
                target=Target.model_validate(
                    {
                        "id": "example",
                        "name": "Example",
                        "url": "https://example.com/list",
                        "category": "test",
                    }
                )
            )
        )
    assert response.error is None and response.status_code == 200 and response.html
    os.environ["MRSCRAPER_API_KEY"] = "invalid-synthetic-key"
    async with MrScraperClient() as client:
        try:
            await client.account()
        except MrScraperError as exc:
            assert str(exc) == "MrScraper HTTP 401"
        else:
            raise AssertionError("Invalid credentials were accepted")
    print("PASS: Account, webSearch, HTML/Markdown/screenshot, adapter, HTTP 401")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simulation-url", required=True)
    asyncio.run(smoke(parser.parse_args().simulation_url))
