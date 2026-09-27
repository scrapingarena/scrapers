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
        base_username = self.username.split("-cc-", 1)[0].split("-sessid-", 1)[0]
        if self.provider_name == "nodemaven":
            base_username = self.username.split("-country-", 1)[0].split("-sid-", 1)[0]
        for secret in (self.username, base_username, self.password):
            redacted = redacted.replace(secret, "***")
            redacted = redacted.replace(quote(secret, safe=""), "***")
        return redacted


def configured_proxy(provider_name: str) -> ProxySettings | None:
    """Load one named provider, with ``direct`` representing no proxy."""
    if provider_name == "direct":
        return None
    if provider_name == "nodemaven":
        return configured_nodemaven_proxy()
    if provider_name != "oxylabs":
        raise ValueError(f"unknown proxy provider: {provider_name}")
    username_key = "OXYLABS_PROXIES_USERNAME"
    password_key = "OXYLABS_PROXIES_PASSWORD"
    username = os.getenv(username_key)
    password = os.getenv(password_key)
    if not username and not password:
        username_key = "OXYLABS_RESIDENTIAL_PROXIES_USERNAME"
        password_key = "OXYLABS_RESIDENTIAL_PROXIES_PASSWORD"
        username = os.getenv(username_key)
        password = os.getenv(password_key)
    if bool(username) != bool(password):
        raise ValueError(f"{username_key} and {password_key} must be set together")
    if not username or not password:
        raise ValueError("Oxylabs proxy credentials are not configured")
    # Preserve provider-issued credentials, including any explicit routing options.
    return ProxySettings(
        host="pr.oxylabs.io",
        port=7777,
        username=username,
        password=password,
        provider_name="oxylabs",
        provider_url="https://oxylabs.io/products/proxy-solutions",
    )


def configured_nodemaven_proxy() -> ProxySettings:
    """Preserve the dashboard username, including routing and filtering."""
    username = os.getenv("NODEMAVEN_USERNAME")
    password = os.getenv("NODEMAVEN_PASSWORD")
    if bool(username) != bool(password):
        raise ValueError(
            "NODEMAVEN_USERNAME and NODEMAVEN_PASSWORD must be set together"
        )
    if not username or not password:
        raise ValueError("NodeMaven proxy credentials are not configured")
    return ProxySettings(
        host="gate.nodemaven.com",
        port=8080,
        username=username,
        password=password,
        provider_name="nodemaven",
        provider_url="https://nodemaven.com/",
    )
