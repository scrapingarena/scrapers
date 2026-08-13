from __future__ import annotations

import json
from pathlib import Path

from scrapingarena.models import ScrapeRequest, ScrapeResponse, Target
from scrapingarena.reporting import write_report
from scrapingarena.runner import BenchmarkRunner
from scrapingarena.scrapers.base import BaseScraper, ScraperMetadata
from scrapingarena.validation.composite import CompositeValidator


class FakeScraper(BaseScraper):
    metadata = ScraperMetadata(
        slug="fake",
        name="Fake",
        kind="test",
        homepage="https://example.com",
    )

    async def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        return ScrapeResponse(
            requested_url=request.target.url_string,
            final_url=request.target.url_string,
            status_code=200,
            headers={
                "content-type": "text/html",
                "set-cookie": "secret=must-not-be-persisted",
            },
            html="<html><body>Expected useful body content.</body></html>",
            duration_ms=12,
        )


async def test_runner_scores_and_report_excludes_html_and_headers(
    tmp_path: Path,
) -> None:
    corpus = tmp_path / "targets.json"
    corpus.write_text("[]", encoding="utf-8")
    target = Target.model_validate(
        {
            "id": "example",
            "name": "Example",
            "url": "https://example.com/",
            "category": "test",
            "required_markers": ["Expected"],
            "min_visible_chars": 10,
        }
    )
    report = await BenchmarkRunner(
        CompositeValidator(),
        concurrency=1,
        retries=0,
    ).run([FakeScraper()], [target], targets_path=corpus)

    run_path, latest_path = write_report(report, tmp_path / "results")
    payload = latest_path.read_text(encoding="utf-8")
    parsed = json.loads(payload)

    assert report.summaries[0].success_rate == 100
    assert run_path.is_file()
    assert "must-not-be-persisted" not in payload
    assert "<html>" not in payload
    assert (
        parsed["results"]["fake"][0]["attempts"][0]["validation"]["verdict"]
        == "success"
    )
