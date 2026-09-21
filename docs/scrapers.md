# Scraper catalog

Every registered adapter, how to run it locally, and the constraints that
affect how its numbers should be read. Slugs are what you pass to `--scraper`.

All adapters support external proxies. Every one is benchmarked both `direct`
and `oxylabs`, and all published configurations run at **concurrency 1**.

| Slug | Name | Family | Local setup |
| --- | --- | --- | --- |
| [`wreq`](#wreq) | wreq | HTTP | `uv sync` |
| [`curl-cffi`](#curl-cffi) | curl_cffi | HTTP | `uv sync --extra curl-cffi` |
| [`niquests`](#niquests) | Niquests | HTTP | `uv sync --extra niquests` |
| [`camoufox-original`](#camoufox-original) | Camoufox (original) | Anti-bot browser | `uv sync --extra camoufox-original` + fetch |
| [`cloakbrowser`](#cloakbrowser) | CloakBrowser | Anti-bot browser | `uv sync --extra cloakbrowser` + install |
| [`fortress`](#fortress) | Fortress | Anti-bot browser | `uv sync --extra cdp` + Docker |
| [`patchright`](#patchright) | Patchright | Anti-bot browser | `uv sync --extra patchright` + Chrome |
| [`shardbrowser`](#shardbrowser) | ShardBrowser (ShardX) | Anti-bot browser | `uv sync --extra shardbrowser` |
| [`lightpanda`](#lightpanda) | Lightpanda | Agent browser | `uv sync --extra cdp` + Docker |
| [`moli`](#moli) | Moli | Agent browser | `uv sync` + installer |
| [`obscura`](#obscura) | Obscura | Agent browser | `uv sync --extra cdp` + Docker |
| [`steel`](#steel) | Steel Browser | Agent browser | `uv sync --extra steel` + Docker |
| [`vercel-agent-browser`](#vercel-agent-browser) | Vercel Agent Browser | Agent browser | Node 24 + npm install |

> The `kind` in adapter metadata (`http`, `antibot-browser`, `agent-browser`)
> is what the website displays. The grouping in `benchmark-scrapers.json`
> (`http`, `browser`, `agent`) organizes CI. They don't have to agree.

Every run below needs `OPENAI_API_KEY` exported for validation.

---

## HTTP clients

### wreq

[`wreq`](https://github.com/0x676e67/wreq-python). Rust-backed client with TLS
and HTTP/2 emulation.

```bash
uv sync
uv run scrapingarena benchmark --scraper wreq --limit 5
```

It **does not add or override request headers**. At startup it selects the
numerically newest `Chrome*` emulation profile the installed, locked release
exposes, so bumping the dependency advances the browser profile automatically.
The emulation profile owns the complete fingerprint, headers included, so
adding headers on top would desynchronize it.

### curl-cffi

[`curl_cffi`](https://github.com/lexiforest/curl_cffi). Curl-impersonate
bindings, using the `chrome` impersonation target.

```bash
uv sync --extra curl-cffi
uv run scrapingarena benchmark --scraper curl-cffi --limit 5
```

### niquests

[`Niquests`](https://github.com/jawah/niquests). A `requests`-compatible client
with HTTP/2 and HTTP/3.

```bash
uv sync --extra niquests
uv run scrapingarena benchmark --scraper niquests --limit 5
```

---

## Anti-bot browsers

### camoufox-original

[Camoufox](https://github.com/daijro/camoufox). A Firefox fork with
fingerprint injection below the JS layer.

```bash
uv sync --extra camoufox-original
uv run python -m camoufox fetch
uv run scrapingarena benchmark --scraper camoufox-original --limit 5
```

> **Camoufox distributions both import as `camoufox`.** Never install their
> extras together. They shadow each other, and you end up benchmarking
> whichever won. CI gives each one a separate environment.

On Linux, run under `xvfb-run -a`.

### cloakbrowser

[CloakBrowser](https://github.com/CloakHQ/CloakBrowser). Packaged Chromium.

```bash
uv sync --extra cloakbrowser
uv run python -m cloakbrowser install
xvfb-run -a uv run scrapingarena benchmark --scraper cloakbrowser --limit 5
```

**The free binary permits one concurrent session,** so its CI shard is fixed at
concurrency 1. CI also sets `CLOAKBROWSER_AUTO_UPDATE=false` to keep runs
reproducible.

### fortress

[Fortress](https://github.com/tiliondev/fortress). Official container driven
over its raw CDP endpoint. Pinned to image tag `149`.

```bash
docker run -d --name scrapingarena-browser --shm-size=2g \
  -p 127.0.0.1:9222:9222 tilion/fortress:149
uv sync --extra cdp
uv run scrapingarena benchmark --scraper fortress --limit 5
docker rm -f scrapingarena-browser
```

Endpoint override: `FORTRESS_CDP_URL` (default `http://127.0.0.1:9222`).

> Fortress has no `compose.browsers.yml` profile, so use `docker run` as above.

### patchright

[Patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright). A patched
Playwright driver against real Google Chrome, using upstream's recommended
headed persistent context with **no viewport override**. Each attempt gets a
fresh temporary profile; no custom fingerprint headers are injected.

```bash
uv sync --locked --extra patchright
uv run patchright install --with-deps chrome
xvfb-run -a uv run python scripts/smoke_browser.py --scraper patchright
xvfb-run -a uv run scrapingarena benchmark --scraper patchright --proxy direct
```

On macOS, drop `xvfb-run -a` and Chrome opens normally. Credentials and routing
options pass to Patchright unchanged. The driver and browser close after every
attempt.

### shardbrowser

[ShardBrowser](https://github.com/ProxyShard/ShardBrowser). ShardX packaged
Chromium; the runtime downloads on first use.

```bash
uv sync --extra shardbrowser
xvfb-run -a uv run scrapingarena benchmark --scraper shardbrowser --limit 5
```

Defaults to the `linux-gt1030` fingerprint. Set `SHARDX_PROFILE` for another
bundled template.

---

## Agent and service browsers

### lightpanda

[Lightpanda](https://github.com/lightpanda-io/browser). A lightweight browser
built for automation, driven over CDP.

```bash
docker compose -f compose.browsers.yml --profile lightpanda up -d lightpanda
uv sync --extra cdp
uv run scrapingarena benchmark --scraper lightpanda --limit 5 --concurrency 1
docker compose -f compose.browsers.yml --profile lightpanda down
```

Proxied runs pass the upstream proxy to the server as `--http-proxy` at
container start, so the value is redacted from CI logs.

### moli

[Moli](https://github.com/lexmount/moli). Native CLI, pinned to 1.1.9, run
as a fresh child process for every attempt. Returns JSON with rendered HTML,
headers, status, and final URL.

```bash
uv sync --locked
uv run python scripts/install_moli.py
uv run python scripts/smoke_browser.py --scraper moli
uv run scrapingarena benchmark --scraper moli --proxy direct
```

The installer downloads the pinned official Linux/macOS binary to
`~/.cache/scrapingarena/moli/1.1.9/moli`. Override with
`SCRAPINGARENA_MOLI_BINARY`. No browser service or Playwright needed.

> **Resource comparisons need a caveat.** Moli runs in its default DOM-focused
> mode, with no layout/paint and no image/font/media loading. Its CPU and memory
> numbers are not directly comparable to Chrome-based browsers doing full
> rendering.

Uses DOMContentLoaded plus the same two-second rendering window as other
browser adapters. Oxylabs auth goes through an attempt-owned loopback bridge;
HTTPS uses CONNECT with TLS verification enabled. Timeouts terminate and reap
the child process.

### obscura

[Obscura](https://github.com/h4ckf0r0day/obscura). CDP browser service.

```bash
docker compose -f compose.browsers.yml --profile obscura up -d obscura
uv sync --extra cdp
uv run scrapingarena benchmark --scraper obscura --limit 5 --concurrency 1
docker compose -f compose.browsers.yml --profile obscura down
```

**Keep concurrency at 1.** Obscura pages share a V8 isolate. Each attempt uses
a disposable context; a failure discards the CDP connection and reconnects next
attempt, and connection failures are recorded per attempt.

Compose and CI set server-side budgets below the 30s client deadline:
navigation 20s, script 15s, fetch 10s, CDP command 25s. **The server watchdog
is essential:** cancelling a Playwright call cannot interrupt server-side
JavaScript, so without it a stuck page hangs the whole shard. The tradeoff is
intentional: long SPA loads are given up in exchange for bounded attempts.

The container pulls the current image and restarts on failure, picking up
upstream watchdog fixes. For reproducible runs, pin and record the tested image
digest.

For proxied local runs, export `OBSCURA_PROXY` **before** starting Compose,
then pass `--proxy oxylabs`.

Upstream docs:
[Playwright](https://github.com/h4ckf0r0day/obscura/blob/main/docs/Use-with-Playwright.md) ·
[environment variables](https://github.com/h4ckf0r0day/obscura/blob/main/docs/Environment-variables.md).

> A successful `/json/version` probe only proves discovery works. Use a small
> benchmark run to verify page creation and navigation. If it stalls:
> `docker compose -f compose.browsers.yml logs --tail 200 obscura`.

### steel

[Steel Browser](https://github.com/steel-dev/steel-browser). Browser API
service on port 3000, driven through its SDK rather than CDP.

```bash
docker compose -f compose.browsers.yml --profile steel up -d steel
uv sync --extra steel
uv run scrapingarena benchmark --scraper steel --limit 5 --concurrency 1
docker compose -f compose.browsers.yml --profile steel down
```

**The self-hosted container supports one active browser operation at a time,**
hence concurrency 1. CI waits for `/v1/health` before starting, and prints the
final container state plus the last 200 log lines so service failures are
diagnosable.

Steel uses its quick-scrape endpoint for both direct and proxied requests,
passing the provider URL through the endpoint's `proxyUrl` field. Base URL:
`STEEL_BASE_URL` (CI uses `http://127.0.0.1:3000`).

### vercel-agent-browser

[agent-browser](https://github.com/vercel-labs/agent-browser). Chrome driven
by agent-browser's native Rust daemon. No Playwright, and no LLM involved in
fetching. Pinned to **0.37.1**. Needs Node 24.

```bash
npm install --global agent-browser@0.37.1
agent-browser install --with-deps
uv run python scripts/smoke_vercel_agent_browser.py
uv run scrapingarena benchmark --scraper vercel-agent-browser --proxy direct
```

Proxied:

```bash
uv run python scripts/smoke_vercel_agent_browser.py --proxy oxylabs
uv run scrapingarena benchmark --scraper vercel-agent-browser --proxy oxylabs
```

Accepts `OXYLABS_PROXIES_USERNAME` / `OXYLABS_PROXIES_PASSWORD`, or the legacy
`OXYLABS_RESIDENTIAL_PROXIES_*` pair. The configured username and its routing
options are preserved exactly.

An attempt-owned loopback HTTP proxy bridge sends Basic proxy authentication
upstream, keeping credentials out of CLI arguments and out of Chrome. This
works around native 0.37.1 proxy-auth interception stalling `Page.navigate`.
HTTPS uses opaque CONNECT tunnels with TLS verification enabled; the bridge and
its connections close after each attempt.

Each attempt owns a fresh daemon and browser with an overall deadline and
bounded graceful cleanup followed by process termination. Those children are
included in the resource monitor.

> The integration speaks agent-browser's **version-specific** Unix socket JSON
> protocol. When bumping the pinned version, update it in both the workflow and
> `benchmark-scrapers.json`, then rerun the smoke checks.

Linux and macOS are supported. Set
`SCRAPINGARENA_VERCEL_AGENT_BROWSER_BINARY` to use a specific executable.

---

## Environment variables

| Variable | Used by | Purpose |
| --- | --- | --- |
| `OPENAI_API_KEY` | all | Required for validation. |
| `SCRAPINGARENA_OPENAI_MODEL` | validator | Override the judge model. |
| `OXYLABS_PROXIES_USERNAME` / `_PASSWORD` | proxied runs | Preferred credential pair. |
| `OXYLABS_RESIDENTIAL_PROXIES_USERNAME` / `_PASSWORD` | proxied runs | Legacy fallback. |
| `SCRAPINGARENA_RUN_ID` | reporting | Pin the run id instead of generating one. |
| `SCRAPINGARENA_RESOURCE_CONTAINER` | resources | Docker container to include in sampling. |
| `SCRAPINGARENA_CDP_ENDPOINT` | CDP adapters | Default CDP endpoint. |
| `FORTRESS_CDP_URL` | fortress | Fortress CDP endpoint. |
| `STEEL_BASE_URL` | steel | Steel API base URL. |
| `OBSCURA_PROXY` | obscura | Upstream proxy, set before container start. |
| `SHARDX_PROFILE` | shardbrowser | Bundled fingerprint template. |
| `CLOAKBROWSER_AUTO_UPDATE` | cloakbrowser | CI sets `false` for reproducibility. |
| `SCRAPINGARENA_MOLI_BINARY` | moli | Explicit Moli executable. |
| `SCRAPINGARENA_VERCEL_AGENT_BROWSER_BINARY` | vercel-agent-browser | Explicit agent-browser executable. |

## Local browser services

`compose.browsers.yml` ships profiles for `obscura`, `lightpanda`, and `steel`:

```bash
docker compose -f compose.browsers.yml --profile <name> up -d <name>
docker compose -f compose.browsers.yml --profile <name> down
```

CI uses the equivalent `docker run` lines from `benchmark-scrapers.json`
instead, naming the container `scrapingarena-browser` so resource sampling and
failure diagnostics can find it.
