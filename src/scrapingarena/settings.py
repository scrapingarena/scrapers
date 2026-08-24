from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import quote


@dataclass(frozen=True, slots=True)
class OpenAIValidatorSettings:
    api_key: str | None
    model: str = "gpt-5.6-luna"
    timeout_seconds: float = 45
    max_evidence_chars: int = 12_000


def configured_openai_validator() -> OpenAIValidatorSettings:
    """Load OpenAI validator configuration from the process environment."""
    return OpenAIValidatorSettings(
        api_key=os.getenv("OPENAI_API_KEY"),
        model=os.getenv("SCRAPINGARENA_OPENAI_MODEL", "gpt-5.6-luna"),
    )


@dataclass(frozen=True, slots=True)
class ProxySettings:
    host: str
    port: int
    username: str
    password: str
    provider_name: str
    provider_url: str

    @property
    def url(self) -> str:
        username = quote(self.username, safe="")
        password = quote(self.password, safe="")
        return f"http://{username}:{password}@{self.host}:{self.port}"

    def redact(self, value: str) -> str:
        """Remove proxy credentials from an error before it reaches a report."""
        redacted = value.replace(self.url, f"http://***@{self.host}:{self.port}")
        for secret in (self.username, self.password):
            redacted = redacted.replace(secret, "***")
            redacted = redacted.replace(quote(secret, safe=""), "***")
        return redacted


def configured_proxy(provider_name: str) -> ProxySettings | None:
    """Load one named provider, with ``direct`` representing no proxy."""
    if provider_name == "direct":
        return None
    if provider_name != "oxylabs":
        raise ValueError(f"unknown proxy provider: {provider_name}")
    username = os.getenv("OXYLABS_RESIDENTIAL_PROXIES_USERNAME")
    password = os.getenv("OXYLABS_RESIDENTIAL_PROXIES_PASSWORD")
    if bool(username) != bool(password):
        raise ValueError(
            "OXYLABS_RESIDENTIAL_PROXIES_USERNAME and "
            "OXYLABS_RESIDENTIAL_PROXIES_PASSWORD must be set together"
        )
    if not username or not password:
        raise ValueError("Oxylabs proxy credentials are not configured")
    return ProxySettings(
        host="pr.oxylabs.io",
        port=7777,
        username=username,
        password=password,
        provider_name="oxylabs",
        provider_url="https://oxylabs.io/products/residential-proxy-pool",
    )
