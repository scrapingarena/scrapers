# Adding a scraper

Adapters are welcome from anyone, including vendors adding their own product.
An adapter cannot influence its own score: it fetches, and shared code does the
rest.

Read [How it works](architecture.md) first if you haven't.

## The contract

```python
class BaseScraper(ABC):
    metadata: ScraperMetadata
    supports_proxy = False

    def __init__(self, proxy: ProxySettings | None = None) -> None: ...
    async def __aenter__(self) -> BaseScraper: ...
    async def __aexit__(self, *exc) -> None: ...  # calls close()
    async def close(self) -> None: ...
    async def scrape(self, request: ScrapeRequest) -> ScrapeResponse: ...
```

Your adapter must:

- return a `ScrapeResponse` describing what happened, success or not;
- release every resource it opens in `close()`;
- pass `request.proxy` to its client when it sets `supports_proxy = True`.

Your adapter must not:

- decide whether a response was a success, or set any verdict;
- retry, since the runner owns the retry budget;
- branch on a target's `id`, `name`, `url`, or domain;
- inject headers that mimic a browser its engine isn't. If the library owns a
  fingerprint, let it own the whole fingerprint.
- write files, or log credentials.

### Checklist

1. `src/scrapingarena/scrapers/<name>.py`, subclassing `BaseScraper`.
2. Register it in `scrapers/registry.py`.
3. Add an entry to `benchmark-scrapers.json`.
4. Add tests using synthetic responses. No live sites in CI.
5. Update `tests/test_registry.py`'s expected slug list.
6. Add a row to [`docs/scrapers.md`](scrapers.md).

## 1. Write the adapter

A complete HTTP adapter, which is most of what there is to it:

```python
from __future__ import annotations

import time
from typing import Any

from scrapingarena.models import ScrapeRequest, ScrapeResponse
from scrapingarena.scrapers.base import BaseScraper, ScraperMetadata
from scrapingarena.settings import ProxySettings


class ExampleScraper(BaseScraper):
    supports_proxy = True
    metadata = ScraperMetadata(
        slug="example",  # CLI slug, kebab-case
        name="Example",  # display name on the site
        kind="http",  # http | antibot-browser | agent-browser
        homepage="https://github.com/org/example",
    )

    def __init__(self, proxy: ProxySettings | None = None) -> None:
        super().__init__(proxy)
        try:
            from example_lib import AsyncSession
        except ImportError as exc:
            raise RuntimeError("example requires the 'example' project extra") from exc
        self._session: Any = AsyncSession()

    async def close(self) -> None:
        await self._session.close()

    async def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        started = time.perf_counter()
        try:
            response = await self._session.get(
                request.target.url_string,
                timeout=request.timeout_seconds,
                allow_redirects=True,
                proxy=request.proxy.url if request.proxy else None,
            )
            return ScrapeResponse(
                requested_url=request.target.url_string,
                final_url=str(response.url),
                status_code=response.status_code,
                headers={k.lower(): v for k, v in response.headers.items()},
                html=response.text,
                duration_ms=(time.perf_counter() - started) * 1000,
            )
        except Exception as exc:
            # A failed fetch is a result, not a crash. Report it.
            return ScrapeResponse(
                requested_url=request.target.url_string,
                duration_ms=(time.perf_counter() - started) * 1000,
                error=f"{type(exc).__name__}: {exc}",
            )
```

### Notes on the details

**Import the optional dependency inside `__init__`,** not at module level. The
registry imports every adapter module on startup, so a top-level import of an
optional package breaks `scrapingarena scrapers` for anyone who hasn't
installed that extra. Raise a `RuntimeError` naming the extra instead.

**Lowercase your header keys.** The validator looks up a fixed allow-list of
header names in lowercase.

**Return errors rather than raising them.** The runner does catch exceptions,
but an adapter that returns a populated `error` produces a cleaner message than
a stack-trace string.

**`duration_ms` is required but gets overwritten.** The runner replaces it with
its own end-to-end measurement so engine startup counts. Set it accurately
anyway, since it helps when debugging the adapter directly.

**Pin the fingerprint to the library.** `wreq_scraper.py` picks the numerically
newest `Chrome*` emulation profile the installed version exposes, so a
dependency bump advances the browser profile on its own. Prefer that over
hardcoding a version.

### Browser adapters

For a browser service driven over CDP, subclass `PlaywrightCdpScraper` instead.
It already handles connect, per-attempt context isolation, bounded cleanup, and
proxy plumbing, so the adapter is often just metadata:

```python
class FortressScraper(PlaywrightCdpScraper):
    metadata = ScraperMetadata(
        slug="fortress",
        name="Fortress",
        kind="antibot-browser",
        homepage="https://github.com/tiliondev/fortress",
    )
    endpoint_env = "FORTRESS_CDP_URL"
    default_endpoint = "http://127.0.0.1:9222"
```

For browsers launched as a child process, see `moli_scraper.py` and
`vercel_agent_browser_scraper.py`. Both give every attempt a fresh process with
an overall deadline and bounded graceful cleanup followed by termination. Child
processes are picked up automatically by the resource monitor.

### Proxy authentication

Some runtimes can't do authenticated proxies over CLI arguments, or stall on
auth interception. The approach used here is an attempt-owned loopback bridge:
a local HTTP proxy that adds Basic auth upstream, keeping credentials out of
process arguments, using opaque CONNECT tunnels for HTTPS with TLS verification
left on, and torn down after each attempt. See
[`vercel_agent_browser_proxy.py`](../src/scrapingarena/scrapers/vercel_agent_browser_proxy.py).

If your runtime handles authenticated proxies natively, pass
`request.proxy.url` and skip all of this.

## 2. Register it

```python
# src/scrapingarena/scrapers/registry.py
from scrapingarena.scrapers.example_scraper import ExampleScraper

_SCRAPERS: dict[str, ScraperFactory] = {
    scraper.metadata.slug: scraper
    for scraper in (
        ExampleScraper,
        ...,
    )
}
```

Add the dependency as an optional extra in `pyproject.toml` unless every
install genuinely needs it:

```toml
[project.optional-dependencies]
example = ["example-lib>=1,<2"]
```

If the library ships no type stubs, add it to the mypy override list at the
bottom of `pyproject.toml`.

## 3. Add the CI entry

```json
{
  "slug": "example",
  "install_command": "uv sync --locked --extra example",
  "benchmark_command": "uv run scrapingarena benchmark --scraper example",
  "cache_paths": [],
  "setup_commands": [],
  "service_commands": [],
  "health_url": "",
  "proxy_providers": ["direct", "oxylabs"],
  "concurrency": 1
}
```

Place it under `http`, `browser`, or `agent`. Keep `direct` in
`proxy_providers`, since the direct run is the control.

The tests check that every field is present, `concurrency` is positive,
`direct` is included, and `health_url` is non-empty whenever
`service_commands` is set.

Extra fields for heavier runtimes:

- Downloads a runtime? List its cache directory in `cache_paths` and do the
  download in `setup_commands`.
- Needs a display? Prefix `benchmark_command` with `xvfb-run -a` and install
  `xvfb` in `setup_commands`.
- Runs as a service? Put the `docker run` line in `service_commands`, name the
  container `scrapingarena-browser` so resource measurement and diagnostics can
  find it, and set `health_url`.

Then check the matrix expands:

```bash
python3 scripts/benchmark_ci.py matrix | python3 -m json.tool
```

## 4. Test it

Tests must use synthetic responses. CI never touches live sites: it would be
slow and flaky, it puts load on the target sites, and it would make a PR's
result depend on how an anti-bot vendor happened to be behaving that day.

```python
from scrapingarena.models import ScrapeRequest, Target
from scrapingarena.scrapers.example_scraper import ExampleScraper


class FakeResponse:
    url = "https://example.com/search?q=shoes"
    status_code = 200
    headers = {"Content-Type": "text/html"}
    text = "<html><body>result rows</body></html>"


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def get(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return FakeResponse()

    async def close(self) -> None: ...


async def test_normalizes_a_successful_response() -> None:
    scraper = ExampleScraper()
    scraper._session = FakeSession()

    target = Target(
        id="example",
        name="Example",
        url="https://example.com/search?q=shoes",
        category="marketplace",
    )
    response = await scraper.scrape(ScrapeRequest(target=target))

    assert response.status_code == 200
    assert response.error is None
    assert response.headers["content-type"] == "text/html"  # lowercased
```

Cover at least a successful response, a transport failure producing a populated
`error` rather than an exception, proxy URL forwarding when `supports_proxy` is
set, and cleanup in `close()`. `tests/test_steel_scraper.py` and
`tests/test_native_browsers.py` show the patterns.

Then update the expected slug list in `tests/test_registry.py`, which is
sorted.

## 5. Run the checks

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest
uv run scrapingarena doctor

export OPENAI_API_KEY=...
uv run scrapingarena benchmark --scraper example --limit 5
```

Include the smoke run's output in your PR. If your adapter supports proxies,
also run `--proxy oxylabs --limit 5` and say so.

Don't commit `results/` changes from a local run. CI writes that directory.

## Common review findings

| Problem | Fix |
| --- | --- |
| Optional dependency imported at module level | Import inside `__init__`, raise `RuntimeError` naming the extra. |
| Adapter returns early or marks its own success | Return the response and let the validator score it. |
| Adapter retries internally | Remove it. The runner does up to 4 attempts. |
| Browser or process leaks across attempts | Release everything in `close()`, bound the cleanup, then terminate. |
| `supports_proxy = True` but `request.proxy` unused | Pass it to the client, and add a test asserting it. |
| Header keys not lowercased | The validator's allow-list is lowercase. |
| Hardcoded browser version | Select the newest profile the installed library exposes. |
| `benchmark-scrapers.json` not updated | `tests/test_registry.py` fails. |

## Where to ask

If you aren't sure whether your tool fits, or how to model something unusual,
open an issue using the **New scraper** template before writing code.
