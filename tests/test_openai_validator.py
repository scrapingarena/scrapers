from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from scrapingarena.models import ScrapeResponse, Target, Verdict
from scrapingarena.settings import OpenAIValidatorSettings
from scrapingarena.validation.openai_validator import OpenAIValidator, PageValidation


class FakeResponses:
    def __init__(self, parsed: PageValidation | None) -> None:
        self.parsed = parsed
        self.arguments: dict[str, Any] = {}

    async def parse(self, **kwargs: Any) -> Any:
        self.arguments = kwargs
        return SimpleNamespace(output_parsed=self.parsed)


def validator_with(
    parsed: PageValidation | None,
) -> tuple[OpenAIValidator, FakeResponses]:
    responses = FakeResponses(parsed)
    client = SimpleNamespace(responses=responses)
    settings = OpenAIValidatorSettings(
        api_key="test-key",
        model="test-model",
        max_evidence_chars=30,
    )
    return OpenAIValidator(settings, client=client), responses


async def test_openai_validator_uses_parsed_structured_output() -> None:
    validator, responses = validator_with(PageValidation(success=False))
    target = Target.model_validate(
        {
            "id": "example",
            "name": "Example",
            "url": "https://example.com",
            "category": "test",
            "required_markers": ["catalog"],
        }
    )
    response = ScrapeResponse(
        requested_url="https://example.com",
        final_url="https://example.com/challenge",
        status_code=200,
        headers={"Content-Type": "text/html", "Set-Cookie": "private"},
        html=f"<html><title>Wait</title><body>{'x' * 80}</body></html>",
        duration_ms=10,
    )

    result = await validator.validate(target, response)

    assert result.verdict is Verdict.FAILED
    assert result.confidence == 1
    assert result.reasons == ["OpenAI classified the fetch as failed"]
    assert result.validator == "openai-binary-v1"
    assert result.signals == {"model": "test-model"}
    assert responses.arguments["text_format"] is PageValidation
    assert responses.arguments["store"] is False
    evidence = json.loads(responses.arguments["input"])
    assert set(evidence) == {"headers", "final_url", "observed_page"}
    assert evidence["final_url"] == "https://example.com/challenge"
    assert evidence["headers"] == {"content-type": "text/html"}
    sample = evidence["observed_page"]["visible_text_sample"]
    assert "[...middle omitted...]" in sample
    assert sample.startswith("Wait ")
    assert sample.endswith("x" * 10)
    assert "<html>" in evidence["observed_page"]["html_sample"]


async def test_openai_validator_rejects_missing_parsed_output() -> None:
    validator, _ = validator_with(None)
    target = Target.model_validate(
        {
            "id": "example",
            "name": "Example",
            "url": "https://example.com",
            "category": "test",
        }
    )
    response = ScrapeResponse(
        requested_url="https://example.com",
        duration_ms=1,
    )

    with pytest.raises(RuntimeError, match="no parsed validation result"):
        await validator.validate(target, response)


async def test_openai_validator_maps_true_to_success() -> None:
    validator, _ = validator_with(PageValidation(success=True))
    target = Target.model_validate(
        {
            "id": "example",
            "name": "Example",
            "url": "https://example.com",
            "category": "test",
        }
    )
    response = ScrapeResponse(
        requested_url="https://example.com",
        duration_ms=1,
    )

    result = await validator.validate(target, response)

    assert result.verdict is Verdict.SUCCESS
