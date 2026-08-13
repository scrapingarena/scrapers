from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from scrapingarena.models import BenchmarkReport


def write_report(report: BenchmarkReport, output_dir: Path) -> tuple[Path, Path]:
    runs_dir = output_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    payload = report.model_dump_json(indent=2)
    run_path = runs_dir / f"{report.metadata.run_id}.json"
    latest_path = output_dir / "latest.json"
    _atomic_write(run_path, f"{payload}\n")
    _atomic_write(latest_path, f"{payload}\n")
    _update_index(output_dir / "index.json", report)
    return run_path, latest_path


def _update_index(path: Path, report: BenchmarkReport) -> None:
    if path.exists():
        index: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    else:
        index = {"schema_version": 1, "runs": []}

    run = {
        "run_id": report.metadata.run_id,
        "started_at": report.metadata.started_at.isoformat(),
        "summaries": [summary.model_dump(mode="json") for summary in report.summaries],
    }
    previous = [
        item
        for item in index.get("runs", [])
        if item.get("run_id") != report.metadata.run_id
    ]
    index["runs"] = [run, *previous][:100]
    _atomic_write(path, f"{json.dumps(index, indent=2)}\n")


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp-{os.getpid()}")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)
