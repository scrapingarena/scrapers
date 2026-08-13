from __future__ import annotations

from dataclasses import dataclass

import pytest

from scrapingarena.models import (
    ScrapeResponse,
    Target,
    ValidationResult,
    Verdict,
)
from scrapingarena.validation.composite import CompositeValidator
from scrapingarena.validation.deterministic import DeterministicValidator


def target(**overrides: object) -> Target:
    values: dict[str, object] = {
        "id": "example",
        "name": "Example",
        "url": "https://example.com/",
        "category": "test",
        "required_markers": ["Expected product"],
        "min_visible_chars": 20,
    }
    values.update(overrides)
    return Target.model_validate(values)


def response(**overrides: object) -> ScrapeResponse:
    values: dict[str, object] = {
        "requested_url": "https://example.com/",
        "final_url": "https://example.com/",
        "status_code": 200,
        "headers": {"content-type": "text/html; charset=utf-8"},
        "html": (
            "<html><title>Expected product</title><body>"
            "Expected product with enough useful page content.</body></html>"
        ),
        "duration_ms": 42,
    }
    values.update(overrides)
    return ScrapeResponse.model_validate(values)


@pytest.mark.parametrize("status", [401, 403, 407, 418, 429, 451])
async def test_block_statuses_are_blocked(status: int) -> None:
    result = await DeterministicValidator().validate(
        target(),
        response(status_code=status),
    )

    assert result.verdict is Verdict.BLOCKED
    assert result.confidence >= 0.99


async def test_cloudflare_authoritative_header_wins_over_200() -> None:
    result = await DeterministicValidator().validate(
        target(),
        response(headers={"cf-mitigated": "challenge"}),
    )

    assert result.verdict is Verdict.BLOCKED
    assert result.signals["provider"] == "cloudflare"


@pytest.mark.parametrize(
    ("html", "provider"),
    [
        ("<script src='/cdn-cgi/challenge-platform/x'></script>", "cloudflare"),
        ("<script src='https://geo.captcha-delivery.com/x'></script>", "datadome"),
        ("<div id='px-captcha'></div>", "human-security"),
        ("<p>Incapsula incident ID 123</p>", "imperva"),
        ("<h1>Too Many Requests</h1>", "rate-limit"),
    ],
)
async def test_known_soft_block_signatures(html: str, provider: str) -> None:
    result = await DeterministicValidator().validate(
        target(),
        response(html=html),
    )

    assert result.verdict is Verdict.BLOCKED
    assert result.signals["provider"] == provider


async def test_valid_content_is_success() -> None:
    result = await DeterministicValidator().validate(target(), response())

    assert result.verdict is Verdict.SUCCESS


async def test_missing_expected_content_is_ambiguous() -> None:
    result = await DeterministicValidator().validate(
        target(),
        response(
            html="<html><body>A generic but long enough response body.</body></html>"
        ),
    )

    assert result.verdict is Verdict.AMBIGUOUS


@dataclass
class FakeAdjudicator:
    calls: int = 0

    async def validate(
        self,
        page_target: Target,
        page_response: ScrapeResponse,
    ) -> ValidationResult:
        del page_target, page_response
        self.calls += 1
        return ValidationResult(
            verdict=Verdict.FAILED,
            confidence=0.88,
            reasons=["consent-only page"],
            validator="fake",
        )


async def test_adjudicator_only_receives_ambiguous_responses() -> None:
    adjudicator = FakeAdjudicator()
    validator = CompositeValidator(adjudicator=adjudicator)

    valid = await validator.validate(target(), response())
    ambiguous = await validator.validate(
        target(),
        response(html="<html><body>Generic response content here.</body></html>"),
    )

    assert valid.verdict is Verdict.SUCCESS
    assert ambiguous.verdict is Verdict.FAILED
    assert adjudicator.calls == 1
    assert "deterministic" in ambiguous.signals
