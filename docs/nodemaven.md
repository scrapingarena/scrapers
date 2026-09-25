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

## Manual GitHub tests without publishing

Once `.github/workflows/benchmark-test.yml` is on the default branch, open
**Actions → Benchmark test (no publishing) → Run workflow**.

- **scrapers**: defaults to `all`; optionally choose slugs such as `wreq,curl-cffi`.
- **proxies**: defaults to `nodemaven-filtered,nodemaven-unfiltered`. You can also
  select `direct` and `oxylabs`, alone or in a comma-separated combination.
- **limit**: blank by default, running the full target corpus for every scraper.
  Optionally enter a target limit for a smaller run.

The same NodeMaven secrets are used for both variants. The test requires country
and sticky-session fields in the username, removes any existing `-filter-...`
field, and adds `-filter-medium` only for the filtered variant. Country and
session remain unchanged, so this does not guarantee different exit IPs between
variants. Each combination gets a separately named job with its result in the
Actions log.

This workflow runs only on manual dispatch or the explicit PR label below,
has read-only repository permissions, and has
no aggregation, commit, push, or result artifact upload. Reports are written to
a temporary directory and removed when execution finishes, including on failure.
GitHub still retains normal workflow logs and dependency/browser caches. The
regular publishing benchmark workflow remains separate.

### Run before merging

Push the workflow and scripts to a branch in this repository and open a PR
(a draft PR works). Create the repository label `benchmark-test` if needed,
then apply it to the PR. This starts the test without merging. Fork PRs are
excluded because the test requires repository secrets.

The label trigger runs all scrapers, both NodeMaven filtering variants, and
the full target corpus by default. To change those selections before merging, edit `PR_TEST_SCRAPERS`,
`PR_TEST_PROXIES`, and `PR_TEST_LIMIT` in the workflow on your branch and push.
Remove and reapply the label to start another run; ordinary pushes do not
start this benchmark.

Find results under the PR's Checks tab or Actions, open the benchmark job,
and expand **Run temporary benchmark**. Results are printed in logs; no
benchmark records or result artifacts are published.
