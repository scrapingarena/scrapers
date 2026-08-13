from __future__ import annotations

from pathlib import Path

from scrapingarena.models import BenchmarkReport, RunMetadata, TargetResult


def merge_reports(paths: list[Path], *, run_id: str | None = None) -> BenchmarkReport:
    if not paths:
        raise ValueError("at least one report is required")

    reports = [
        BenchmarkReport.model_validate_json(path.read_text(encoding="utf-8"))
        for path in paths
    ]
    first = reports[0]
    results: dict[str, list[TargetResult]] = {}
    summaries = []

    for report in reports:
        if report.schema_version != first.schema_version:
            raise ValueError("cannot merge reports with different schema versions")
        if report.metadata.git_sha != first.metadata.git_sha:
            raise ValueError("cannot merge reports from different git SHAs")
        if report.metadata.target_set_sha256 != first.metadata.target_set_sha256:
            raise ValueError("cannot merge reports with different target sets")

        duplicate_scrapers = results.keys() & report.results.keys()
        if duplicate_scrapers:
            duplicates = ", ".join(sorted(duplicate_scrapers))
            raise ValueError(f"duplicate scraper reports: {duplicates}")

        results.update(report.results)
        summaries.extend(report.summaries)

    summaries.sort(key=lambda summary: summary.scraper)
    return BenchmarkReport(
        schema_version=first.schema_version,
        metadata=RunMetadata(
            run_id=run_id or first.metadata.run_id,
            started_at=min(report.metadata.started_at for report in reports),
            finished_at=max(report.metadata.finished_at for report in reports),
            git_sha=first.metadata.git_sha,
            runner="github-actions-matrix",
            target_set_sha256=first.metadata.target_set_sha256,
        ),
        summaries=summaries,
        results=dict(sorted(results.items())),
    )
