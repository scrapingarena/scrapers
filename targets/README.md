# Benchmark targets

[`targets.json`](targets.json) is the single source of truth for benchmark URLs.
Every registered scraper receives these entries in the same order.

Each entry has this shape:

```json
{
  "id": "example",
  "name": "Example Domain",
  "url": "https://example.com/",
  "category": "reference",
  "protection": "none",
  "required_markers": ["Example Domain"],
  "forbidden_markers": [],
  "min_visible_chars": 50
}
```

- `id`: stable lowercase identifier used in reports.
- `name`: human-readable label.
- `url`: public URL to request. The corpus permits one URL per domain.
- `category`: grouping label for later breakdowns.
- `protection`: expected anti-bot provider. This is descriptive metadata, not
  part of the success decision.
- `required_markers`: text where at least one marker should appear in a valid
  page.
- `forbidden_markers`: text that indicates the wrong page when present.
- `min_visible_chars`: minimum useful visible-text length.

`protection`, `required_markers`, `forbidden_markers`, and
`min_visible_chars` have defaults, but explicit values are preferable for
published benchmark targets. Supported protection values are `none`,
`cloudflare`, `akamai`, `datadome`, `human-security`, `imperva`, `fastly`, and
`unknown`.

After editing the array, validate it without making network requests:

```bash
uv run scrapingarena doctor
```

The canonical corpus currently requires exactly 100 unique IDs and 100 unique
domains. For a quick run against the first few configured URLs:

```bash
uv run scrapingarena benchmark --scraper wreq --limit 5
```
