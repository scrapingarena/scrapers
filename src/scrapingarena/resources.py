from __future__ import annotations

import asyncio
import contextlib
import re
import time
from dataclasses import dataclass, field

import psutil

from scrapingarena.models import ResourceSample, ResourceUsage

MEBIBYTE = 1024 * 1024


@dataclass(slots=True)
class ResourceMonitor:
    interval_seconds: float = 1.0
    container_name: str | None = None
    _samples: list[ResourceSample] = field(default_factory=list, init=False)
    _started: float = field(default=0, init=False)
    _task: asyncio.Task[None] | None = field(default=None, init=False)
    _previous_cpu_seconds: float | None = field(default=None, init=False)
    _previous_sample_time: float | None = field(default=None, init=False)

    async def __aenter__(self) -> ResourceMonitor:
        self._started = time.perf_counter()
        self._task = asyncio.create_task(self._run())
        return self

    async def __aexit__(
        self,
        exc_type: object,
        exc: BaseException | None,
        traceback: object,
    ) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        await self._sample()

    def usage(self) -> ResourceUsage:
        memory = [sample.memory_mb for sample in self._samples]
        cpu = [sample.cpu_cores for sample in self._samples]
        return ResourceUsage(
            duration_ms=round((time.perf_counter() - self._started) * 1000, 2),
            peak_memory_mb=round(max(memory, default=0), 2),
            average_memory_mb=round(sum(memory) / len(memory), 2) if memory else 0,
            peak_cpu_cores=round(max(cpu, default=0), 3),
            average_cpu_cores=round(sum(cpu) / len(cpu), 3) if cpu else 0,
            samples=self._samples,
        )

    async def _run(self) -> None:
        while True:
            await self._sample()
            await asyncio.sleep(self.interval_seconds)

    async def _sample(self) -> None:
        now = time.perf_counter()
        memory_bytes = 0
        cpu_seconds = 0.0
        process = psutil.Process()
        try:
            processes = [process, *process.children(recursive=True)]
        except (OSError, psutil.Error):
            # Sandboxed hosts can deny process-table enumeration. The benchmark
            # process itself is still useful, and Linux CI permits descendants.
            processes = [process]
        for item in processes:
            try:
                memory_bytes += item.memory_info().rss
                times = item.cpu_times()
                cpu_seconds += times.user + times.system
            except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
                continue

        cpu_cores = 0.0
        if self._previous_cpu_seconds is not None and self._previous_sample_time:
            elapsed = now - self._previous_sample_time
            if elapsed > 0:
                cpu_cores = max(0, (cpu_seconds - self._previous_cpu_seconds) / elapsed)
        if self.container_name:
            container_memory, container_cpu = await self._container_usage()
            memory_bytes += container_memory
            cpu_cores += container_cpu
        self._previous_cpu_seconds = cpu_seconds
        self._previous_sample_time = now
        self._samples.append(
            ResourceSample(
                elapsed_ms=round((now - self._started) * 1000, 2),
                memory_mb=round(memory_bytes / MEBIBYTE, 2),
                cpu_cores=round(cpu_cores, 3),
            )
        )

    async def _container_usage(self) -> tuple[int, float]:
        container_name = self.container_name
        if not container_name:
            return 0, 0
        try:
            process = await asyncio.create_subprocess_exec(
                "docker",
                "stats",
                "--no-stream",
                "--format",
                "{{.CPUPerc}}|{{.MemUsage}}",
                container_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await process.communicate()
        except OSError:
            return 0, 0
        if process.returncode != 0:
            return 0, 0
        cpu_text, _, memory_text = stdout.decode().strip().partition("|")
        memory_value = memory_text.partition("/")[0].strip()
        return _parse_bytes(memory_value), float(cpu_text.rstrip("%") or 0) / 100


def _parse_bytes(value: str) -> int:
    match = re.fullmatch(r"([0-9.]+)([KMG]i?B)", value)
    if not match:
        return 0
    amount, unit = match.groups()
    multipliers = {
        "KB": 1000,
        "KiB": 1024,
        "MB": 1000**2,
        "MiB": 1024**2,
        "GB": 1000**3,
        "GiB": 1024**3,
    }
    return round(float(amount) * multipliers[unit])
