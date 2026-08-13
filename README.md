
# ScrapingArena benchmark

Reproducible, serverless benchmarks for Python web scrapers. The suite runs the
same 100 public URLs through every scraper adapter, validates whether the
returned HTML is real page content or a block/challenge page, and publishes
machine-readable results from GitHub Actions.

## Quick start

```bash
uv sync --all-extras --dev
uv run scrapingarena doctor
uv run scrapingarena benchmark --scraper wreq --limit 5
uv run pytest
```

Results are written to `results/runs/<run-id>.json` and
`results/latest.json`. Raw HTML is deliberately not persisted: it can contain
copyrighted content, session data, or identifiers.

List registered adapters for a person or an Actions matrix:

```bash
uv run scrapingarena scrapers
uv run scrapingarena scrapers --json
```

Run one adapter into an isolated shard and combine independently produced
shards into a canonical report:

```bash
uv run scrapingarena benchmark \
  --scraper wreq --concurrency 10 --output-dir shard-results/wreq
uv run scrapingarena merge shard-results/*/latest.json \
  --run-id local-combined --output-dir results
```

## Architecture

```text
targets/targets.json                   versioned 100-URL corpus
src/scrapingarena/scrapers/            scraper adapters
src/scrapingarena/validation/          deterministic + optional LLM validation
src/scrapingarena/runner.py            concurrency, retries, orchestration
src/scrapingarena/reporting.py         stable JSON reports and aggregation
.github/workflows/benchmark.yml        scheduled/manual benchmark + commit
```

Each adapter implements `BaseScraper` and returns a normalized
`ScrapeResponse`. It must fetch, not decide whether it succeeded. Validation is
kept separate so every scraper is scored by exactly the same rules.

The `wreq` adapter uses
[`wreq`](https://github.com/0x676e67/wreq-python). It does not add or override
request headers. At startup it selects the numerically newest `Chrome*`
emulation profile exposed by the installed, locked `wreq` release, so a
dependency upgrade automatically advances the browser profile.

### Included scrapers

| Slug | Runtime | Local setup |
| --- | --- | --- |
| `wreq` | Python HTTP client | `uv sync` |
| `curl-cffi` | Python HTTP client | `uv sync --extra curl-cffi` |
| `obscura` | CDP browser service | `uv sync --extra cdp` + Docker Compose profile |
| `lightpanda` | CDP browser service | `uv sync --extra cdp` + Docker Compose profile |
| `steel` | Browser API service | `uv sync --extra steel` + Docker Compose profile |
| `cloakbrowser` | Packaged Chromium | `uv sync --extra cloakbrowser`, then `uv run python -m cloakbrowser install` |
| `camoufox-original` | Packaged Firefox fork | `uv sync --extra camoufox-original`, then `uv run python -m camoufox fetch` |
| `camoufox-fork` | CloverLabs wrapper + prerelease browser | `uv sync --extra camoufox-fork`, then select `official/prerelease` and fetch |
| `shardbrowser` | ShardX packaged Chromium | `uv sync --extra shardbrowser`; runtime downloads on first use |

Start one of the service-backed browsers locally, then run its adapter:

```bash
docker compose -f compose.browsers.yml --profile obscura up -d obscura
uv sync --extra cdp
uv run scrapingarena benchmark --scraper obscura --limit 5 --concurrency 2
docker compose -f compose.browsers.yml --profile obscura down
```

Replace `obscura` with `lightpanda` for the other CDP service. Steel listens on
port 3000 and uses its SDK instead:

```bash
docker compose -f compose.browsers.yml --profile steel up -d steel
uv sync --extra steel
uv run scrapingarena benchmark --scraper steel --limit 5 --concurrency 2
docker compose -f compose.browsers.yml --profile steel down
```

Camoufox's two distributions both import as `camoufox`, so never install their
extras together. The Actions matrix gives each one a separate environment.
CloakBrowser and ShardBrowser download browser runtimes into local caches.
ShardBrowser uses the `linux-gt1030` fingerprint by default; set
`SHARDX_PROFILE` to select another bundled template.
CloakBrowser's free binary permits one concurrent session; its Actions shard is
therefore fixed at concurrency 1. Other local browser shards should start at
concurrency 2–4 and be increased only after checking memory use.

### Add a scraper

1. Add `src/scrapingarena/scrapers/<name>.py`.
2. Subclass `BaseScraper` and implement `scrape()`.
3. Register one factory in `scrapers/registry.py`.
4. Add adapter tests using synthetic responses; do not hit live sites in CI.

Adapters can read credentials from environment variables. Never put credentials
in the target corpus, reports, or adapter metadata.

## Validation

`CompositeValidator` evaluates evidence in descending order of reliability:

1. transport failures and authoritative response headers;
2. HTTP status and redirect behavior;
3. known challenge/block-page HTML signatures;
4. visible-content size, title, and target-specific required/forbidden markers;
5. optional OpenAI adjudication for otherwise ambiguous HTML.

The default is deterministic and has no API cost:

```bash
uv run scrapingarena benchmark --validator deterministic
```

To adjudicate only ambiguous responses with structured output:

```bash
export OPENAI_API_KEY=...
uv sync --extra openai
uv run scrapingarena benchmark --validator openai
```

The model is configured with `SCRAPINGARENA_OPENAI_MODEL` and defaults to
`gpt-5.6-luna`. An LLM decision never overrides hard response-header, status, or
known challenge-signature evidence.

No detector is literally bulletproof. Block pages change, some sites return
legitimate short pages, and geo/consent/login pages can be domain content but
still wrong for a benchmark. Keep target expectations specific and add a
fixture whenever a false classification is found.

## Target corpus

[`targets/targets.json`](targets/targets.json) is the editable URL configuration
and contains exactly 100 distinct domains. See
[`targets/README.md`](targets/README.md) for the entry schema and editing
guidance. `protection` is a
benchmark stratum, not a claim that a vendor is always active; protection can
change by region, traffic, and time. Before publishing scores:

- confirm the URL is public and suitable for automated requests;
- review the site's terms and robots policy;
- keep concurrency and retry limits conservative;
- use a controlled test page when a production site disallows benchmarking;
- update `required_markers` when the intended page changes.

Use `uv run scrapingarena doctor` to validate corpus invariants without making
network requests.

## GitHub Actions and reporting

The benchmark workflow runs weekly and on `workflow_dispatch`. It discovers
registered adapters through the CLI, runs one matrix job per adapter, and
merges their artifacts. A full run commits the combined report to the branch
selected for the workflow dispatch; limited smoke runs only upload artifacts.
Full runs update:

- `results/latest.json` — stable URL for the frontend;
- `results/runs/<run-id>.json` — immutable run history;
- `results/index.json` — lightweight list of recent runs.

The workflow needs repository `contents: write`. Add `OPENAI_API_KEY` only if
the optional validator is enabled. Git history is the public, durable result
store; artifacts are the debugging/download copy. A later frontend deployment
can fetch `results/latest.json` from GitHub without a database or server.

Scheduled Actions may be delayed and, for inactive public repositories, can be
disabled by GitHub. The manual trigger remains available.
