from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class Protection(StrEnum):
    NONE = "none"
    CLOUDFLARE = "cloudflare"
    AKAMAI = "akamai"
    DATADOME = "datadome"
    HUMAN_SECURITY = "human-security"
    IMPERVA = "imperva"
    FASTLY = "fastly"
    KASADA = "kasada"
    UNKNOWN = "unknown"


class Target(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str
    url: HttpUrl
    category: str
    protection: Protection = Protection.UNKNOWN
    required_markers: list[str] = Field(default_factory=list)
    forbidden_markers: list[str] = Field(default_factory=list)
    min_visible_chars: int = Field(default=200, ge=0)

    @property
    def url_string(self) -> str:
        return str(self.url)


class ScrapeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: Target
    timeout_seconds: float = Field(default=30, gt=0, le=120)


class ScrapeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_url: str
    final_url: str | None = None
    status_code: int | None = Field(default=None, ge=100, le=599)
    # Needed during validation but excluded from persisted public reports.
    headers: dict[str, str] = Field(default_factory=dict, exclude=True)
    html: str = Field(default="", exclude=True)
    duration_ms: float = Field(ge=0)
    error: str | None = None


class Verdict(StrEnum):
    SUCCESS = "success"
    BLOCKED = "blocked"
    FAILED = "failed"
    AMBIGUOUS = "ambiguous"


class ValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Verdict
    confidence: float = Field(ge=0, le=1)
    reasons: list[str] = Field(min_length=1)
    signals: dict[str, Any] = Field(default_factory=dict)
    validator: str = "deterministic"


class AttemptResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt: int = Field(ge=1)
    response: ScrapeResponse
    validation: ValidationResult


class TargetResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_id: str
    url: str
    protection: Protection
    attempts: list[AttemptResult] = Field(min_length=1)

    @property
    def final_attempt(self) -> AttemptResult:
        return self.attempts[-1]


class ScraperSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scraper: str
    total: int
    success: int
    blocked: int
    failed: int
    ambiguous: int
    success_rate: float
    median_success_ms: float | None


class RunMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    started_at: datetime
    finished_at: datetime
    git_sha: str | None = None
    runner: str
    target_set_sha256: str

    @model_validator(mode="after")
    def finished_after_started(self) -> RunMetadata:
        if self.finished_at < self.started_at:
            raise ValueError("finished_at must not precede started_at")
        return self


class BenchmarkReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    metadata: RunMetadata
    summaries: list[ScraperSummary]
    results: dict[str, list[TargetResult]]


def utc_now() -> datetime:
    return datetime.now(UTC)
