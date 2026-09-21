# Contributing to ScrapingArena

Thanks for helping make scraper benchmarks something people can actually
verify. Contributions are welcome from everyone — **including vendors
benchmarking their own product.** That's not a loophole; it's the design. An
adapter cannot influence its own score, so the people who know a tool best are
the right people to integrate it.

## What to contribute

| I want to… | Start here |
| --- | --- |
| Add a scraper | [docs/adding-a-scraper.md](docs/adding-a-scraper.md) |
| Add a proxy provider | [docs/adding-a-proxy-provider.md](docs/adding-a-proxy-provider.md) |
| Propose or fix a target | [targets/README.md](targets/README.md) |
| Report a misjudged page | Issue → *Validation result* |
| Fix a bug or improve docs | Straight to a PR |
| Understand the system first | [docs/architecture.md](docs/architecture.md) |

Open an issue before starting anything large. A short conversation is cheaper
than a rewritten PR.

## The rules that keep this fair

Non-negotiable, because they're what makes the numbers mean anything:

1. **An adapter fetches. It never decides whether it succeeded.** Scoring lives
   in the shared validator so no scraper grades itself.
2. **No per-target special-casing.** An adapter may not branch on a target's
   `id`, `name`, `url`, or domain. Anything that would fail if a target were
   renamed doesn't belong in an adapter.
3. **The runner owns retries.** Adapters don't retry internally — it would give
   them a bigger attempt budget than everyone else.
4. **Credentials never reach a report.** Not in errors, not in metadata, not in
   the corpus, not in logs.
5. **No live network in tests.** CI uses synthetic responses only.

## Development setup

Requires **Python 3.12+** and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/scrapingarena/scrapers.git
cd scrapers
uv sync --all-extras --dev
uv run scrapingarena doctor
uv run pytest
```

> **Exception:** `camoufox-original` conflicts with other Camoufox
> distributions — both import as `camoufox`. If you're touching those, use a
> dedicated environment instead of `--all-extras`.

Validation needs an OpenAI key. Without it, `doctor` and the tests still work;
`benchmark` won't start.

```bash
export OPENAI_API_KEY=...
uv run scrapingarena benchmark --scraper wreq --limit 5
```

Useful commands:

```bash
uv run scrapingarena scrapers                  # list adapter slugs
uv run scrapingarena scrapers --json           # machine-readable
uv run scrapingarena doctor                    # validate corpus, no network
python3 scripts/benchmark_ci.py matrix | python3 -m json.tool
```

## Required checks

Run all four before pushing — CI runs exactly these:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv run scrapingarena doctor
```

- **ruff** — line length 88, target py312, rules `E F I UP B SIM RUF`.
- **mypy** — `strict`, over `src` and `tests`. Libraries without stubs go in the
  override list in `pyproject.toml`.
- **pytest** — `asyncio_mode = "auto"`, so async tests need no decorator.

## Code style

The codebase has strong conventions. Match them:

- `from __future__ import annotations` at the top of every module.
- Modern typing: `X | None`, built-in generics, no `Optional`/`Dict`.
- Pydantic models use `ConfigDict(extra="forbid")` — be explicit about fields.
- Keyword-only arguments for anything that isn't obvious at the call site.
- **Comments explain *why*, not *what*.** The existing ones record hard-won
  reasons — why Steel needs one session, why timing is measured end-to-end, why
  Obscura's watchdog matters. If you worked something out the hard way, leave
  the reason behind; if the code is self-evident, don't narrate it.

## Testing

Tests use synthetic responses, never live sites. Live-site tests would be slow,
flaky, rude to the sites, and would make your PR's outcome depend on whether an
anti-bot vendor was having a bad day.

New adapters should cover: a successful response, a transport failure producing
a populated `error` rather than an exception, proxy forwarding when
`supports_proxy` is set, and resource cleanup. `tests/test_steel_scraper.py`
and `tests/test_native_browsers.py` are good models.

Fixtures are the right answer to a misjudged page: when you find a
classification that's wrong, add a case so it stays fixed.

## Pull requests

**Before opening:**

- [ ] All five checks pass locally.
- [ ] Tests added or updated, using synthetic responses.
- [ ] Docs updated — new adapter means a row in `docs/scrapers.md`.
- [ ] No `results/` changes committed. That directory is written by CI.
- [ ] No credentials, tokens, or `.env` files.
- [ ] Smoke run output included, if you added an adapter.

**In the description:** say what you changed and why, and paste the output of
any smoke run. For an adapter, include both `--proxy direct --limit 5` and,
where supported, `--proxy oxylabs --limit 5`.

Keep PRs focused. An adapter, a provider, and a corpus change are three PRs.

**What review will look at:** whether the adapter only fetches; whether
cleanup is complete and bounded; whether credentials can leak into reports or
logs; whether optional dependencies are imported lazily; whether the CI matrix
entry matches the registry.

## Adding or changing targets

The corpus is deliberately hard to change — it's the benchmark's control
variable, and its hash is recorded in every report. Read
[targets/README.md](targets/README.md) for the full criteria before proposing
one.

The short version: 100 entries, one URL per domain, deep routes only, and a
target must return **a record set somebody would pay to have**. Listings,
offers, search results, profiles, reviews, jobs, properties, vehicles, stays.
Not marketing pages, docs, blogs, or anything whose data is already published
as a free dump. A marketing page behind Akamai is still a marketing page.

Also: confirm the URL is public and suitable for automated requests, review the
site's terms and robots policy, keep concurrency and retries conservative, and
prefer a controlled test page when a production site disallows benchmarking.

## Reporting a misjudged page

Validation errors are useful bug reports. Include the target id, the scraper
and variant, the run id, what the validator decided, and what the page actually
was. Then add a fixture if you can.

## Licensing

By contributing, you agree your contributions are licensed under the
[MIT License](LICENSE).

## Conduct and security

Be decent — see [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). For vulnerabilities,
use GitHub's private reporting rather than a public issue; see
[SECURITY.md](SECURITY.md).
