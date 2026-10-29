# MrScraper integration

ScrapingArena uses the REST API for reproducible benchmark runs. It needs an
API key in the local environment or the `MRSCRAPER_API_KEY` GitHub Actions
secret. The existing benchmark workflows pass that secret to all three variants.
Credentials are never CLI arguments or part of benchmark reports.

```bash
uv sync --locked --extra mrscraper
export MRSCRAPER_API_KEY="your-api-key"
```

Get a key from your [MrScraper account](https://app.mrscraper.com/api-tokens).
These utility commands print JSON and do not require `OPENAI_API_KEY`.

| Capability | CLI command | REST endpoint |
| --- | --- | --- |
| Account | `scrapingarena mrscraper account` | `GET https://api.app.mrscraper.com/api/v1/subscription-accounts` |
| scraperAPI | `scrapingarena mrscraper scraper-api URL` | `POST https://api.mrscraper.com/` |
| webSearch | `scrapingarena mrscraper web-search QUERY` | `POST https://sync.scraper.mrscraper.com/api/google/serp/v2/sync` |

## Account

```bash
uv run scrapingarena mrscraper account
```

Returns selected identity, verification, subscription, token usage, expiry,
renewal, and rate-limit fields. Remaining quota is calculated as
`max(0, tokenLimit - tokenUsage)` when both values are available. Unknown quota
stays `null`. Billing IDs and other raw account fields are excluded.

## scraperAPI

Fetch a public web page as rendered HTML, Markdown, a screenshot, or a combination.

```bash
uv run scrapingarena mrscraper scraper-api https://example.com --render-js
uv run scrapingarena mrscraper scraper-api https://example.com --markdown
uv run scrapingarena mrscraper scraper-api https://example.com --no-html --markdown
uv run scrapingarena mrscraper scraper-api https://example.com --markdown --screenshot
```

The response contains the requested `html`, `markdown`, and/or `screenshot`
fields. Screenshots are base64 JPEG strings in the JSON output. Browser fallback
is automatic; `--render-js` forces rendering, and screenshots always force it.
`--timeout` sets the total client deadline (default 120 seconds). Utility
fetches use MrScraper's managed proxy routing and perform no internal retries.

For benchmark scoring, use the registered adapter:

```bash
export OPENAI_API_KEY="your-validator-key"
uv run scrapingarena benchmark --scraper mrscraper --proxy direct --limit 5
uv run scrapingarena benchmark --scraper mrscraper --proxy oxylabs --limit 5
uv run scrapingarena benchmark --scraper mrscraper --proxy nodemaven --limit 5
```

The adapter always requests browser-rendered HTML. Direct runs disable the
service's proxy with `useProxy=false`; external variants forward the exact
provider credentials and routing options to the target-page proxy parameter.
The adapter does not retry, select search results, classify pages, or change
the shared corpus. The runner controls deadlines, concurrency, retries, and
scoring. API errors become failed attempt responses. Target status is read from
`X-Status-Code`; an absent status remains unknown. Local resource figures do
not include MrScraper's remote browsers.

## webSearch

Search the web to retrieve real-time results, including relevant website URLs,
titles, descriptions, and related questions based on a query.

```bash
uv run scrapingarena mrscraper web-search "web scraping"
uv run scrapingarena mrscraper web-search "web scraping" --region id --language id
uv run scrapingarena mrscraper web-search "web scraping" --page 2 --render-js
```

The REST call explicitly requests `format=json`. Results are in
`data.organic[]`, with `link`, `title`, and `description`. Related questions are
in `data.people_also_ask` when supplied. Pagination and other result sections
are preserved. The client checks both HTTP status and `success`.
`--timeout` defaults to 600 seconds. Search is a utility, not a benchmark
adapter: it does not substitute search snippets for the corpus page's HTML.

## MCP alternative

For interactive agent use, connect your MCP client to
`https://mcp.mrscraper.com/mcp` using its OAuth browser flow. The tools are
`status` (Account), `scraperAPI`, and `webSearch`. Authentication stays in the
MCP client. ScrapingArena's benchmark does not depend on an interactive MCP
session; installing this adapter does not change your MCP client configuration.

See the [official MCP reference](https://docs.mrscraper.com/docs/getting-started/mcp-server)
and [Scraper API documentation](https://docs.mrscraper.com/docs/getting-started/scraper-api).
The supplied API/MCP integration reference (20 October 2026) was used for the
REST account and response schemas; its proposal and contact instructions are
not part of this integration.

## Local verification

Unit tests use synthetic responses. A local Postman simulation under
`postman/` exercises the actual HTTP client without production credentials.
`MRSCRAPER_FETCH_URL`, `MRSCRAPER_SEARCH_URL`, and `MRSCRAPER_ACCOUNT_URL`
override the complete endpoint URLs for this purpose. Only point these at
trusted services: the client sends the configured API key to them.

```bash
postman simulation run postman/simulations/mrscraper.sim.yaml --port auto --no-history --output ndjson
# Use the member address printed in the listening event:
uv run python scripts/smoke_mrscraper.py --simulation-url http://localhost:PORT/mrscraper
```

The smoke command supplies synthetic credentials and checks all three APIs,
the benchmark adapter, and HTTP 401 handling. Stop the simulation with Ctrl-C.
It verifies HTTP integration; it does not measure live scraping performance.
