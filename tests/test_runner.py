from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar

import pytest

from scrapingarena.models import ScrapeRequest, ScrapeResponse, Target
from scrapingarena.reporting import write_report
from scrapingarena.runner import BenchmarkRunner
from scrapingarena.scrapers.base import BaseScraper, ScraperMetadata
from scrapingarena.settings import ProxySettings
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


class RetriedScraper(BaseScraper):
    metadata = ScraperMetadata(
        slug="retried",
        name="Retried",
        kind="test",
        homepage="https://example.com",
    )
    opened: ClassVar[int] = 0
    closed: ClassVar[int] = 0

    async def __aenter__(self) -> RetriedScraper:
        type(self).opened += 1
        return self

    async def close(self) -> None:
        type(self).closed += 1

    async def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        return ScrapeResponse(
            requested_url=request.target.url_string,
            status_code=500,
            duration_ms=1,
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
        parsed["results"]["fake-direct"][0]["attempts"][0]["validation"]["verdict"]
        == "success"
    )


async def test_runner_logs_and_reopens_scraper_for_three_retries(
    capsys: pytest.CaptureFixture[str],
) -> None:
    RetriedScraper.opened = 0
    RetriedScraper.closed = 0
    target = Target.model_validate(
        {
            "id": "example",
            "name": "Example",
            "url": "https://example.com/",
            "category": "test",
        }
    )

    report = await BenchmarkRunner(CompositeValidator(), concurrency=1, retries=3).run(
        [RetriedScraper()], [target]
    )

    assert len(report.results["retried-direct"][0].attempts) == 4
    assert RetriedScraper.opened == 4
    assert RetriedScraper.closed == 4
    output = capsys.readouterr().out
    assert "[retried-direct] example attempt 1/4 start" in output
    assert "[retried-direct] example attempt 4/4 result=failed status=500" in output


async def test_runner_benchmarks_each_proxy_provider() -> None:
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
    proxy = ProxySettings(
        host="proxy.example.com",
        port=8080,
        username="user",
        password="secret",
        provider_name="example-proxy",
        provider_url="https://example.com/proxy",
    )

    report = await BenchmarkRunner(CompositeValidator(), concurrency=1, retries=0).run(
        [FakeScraper()], [target], proxy=proxy
    )

    assert list(report.results) == ["fake-example-proxy"]
    assert report.summaries[0].benchmark == "fake-example-proxy"
    assert report.summaries[0].scraper == "fake"
    assert report.summaries[0].proxy_provider == "example-proxy"
