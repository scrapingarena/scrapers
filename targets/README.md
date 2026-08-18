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
`cloudflare`, `akamai`, `datadome`, `human-security`, `imperva`, `fastly`,
`kasada`, and `unknown`. Set it from evidence — a bot-manager cookie or header
on a live request (`__cf_bm`, `_abck`, `datadome`, `_px`, `visid_incap`,
`x-kpsdk`) — not from what a vendor's case-study page claims. The CDN headers
that say who *delivers* a page (`cf-ray`, `x-served-by`, `x-akamai-*`) are not
evidence of bot defence.

After editing the array, validate it without making network requests:

```bash
uv run scrapingarena doctor
```

The canonical corpus requires exactly 100 unique IDs and 100 unique domains.
Every canonical target must name a protection provider and use a deep search,
shopping, listing, catalog, or product-result route. Unprotected sites,
homepages, news, and publishing pages are rejected: they tend to exercise
ordinary HTML delivery or CDN caching rather than behavioral defenses on
high-value dynamic pages. Keep queries read-only and deterministic; do not add
login, cart, checkout, or reservation flows.

**A target must return a record set somebody would pay to have.** Listings and
offers, search results, profiles and posts, reviews, jobs, properties,
vehicles, stays — the pages commercial scraping revenue actually concentrates
in. That rules out, in addition to the above:

- vendor marketing and product-overview pages (`/products`, `/features/...`),
- documentation and API references,
- blogs, tutorials, and resource libraries,
- template, integration, and app-directory galleries,
- reference and content pages whose data is published as a free dump or API
  (package registries, open map data, almanac and weather pages).

The test is not whether a page is dynamic or well defended — a marketing page
behind Akamai is still a marketing page. It is whether getting past the defence
would win you data worth the trouble.

For a quick run against the first few configured URLs:

```bash
uv run scrapingarena benchmark --scraper wreq --limit 5
```
