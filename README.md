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

Run the same scraper through Oxylabs by setting its credentials and selecting
the provider explicitly:

```bash
export OXYLABS_RESIDENTIAL_PROXIES_USERNAME=...
export OXYLABS_RESIDENTIAL_PROXIES_PASSWORD=...
uv run scrapingarena benchmark --scraper wreq --proxy oxylabs --limit 5
```

The default is `--proxy direct`, so merely having proxy credentials in the
environment never changes a direct benchmark.

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
benchmark-scrapers.json                Actions runtime matrix
scripts/benchmark_ci.py                CI setup and execution driver
src/scrapingarena/scrapers/            scraper adapters
src/scrapingarena/validation/          OpenAI binary success validation
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

| Slug                | Runtime                  | Local setup                                                                  |
| ------------------- | ------------------------ | ---------------------------------------------------------------------------- |
| `wreq`              | Python HTTP client       | `uv sync`                                                                    |
| `curl-cffi`         | Python HTTP client       | `uv sync --extra curl-cffi`                                                  |
| `niquests`          | Python HTTP client       | `uv sync --extra niquests`                                                   |
| `obscura`           | CDP browser service      | `uv sync --extra cdp` + Docker Compose profile                               |
| `lightpanda`        | CDP browser service      | `uv sync --extra cdp` + Docker Compose profile                               |
| `steel`             | Browser API service      | `uv sync --extra steel` + Docker Compose profile                             |
| `cloakbrowser`      | Packaged Chromium        | `uv sync --extra cloakbrowser`, then `uv run python -m cloakbrowser install` |
| `camoufox-original` | Packaged Firefox fork    | `uv sync --extra camoufox-original`, then `uv run python -m camoufox fetch`  |
| `shardbrowser`      | ShardX packaged Chromium | `uv sync --extra shardbrowser`; runtime downloads on first use               |

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
uv run scrapingarena benchmark --scraper steel --limit 5 --concurrency 1
docker compose -f compose.browsers.yml --profile steel down
```

The self-hosted Steel container supports one active browser operation at a
time, so its benchmark configuration deliberately uses concurrency 1. CI waits
for `/v1/health` before starting and prints the final container state plus the
last 200 log lines to make browser-service failures diagnosable.

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
4. Add its runtime settings to `benchmark-scrapers.json`.
5. Add adapter tests using synthetic responses; do not hit live sites in CI.

The JSON groups adapters as `http`, `browser`, or `agent`. Every entry declares
its install command, benchmark command, cache paths, setup and service commands,
health URL, positive concurrency, and a `proxy_providers` list. The CI driver
expands that list into isolated variants such as `wreq-direct` and
`wreq-oxylabs`; adding another supported provider to an adapter is one config
entry. The small CI driver handles dependency
installation, optional runtime setup, services, health checks, and concurrency.
The Actions workflow only creates the matrix and invokes that driver.

Adapters can read credentials from environment variables. Never put credentials
in the target corpus, reports, or adapter metadata.

### Add a proxy provider

Proxy benchmarks are explicit variants. A direct run is named
`<scraper>-direct`; a proxied run is named `<scraper>-<provider>`. Each variant
runs in its own Actions job and produces its own shard, so aggregation retains
both results instead of replacing the direct result.

To add a provider:

1. Add its environment-variable loader to
   `src/scrapingarena/settings.py`. Keep the host, port, provider name, and
   public provider URL there, and read the username and password from the
   environment. Return `ProxySettings` for the new provider from
   `configured_proxy()`. Reject missing or partially configured credentials;
   never fall back to direct traffic for a requested provider.
2. Confirm that each adapter which will use the provider passes
   `request.proxy` to its underlying HTTP or browser client. Adding a provider
   to the matrix does not add proxy support to an adapter. At present,
   All current adapters support external proxy requests. Steel uses its quick
   scrape endpoint for direct requests and its session/CDP API for external
   proxies because the quick endpoint only exposes Steel-managed proxies.
3. Add the provider name to that adapter's `proxy_providers` list in
   `benchmark-scrapers.json`:

   ```json
   "proxy_providers": ["direct", "oxylabs", "new-provider"]
   ```

   Always retain `direct` so the benchmark measures the scraper both without
   and with a proxy. The CI driver expands this list into independent matrix
   entries such as `wreq-direct`, `wreq-oxylabs`, and
   `wreq-new-provider`.

4. Add a sibling provider job in `.github/workflows/benchmark.yml` so GitHub
   renders the provider as its own graph column. Add a provider-filtered output
   to `prepare`, point the job matrix at that output, and include the new job in
   `aggregate.needs`. The matrix command is:

   ```bash
   python3 scripts/benchmark_ci.py matrix --proxy new-provider
   ```

   Add the provider's credential names to that job's `env` block, sourcing
   their values from GitHub Actions secrets. For example:

   ```yaml
   env:
     NEW_PROVIDER_USERNAME: ${{ secrets.NEW_PROVIDER_USERNAME }}
     NEW_PROVIDER_PASSWORD: ${{ secrets.NEW_PROVIDER_PASSWORD }}
   ```

5. Create those repository secrets in GitHub under **Settings → Secrets and
   variables → Actions → New repository secret**. Secret names must exactly
   match the workflow references. Do not store credentials in
   `benchmark-scrapers.json`, workflow literals, committed `.env` files, or
   benchmark reports.
6. Add settings tests for complete credentials, missing credentials, unknown
   providers, and URL escaping. Run the Python checks and inspect the expanded
   matrix before opening a pull request:

   ```bash
   uv run ruff check src tests scripts
   uv run mypy src tests scripts
   uv run pytest
   python3 scripts/benchmark_ci.py matrix | python3 -m json.tool
   ```

To test a provider locally, export its credentials and select it explicitly:

```bash
export OXYLABS_RESIDENTIAL_PROXIES_USERNAME=...
export OXYLABS_RESIDENTIAL_PROXIES_PASSWORD=...
uv run scrapingarena benchmark --scraper wreq --proxy oxylabs --limit 5
```

Run the direct control separately:

```bash
uv run scrapingarena benchmark --scraper wreq --proxy direct --limit 5
```

Schema-v3 reports identify every result with its `benchmark` variant and also
store the underlying `scraper` and nullable `proxy_provider` separately. Proxy
credentials and authenticated proxy URLs must never be serialized. Provider
homepage URLs are public metadata and are safe to keep in configuration.

### Resource measurements

Schema-v3 reports measure CPU and memory for direct benchmark variants only.
The runner samples its process tree once per second; service-backed browser
jobs also include the `scrapingarena-browser` Docker container. Each direct
summary stores peak and average memory in MiB, peak and average CPU usage in
cores, wall-clock duration, and the full sample series. Proxy summaries set
`resources` to `null` because proxy latency would duplicate and distort the
scraper footprint measurement.

Full samples live in each run report. `results/index.json` deliberately omits
the sample arrays and retains only aggregate resource values, keeping the daily
history index small. The web app normalizes older schema-v1/v2 reports with
`resources: null`, so historical success charts continue to work and resource
charts begin at the first schema-v3 run.

## Validation

OpenAI independently classifies every scrape attempt with binary structured output:

```bash
export OPENAI_API_KEY=...
uv sync --extra openai
uv run scrapingarena benchmark
```

Every result goes directly to the model; there are no deterministic status,
anti-bot signature, or keyword rules. `OPENAI_API_KEY` is required.
The evidence includes filtered response metadata plus bounded samples from both
raw HTML and extracted visible text.

The model is configured with `SCRAPINGARENA_OPENAI_MODEL` and defaults to
`gpt-5.6-luna`.

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
