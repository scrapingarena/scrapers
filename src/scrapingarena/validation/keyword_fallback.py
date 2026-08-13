from __future__ import annotations

from scrapingarena.models import ScrapeResponse, Target, ValidationResult, Verdict

BLOCK_KEYWORDS = (
    "access denied",
    "are you a robot",
    "automated queries",
    "checking your browser",
    "complete the security check",
    "pardon our interruption",
    "press and hold",
    "request blocked",
    "security verification",
    "sorry, you have been blocked",
    "temporarily blocked",
    "unusual traffic",
    "verify you are human",
    "verify your identity",
)


class KeywordFallbackValidator:
    """Resolve ambiguous HTML without an external adjudication service."""

    name = "keyword-fallback-v1"

    async def validate(
        self,
        target: Target,
        response: ScrapeResponse,
    ) -> ValidationResult:
        del target
        html = response.html.lower()
        matches = [keyword for keyword in BLOCK_KEYWORDS if keyword in html]
        if matches:
            return ValidationResult(
                verdict=Verdict.BLOCKED,
                confidence=0.95,
                reasons=[f"block-page keyword found: {matches[0]!r}"],
                signals={"block_keywords": matches},
                validator=self.name,
            )

        return ValidationResult(
            verdict=Verdict.SUCCESS,
            confidence=0.7,
            reasons=["no known block-page keywords found in HTML"],
            signals={"block_keywords": []},
            validator=self.name,
        )
