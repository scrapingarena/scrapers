from __future__ import annotations

import asyncio
import os
import platform
import statistics
import time
import uuid
from collections import Counter
from pathlib import Path

from scrapingarena.models import (
    AttemptResult,
    BenchmarkReport,
    RunMetadata,
    ScrapeRequest,
    ScrapeResponse,
    ScraperSummary,
    Target,
    TargetResult,
    Verdict,
    utc_now,
)
from scrapingarena.scrapers.base import BaseScraper
from scrapingarena.settings import ProxySettings
from scrapingarena.targets import corpus_sha256
from scrapingarena.validation.base import Validator


class BenchmarkRunner:
    def __init__(
        self,
        validator: Validator,
        *,
        concurrency: int = 5,
        retries: int = 3,
        timeout_seconds: float = 30,
    ) -> None:
        if concurrency < 1:
            raise ValueError("concurrency must be at least 1")
        if retries < 0:
            raise ValueError("retries cannot be negative")
        self._validator = validator
        self._concurrency = concurrency
        self._retries = retries
        self._timeout_seconds = timeout_seconds

    async def run(
        self,
        scrapers: list[BaseScraper],
        targets: list[Target],
        *,
        targets_path: Path | None = None,
        proxy: ProxySettings | None = None,
    ) -> BenchmarkReport:
        started_at = utc_now()
        results: dict[str, list[TargetResult]] = {}

        for scraper in scrapers:
            proxy_name = proxy.provider_name if proxy else "direct"
            benchmark_name = f"{scraper.metadata.slug}-{proxy_name}"
            results[benchmark_name] = await self._run_scraper(
                scraper, targets, benchmark_name=benchmark_name, proxy=proxy
            )

        finished_at = utc_now()
        run_id = os.getenv("SCRAPINGARENA_RUN_ID") or (
            f"{started_at:%Y%m%dT%H%M%SZ}-"
            f"{os.getenv('GITHUB_RUN_ID', uuid.uuid4().hex[:8])}"
        )
        return BenchmarkReport(
            metadata=RunMetadata(
                run_id=run_id,
                started_at=started_at,
                finished_at=finished_at,
                git_sha=os.getenv("GITHUB_SHA"),
                runner=f"{platform.system()}-{platform.machine()}",
                target_set_sha256=corpus_sha256(targets_path),
            ),
            summaries=[
                self._summarize(
                    benchmark_name,
                    benchmark_name.removesuffix(
                        f"-{proxy.provider_name if proxy else 'direct'}"
                    ),
                    proxy.provider_name if proxy else None,
                    scraper_results,
                )
                for benchmark_name, scraper_results in results.items()
            ],
            results=results,
        )

    async def _run_scraper(
        self,
        scraper: BaseScraper,
        targets: list[Target],
        *,
        benchmark_name: str,
        proxy: ProxySettings | None,
    ) -> list[TargetResult]:
        semaphore = asyncio.Semaphore(self._concurrency)

        async def run_target(target: Target) -> TargetResult:
            async with semaphore:
                return await self._run_target(
                    scraper, target, benchmark_name=benchmark_name, proxy=proxy
                )

        return list(await asyncio.gather(*(run_target(target) for target in targets)))

    async def _run_target(
        self,
        scraper: BaseScraper,
        target: Target,
        *,
        benchmark_name: str,
        proxy: ProxySettings | None,
    ) -> TargetResult:
        attempts: list[AttemptResult] = []
        request = ScrapeRequest(
            target=target,
            timeout_seconds=self._timeout_seconds,
            proxy=proxy,
        )
        for attempt_number in range(1, self._retries + 2):
            total_attempts = self._retries + 1
            label = (
                f"[{benchmark_name}] {target.id} "
                f"attempt {attempt_number}/{total_attempts}"
            )
            print(f"{label} start {target.url_string}", flush=True)
            started = time.perf_counter()
            try:
                attempt_scraper = type(scraper)()
                async with attempt_scraper:
                    response = await attempt_scraper.scrape(request)
            except Exception as exc:
                response = ScrapeResponse(
                    requested_url=target.url_string,
                    duration_ms=(time.perf_counter() - started) * 1000,
                    error=f"{type(exc).__name__}: {exc}",
                )
            validation = await self._validator.validate(target, response)
            attempts.append(
                AttemptResult(
                    attempt=attempt_number,
                    response=response,
                    validation=validation,
                )
            )
            error = response.error.replace("\n", " ") if response.error else "none"
            print(
                f"{label} result={validation.verdict.value} "
                f"status={response.status_code} "
                f"duration_ms={response.duration_ms:.0f} error={error}",
                flush=True,
            )
            if validation.verdict is Verdict.SUCCESS:
                break

        return TargetResult(
            target_id=target.id,
            url=target.url_string,
            protection=target.protection,
            attempts=attempts,
        )

    @staticmethod
    def _summarize(
        benchmark: str,
        scraper: str,
        proxy_provider: str | None,
        results: list[TargetResult],
    ) -> ScraperSummary:
        verdicts = Counter(
            result.final_attempt.validation.verdict for result in results
        )
        success_durations = [
            result.final_attempt.response.duration_ms
            for result in results
            if result.final_attempt.validation.verdict is Verdict.SUCCESS
        ]
        total = len(results)
        return ScraperSummary(
            benchmark=benchmark,
            scraper=scraper,
            proxy_provider=proxy_provider,
            total=total,
            success=verdicts[Verdict.SUCCESS],
            blocked=verdicts[Verdict.BLOCKED],
            failed=verdicts[Verdict.FAILED],
            ambiguous=verdicts[Verdict.AMBIGUOUS],
            success_rate=round(
                (verdicts[Verdict.SUCCESS] / total * 100) if total else 0,
                2,
            ),
            median_success_ms=(
                round(statistics.median(success_durations), 2)
                if success_durations
                else None
            ),
        )
