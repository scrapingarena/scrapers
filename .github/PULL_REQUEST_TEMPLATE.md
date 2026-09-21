## What and why

<!-- What changed, and what problem it solves. Link any related issue. -->

## Type of change

- [ ] New scraper adapter
- [ ] New proxy provider
- [ ] Target corpus change
- [ ] Bug fix
- [ ] Documentation
- [ ] Other

## Checks

```
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv run scrapingarena doctor
```

- [ ] All five pass locally
- [ ] Tests added or updated, using synthetic responses (no live sites)
- [ ] Docs updated where behavior changed
- [ ] No `results/` changes committed. CI writes that directory
- [ ] No credentials, tokens, or `.env` files

## For a new scraper

- [ ] Adapter only fetches: it doesn't score, retry, or special-case targets
- [ ] Optional dependency imported inside `__init__`, not at module level
- [ ] Registered in `scrapers/registry.py` and added to `tests/test_registry.py`
- [ ] Entry added to `benchmark-scrapers.json`
- [ ] Row added to `docs/scrapers.md`
- [ ] Resources released in `close()`

Smoke run output:

```
# uv run scrapingarena benchmark --scraper <slug> --proxy direct --limit 5
```

## For a new proxy provider

- [ ] `configured_proxy()` fails loudly on missing or partial credentials, never falling back to direct
- [ ] `redact()` covers the provider's username format
- [ ] Provider added to `proxy_url()` in `scripts/benchmark_ci.py`
- [ ] Sibling job added to `benchmark.yml` and included in `aggregate.needs`
- [ ] Settings tests cover complete, missing, partial, and unknown-provider cases
- [ ] Direct control run alongside the proxied run
