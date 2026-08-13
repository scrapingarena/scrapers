from __future__ import annotations

from scrapingarena.models import ScrapeResponse, Target, ValidationResult, Verdict
from scrapingarena.validation.base import Validator
from scrapingarena.validation.deterministic import DeterministicValidator


class CompositeValidator:
    """Run deterministic rules first and adjudicate only ambiguous responses."""

    def __init__(
        self,
        adjudicator: Validator | None = None,
        deterministic: DeterministicValidator | None = None,
    ) -> None:
        self._deterministic = deterministic or DeterministicValidator()
        self._adjudicator = adjudicator

    async def validate(
        self,
        target: Target,
        response: ScrapeResponse,
    ) -> ValidationResult:
        deterministic = await self._deterministic.validate(target, response)
        if deterministic.verdict is not Verdict.AMBIGUOUS or not self._adjudicator:
            return deterministic

        adjudicated = await self._adjudicator.validate(target, response)
        adjudicated.signals["deterministic"] = deterministic.model_dump(mode="json")
        return adjudicated
