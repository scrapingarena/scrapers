from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scrapingarena.merging import merge_reports
from scrapingarena.models import BenchmarkReport, RunMetadata, ScraperSummary


def _write_report(path: Path, report: BenchmarkReport) -> Path:
    path.write_text(report.model_dump_json(), encoding="utf-8")
    return path


@pytest.fixture
def benchmark_report() -> BenchmarkReport:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    return BenchmarkReport(
        metadata=RunMetadata(
            run_id="shard",
            started_at=timestamp,
            finished_at=timestamp,
            git_sha="abc123",
            runner="test",
            target_set_sha256="targets-sha",
        ),
        summaries=[
            ScraperSummary(
                benchmark="fake-direct",
                scraper="fake",
                proxy_provider=None,
                total=0,
                success=0,
                blocked=0,
                failed=0,
                ambiguous=0,
                success_rate=0,
                median_success_ms=None,
            )
        ],
        results={"fake-direct": []},
    )


def test_merge_reports_combines_scraper_shards(
    tmp_path: Path,
    benchmark_report: BenchmarkReport,
) -> None:
    first = deepcopy(benchmark_report)
    second = deepcopy(benchmark_report)
    first.summaries[0].benchmark = "alpha-direct"
    first.summaries[0].scraper = "alpha"
    first.results = {"alpha": next(iter(first.results.values()))}
    second.summaries[0].benchmark = "beta-direct"
    second.summaries[0].scraper = "beta"
    second.results = {"beta": next(iter(second.results.values()))}

    merged = merge_reports(
        [
            _write_report(tmp_path / "alpha.json", first),
            _write_report(tmp_path / "beta.json", second),
        ],
        run_id="actions-123-1",
    )

    assert merged.metadata.run_id == "actions-123-1"
    assert list(merged.results) == ["alpha", "beta"]
    assert [summary.benchmark for summary in merged.summaries] == [
        "alpha-direct",
        "beta-direct",
    ]


def test_merge_reports_rejects_duplicate_scrapers(
    tmp_path: Path,
    benchmark_report: BenchmarkReport,
) -> None:
    paths = [
        _write_report(tmp_path / "one.json", benchmark_report),
        _write_report(tmp_path / "two.json", benchmark_report),
    ]

    with pytest.raises(ValueError, match="duplicate scraper"):
        merge_reports(paths)
