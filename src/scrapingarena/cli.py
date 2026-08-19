from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Annotated

import typer

from scrapingarena.merging import merge_reports
from scrapingarena.reporting import write_report
from scrapingarena.runner import BenchmarkRunner
from scrapingarena.scrapers.registry import create_scraper, scraper_names
from scrapingarena.settings import configured_proxy
from scrapingarena.targets import default_targets_path, load_targets
from scrapingarena.validation.base import Validator
from scrapingarena.validation.composite import CompositeValidator
from scrapingarena.validation.keyword_fallback import KeywordFallbackValidator

app = typer.Typer(
    no_args_is_help=True,
    help="Run and validate reproducible scraper benchmarks.",
)
DEFAULT_TARGETS_PATH = default_targets_path()


@app.command("scrapers")
def list_scrapers(
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Print a JSON array for automation."),
    ] = False,
) -> None:
    """List registered scraper adapter slugs."""
    names = scraper_names()
    typer.echo(json.dumps(names) if as_json else "\n".join(names))


@app.command()
def doctor(
    targets_path: Annotated[
        Path,
        typer.Option("--targets", exists=True, dir_okay=False),
    ] = DEFAULT_TARGETS_PATH,
) -> None:
    """Validate configuration without making network requests."""
    targets = load_targets(targets_path)
    typer.echo(
        f"OK: {len(targets)} unique targets; scrapers: {', '.join(scraper_names())}"
    )


@app.command()
def benchmark(
    scraper: Annotated[
        list[str] | None,
        typer.Option("--scraper", "-s", help="Adapter slug; repeat for multiple."),
    ] = None,
    validator: Annotated[
        str,
        typer.Option(help="deterministic or openai"),
    ] = "deterministic",
    openai_fallback: Annotated[
        bool,
        typer.Option(
            "--openai-fallback/--no-openai-fallback",
            envvar="SCRAPINGARENA_OPENAI_FALLBACK",
            help=(
                "Use HTML block keywords when OpenAI is selected but its key is absent."
            ),
        ),
    ] = True,
    targets_path: Annotated[
        Path,
        typer.Option("--targets", exists=True, dir_okay=False),
    ] = DEFAULT_TARGETS_PATH,
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", file_okay=False),
    ] = Path("results"),
    limit: Annotated[
        int | None,
        typer.Option(min=1, help="Run only the first N targets (smoke tests)."),
    ] = None,
    concurrency: Annotated[int, typer.Option(min=1, max=25)] = 5,
    retries: Annotated[int, typer.Option(min=0, max=5)] = 3,
    timeout: Annotated[float, typer.Option(min=1, max=120)] = 30,
    proxy: Annotated[
        str,
        typer.Option(help="Proxy provider: direct or oxylabs."),
    ] = "direct",
) -> None:
    """Run selected scraper adapters against the versioned target corpus."""
    names = scraper or scraper_names()
    targets = load_targets(targets_path)
    if limit:
        targets = targets[:limit]

    adjudicator: Validator | None = None
    if validator == "openai":
        if os.getenv("OPENAI_API_KEY"):
            from scrapingarena.validation.openai_validator import OpenAIValidator

            adjudicator = OpenAIValidator()
        elif openai_fallback:
            adjudicator = KeywordFallbackValidator()
            typer.echo(
                "OPENAI_API_KEY is not set; using HTML block-keyword fallback",
                err=True,
            )
        else:
            raise typer.BadParameter(
                "OPENAI_API_KEY is required when --no-openai-fallback is set"
            )
    elif validator != "deterministic":
        raise typer.BadParameter("validator must be deterministic or openai")

    runner = BenchmarkRunner(
        CompositeValidator(adjudicator=adjudicator),
        concurrency=concurrency,
        retries=retries,
        timeout_seconds=timeout,
    )
    try:
        proxy_settings = configured_proxy(proxy)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--proxy") from exc

    report = asyncio.run(
        runner.run(
            [create_scraper(name) for name in names],
            targets,
            targets_path=targets_path,
            proxy=proxy_settings,
        )
    )
    run_path, latest_path = write_report(report, output_dir)
    for summary in report.summaries:
        typer.echo(
            f"{summary.benchmark}: {summary.success}/{summary.total} success "
            f"({summary.success_rate:.2f}%), median={summary.median_success_ms}ms"
        )
    typer.echo(f"Wrote {run_path} and {latest_path}")


@app.command()
def merge(
    reports: Annotated[
        list[Path],
        typer.Argument(exists=True, dir_okay=False, help="Shard report files."),
    ],
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", file_okay=False),
    ] = Path("results"),
    run_id: Annotated[
        str | None,
        typer.Option(help="Canonical ID for the combined run."),
    ] = None,
) -> None:
    """Merge independently produced scraper reports into one canonical run."""
    report = merge_reports(reports, run_id=run_id)
    run_path, latest_path = write_report(report, output_dir)
    typer.echo(f"Merged {len(reports)} reports with {len(report.results)} scrapers")
    typer.echo(f"Wrote {run_path} and {latest_path}")


if __name__ == "__main__":
    app()
