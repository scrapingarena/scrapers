from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from scrapingarena.models import (
    ScrapeResponse,
    Target,
    ValidationResult,
    Verdict,
)
from scrapingarena.validation.html import extract_visible_text


@dataclass(frozen=True, slots=True)
class BlockSignature:
    name: str
    markers: tuple[str, ...]
    minimum_matches: int = 1


BLOCK_SIGNATURES = (
    BlockSignature("cloudflare", ("cf-chl-", "/cdn-cgi/challenge-platform/")),
    BlockSignature("cloudflare", ("attention required! | cloudflare",)),
    BlockSignature("datadome", ("geo.captcha-delivery.com", "datadome")),
    BlockSignature("human-security", ("px-captcha", "_pxcaptcha")),
    BlockSignature("akamai", ("akamai bot manager", "reference #18.")),
    BlockSignature("imperva", ("incapsula incident id", "_incapsula_resource")),
    BlockSignature("generic-captcha", ("verify you are human", "captcha")),
    BlockSignature("generic-block", ("access denied", "request blocked"), 2),
    BlockSignature("rate-limit", ("too many requests",)),
    BlockSignature("javascript-wall", ("enable javascript and cookies",)),
)

BLOCK_STATUSES = {401, 403, 407, 418, 429, 451}


class DeterministicValidator:
    name = "deterministic-v1"

    async def validate(
        self,
        target: Target,
        response: ScrapeResponse,
    ) -> ValidationResult:
        if response.error:
            return self._result(
                Verdict.FAILED,
                1,
                [f"transport error: {response.error}"],
            )

        headers = {
            key.lower(): value.lower() for key, value in response.headers.items()
        }
        if headers.get("cf-mitigated") == "challenge":
            return self._result(
                Verdict.BLOCKED,
                1,
                ["Cloudflare cf-mitigated header identifies a challenge response"],
                {"provider": "cloudflare", "header": "cf-mitigated"},
            )

        status = response.status_code
        if status in BLOCK_STATUSES:
            return self._result(
                Verdict.BLOCKED,
                0.99,
                [f"HTTP {status} is a block/auth/rate-limit status"],
                {"status_code": status},
            )
        if status is None or status >= 500:
            return self._result(
                Verdict.FAILED,
                0.99,
                [
                    f"HTTP {status or 'status unavailable'} is a "
                    "server/transport failure"
                ],
                {"status_code": status},
            )
        if status < 200 or status >= 400:
            return self._result(
                Verdict.FAILED,
                0.97,
                [f"HTTP {status} is not a successful page response"],
                {"status_code": status},
            )

        content_type = headers.get("content-type", "")
        if content_type and not any(
            allowed in content_type
            for allowed in ("text/html", "application/xhtml+xml")
        ):
            return self._result(
                Verdict.FAILED,
                0.98,
                [f"unexpected content type: {content_type}"],
                {"content_type": content_type},
            )

        html_lower = response.html.lower()
        signature = self._find_signature(html_lower)
        if signature:
            return self._result(
                Verdict.BLOCKED,
                0.99,
                [f"known {signature.name} challenge signature found"],
                {"provider": signature.name},
            )

        forbidden = [
            marker
            for marker in target.forbidden_markers
            if marker.lower() in html_lower
        ]
        if forbidden:
            return self._result(
                Verdict.BLOCKED,
                0.98,
                [f"target-specific forbidden marker found: {forbidden[0]!r}"],
                {"forbidden_markers": forbidden},
            )

        final_host = urlparse(response.final_url or response.requested_url).hostname
        target_host = target.url.host
        if final_host and target_host and not self._same_site(final_host, target_host):
            return self._result(
                Verdict.AMBIGUOUS,
                0.8,
                [f"cross-site redirect from {target_host} to {final_host}"],
                {"final_host": final_host},
            )

        title, visible_text = extract_visible_text(response.html)
        visible_lower = visible_text.lower()
        required_matches = [
            marker
            for marker in target.required_markers
            if marker.lower() in visible_lower or marker.lower() in html_lower
        ]
        if target.required_markers and not required_matches:
            return self._result(
                Verdict.AMBIGUOUS,
                0.82,
                ["none of the target-specific required markers were found"],
                {
                    "required_markers": target.required_markers,
                    "visible_chars": len(visible_text),
                    "title": title,
                },
            )

        if len(visible_text) < target.min_visible_chars:
            return self._result(
                Verdict.AMBIGUOUS,
                0.78,
                [
                    "page has too little visible content "
                    f"({len(visible_text)} < {target.min_visible_chars} characters)"
                ],
                {"visible_chars": len(visible_text), "title": title},
            )

        return self._result(
            Verdict.SUCCESS,
            0.96 if target.required_markers else 0.9,
            ["successful HTML response passed block and content checks"],
            {
                "visible_chars": len(visible_text),
                "title": title,
                "required_matches": required_matches,
            },
        )

    @staticmethod
    def _find_signature(html: str) -> BlockSignature | None:
        for signature in BLOCK_SIGNATURES:
            matches = sum(marker in html for marker in signature.markers)
            if matches >= signature.minimum_matches:
                return signature
        return None

    @staticmethod
    def _same_site(first: str, second: str) -> bool:
        first = first.removeprefix("www.")
        second = second.removeprefix("www.")
        return (
            first == second
            or first.endswith(f".{second}")
            or second.endswith(f".{first}")
        )

    def _result(
        self,
        verdict: Verdict,
        confidence: float,
        reasons: list[str],
        signals: dict[str, object] | None = None,
    ) -> ValidationResult:
        return ValidationResult(
            verdict=verdict,
            confidence=confidence,
            reasons=reasons,
            signals=signals or {},
            validator=self.name,
        )
