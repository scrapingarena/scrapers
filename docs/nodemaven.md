# NodeMaven residential proxies

NodeMaven runs as a separate `nodemaven` provider through `gate.nodemaven.com:8080`.
Each scraper gets a `<scraper>-nodemaven` result alongside its direct and Oxylabs
results. The workflow has a separate NodeMaven job group and aggregates its shards.

## Credentials and routing

Set these GitHub Actions repository secrets (or environment variables locally):

- `NODEMAVEN_USERNAME`: the full dashboard username, including country and session.
- `NODEMAVEN_PASSWORD`: the dashboard password.

For example, the username shape for US targeting and a sticky session is:

```text
<dashboard-username>-country-us-sid-<session-id>
```

You can include `-region-california` between the country and session fields to
narrow the location. Generate the username in the dashboard with your desired
country and sticky-session settings. Use a fresh session ID for a new independent
run; keep it unchanged within the run. The integration passes the username
verbatim to every adapter, retry, and upstream browser service. It does not
rotate sessions or extend the provider's session lifetime.

## Manual filtering comparison

For the filtered run, append `-filter-medium` to that username. For the unfiltered
run, remove that suffix. No filtering flag is added yet. Set the GitHub secret
before each workflow run, or change the local environment variable between runs.
Both runs use the `nodemaven` provider label, so retain their separate run artifacts
(or use different output directories locally) when comparing results.

```bash
export NODEMAVEN_USERNAME='<dashboard-username>-country-us-sid-<session-id>'
export NODEMAVEN_PASSWORD='<dashboard-password>'
uv run scrapingarena benchmark --scraper wreq --proxy nodemaven --limit 5
```

The benchmark also needs its usual validator configuration (`OPENAI_API_KEY`).
Missing or partial credentials fail rather than falling back to a direct request.
Credentials are URL-escaped for transport and redacted from reported errors.

## Code locations

- `src/scrapingarena/settings.py`: NodeMaven credentials and provider metadata.
- `scripts/benchmark_ci.py`: equivalent URL construction for service-backed browsers,
  available to system Python before dependencies are installed.
- `benchmark-scrapers.json`: enabled provider variants.
- `.github/workflows/benchmark.yml`: NodeMaven secrets, jobs, and aggregation.
