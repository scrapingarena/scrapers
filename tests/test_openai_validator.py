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
            "min_visible_chars": 50,
        }
    )
    response = ScrapeResponse(
        requested_url="https://example.com",
        final_url="https://example.com/challenge",
        status_code=200,
        headers={"Content-Type": "text/html", "Set-Cookie": "private"},
        html=(f"<html><title>Wait</title><body>catalog {'x' * 80}</body></html>"),
        duration_ms=10,
    )

    result = await validator.validate(target, response)

    assert result.verdict is Verdict.FAILED
    assert result.confidence == 1
    assert result.reasons == ["OpenAI classified the fetch as failed"]
    assert result.validator == "openai-binary-v2"
    assert result.signals == {"model": "test-model"}
    assert responses.arguments["text_format"] is PageValidation
    assert responses.arguments["store"] is False
    evidence = json.loads(responses.arguments["input"])
    assert set(evidence) == {
        "error",
        "headers",
        "final_url",
        "observed_page",
        "requested_target",
        "requested_url",
        "status_code",
    }
    assert evidence["requested_target"]["url"] == "https://example.com/"
    assert evidence["requested_target"]["required_markers"] == ["catalog"]
    assert evidence["status_code"] == 200
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
            "min_visible_chars": 0,
        }
    )
    response = ScrapeResponse(
        requested_url="https://example.com",
        status_code=200,
        html="<body>content</body>",
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
        final_url="https://example.com",
        status_code=200,
        html="<body>" + "useful content " * 20 + "</body>",
        duration_ms=1,
    )

    result = await validator.validate(target, response)

    assert result.verdict is Verdict.SUCCESS


@pytest.mark.parametrize("status_code", [401, 403, 407, 429])
async def test_openai_validator_classifies_block_status_without_model(
    status_code: int,
) -> None:
    validator, responses = validator_with(PageValidation(success=True))
    target = Target.model_validate(
        {
            "id": "example",
            "name": "Example",
            "url": "https://example.com",
            "category": "test",
        }
    )
    response = ScrapeResponse(
        requested_url=target.url_string,
        status_code=status_code,
        html="<body>Access denied</body>",
        duration_ms=1,
    )

    result = await validator.validate(target, response)

    assert result.verdict is Verdict.BLOCKED
    assert responses.arguments == {}


async def test_openai_validator_rejects_scraper_error_without_model() -> None:
    validator, responses = validator_with(PageValidation(success=True))
    target = Target.model_validate(
        {
            "id": "example",
            "name": "Example",
            "url": "https://example.com",
            "category": "test",
        }
    )
    response = ScrapeResponse(
        requested_url=target.url_string,
        error="ProxyError: connection failed",
        duration_ms=1,
    )

    result = await validator.validate(target, response)

    assert result.verdict is Verdict.FAILED
    assert result.signals == {"error": True}
    assert responses.arguments == {}


async def test_openai_validator_enforces_target_content_requirements() -> None:
    validator, responses = validator_with(PageValidation(success=True))
    target = Target.model_validate(
        {
            "id": "example",
            "name": "Example",
            "url": "https://example.com",
            "category": "test",
            "required_markers": ["product catalog"],
            "min_visible_chars": 30,
        }
    )
    response = ScrapeResponse(
        requested_url=target.url_string,
        status_code=200,
        html="<body>This is a long but unrelated page with no useful data.</body>",
        duration_ms=1,
    )

    result = await validator.validate(target, response)

    assert result.verdict is Verdict.FAILED
    assert result.signals == {"missing_required_markers": ["product catalog"]}
    assert responses.arguments == {}


def labeled_target(**updates: Any) -> Target:
    values: dict[str, Any] = {
        "id": "shop",
        "name": "Example Shop",
        "url": "https://shop.example/products",
        "category": "commerce",
        "required_markers": ["Example Shop", "Running Shoes"],
        "forbidden_markers": ["Access denied"],
        "min_visible_chars": 50,
    }
    values.update(updates)
    return Target.model_validate(values)


def labeled_response(**updates: Any) -> ScrapeResponse:
    values: dict[str, Any] = {
        "requested_url": "https://shop.example/products",
        "final_url": "https://shop.example/products",
        "status_code": 200,
        "html": (
            "<html><title>Example Shop</title><body>"
            "Running Shoes product catalog with prices and availability."
            "</body></html>"
        ),
        "duration_ms": 10,
    }
    values.update(updates)
    return ScrapeResponse.model_validate(values)


@pytest.mark.parametrize(
    ("response_updates", "expected_verdict"),
    [
        ({"status_code": 401}, Verdict.BLOCKED),
        ({"status_code": 403}, Verdict.BLOCKED),
        ({"status_code": 407}, Verdict.BLOCKED),
        ({"status_code": 429}, Verdict.BLOCKED),
        ({"status_code": 302}, Verdict.FAILED),
        ({"status_code": 500}, Verdict.FAILED),
        ({"error": "ProxyError: tunnel failed"}, Verdict.FAILED),
        ({"html": ""}, Verdict.FAILED),
        ({"html": "<body>Example Shop</body>"}, Verdict.FAILED),
        (
            {
                "html": (
                    "<body>Example Shop Running Shoes Access denied "
                    "by the security policy.</body>"
                )
            },
            Verdict.BLOCKED,
        ),
        (
            {
                "html": (
                    "<body>This is an unrelated page with enough visible text "
                    "to pass the configured minimum character threshold.</body>"
                )
            },
            Verdict.FAILED,
        ),
        (
            {
                "html": (
                    "<script>Example Shop Running Shoes</script>"
                    "<body>This unrelated visible page is long enough to pass "
                    "the minimum length but its markers are hidden in script.</body>"
                )
            },
            Verdict.FAILED,
        ),
    ],
)
async def test_labeled_failures_are_rejected_without_model(
    response_updates: dict[str, Any],
    expected_verdict: Verdict,
) -> None:
    validator, responses = validator_with(PageValidation(success=True))

    result = await validator.validate(
        labeled_target(), labeled_response(**response_updates)
    )

    assert result.verdict is expected_verdict
    assert responses.arguments == {}


async def test_labeled_good_page_requires_content_judgment() -> None:
    validator, responses = validator_with(PageValidation(success=True))

    result = await validator.validate(labeled_target(), labeled_response())

    assert result.verdict is Verdict.SUCCESS
    assert responses.arguments != {}


async def test_same_response_has_same_verdict_regardless_of_proxy_path() -> None:
    direct_validator, _ = validator_with(PageValidation(success=True))
    proxy_validator, _ = validator_with(PageValidation(success=True))
    direct_response = labeled_response()
    proxy_response = direct_response.model_copy(deep=True)

    direct = await direct_validator.validate(labeled_target(), direct_response)
    proxied = await proxy_validator.validate(labeled_target(), proxy_response)

    assert direct == proxied
    assert direct.validator == "openai-binary-v2"
