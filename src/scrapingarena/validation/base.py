from __future__ import annotations

from typing import Protocol

from scrapingarena.models import ScrapeResponse, Target, ValidationResult


class Validator(Protocol):
    async def validate(
        self,
        target: Target,
        response: ScrapeResponse,
    ) -> ValidationResult: ...
