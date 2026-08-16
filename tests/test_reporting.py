from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from scrapingarena.models import BenchmarkReport, RunMetadata
from scrapingarena.reporting import write_report


def _report(run_id: str) -> BenchmarkReport:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    return BenchmarkReport(
        metadata=RunMetadata(
            run_id=run_id,
            started_at=timestamp,
            finished_at=timestamp,
            runner="test",
            target_set_sha256="targets-sha",
        ),
        summaries=[],
        results={},
    )


def test_index_retains_unlimited_run_history(tmp_path: Path) -> None:
    for number in range(105):
        write_report(_report(f"run-{number}"), tmp_path)

    index = json.loads((tmp_path / "index.json").read_text())

    assert len(index["runs"]) == 105
    assert index["runs"][0]["run_id"] == "run-104"
    assert index["runs"][-1]["run_id"] == "run-0"


def test_index_replaces_an_existing_run_id(tmp_path: Path) -> None:
    write_report(_report("same-run"), tmp_path)
    write_report(_report("same-run"), tmp_path)

    index = json.loads((tmp_path / "index.json").read_text())

    assert [run["run_id"] for run in index["runs"]] == ["same-run"]
