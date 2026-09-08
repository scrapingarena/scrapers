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
        for secret in (self.username, base_username, self.password):
            redacted = redacted.replace(secret, "***")
            redacted = redacted.replace(quote(secret, safe=""), "***")
        return redacted

    def with_session(self, session_id: str) -> ProxySettings:
        """Return credentials pinned to one exit IP for a target's retries."""
        safe_session = "".join(c for c in session_id.lower() if c.isalnum())[:24]
        username = self.username
        if "-sessid-" not in username:
            username = f"{username}-sessid-{safe_session}-sesstime-10"
        return ProxySettings(
            host=self.host,
            port=self.port,
            username=username,
            password=self.password,
            provider_name=self.provider_name,
            provider_url=self.provider_url,
        )


def configured_proxy(provider_name: str) -> ProxySettings | None:
    """Load one named provider, with ``direct`` representing no proxy."""
    if provider_name == "direct":
        return None
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
    # The purchased Oxylabs account selects the underlying premium proxy pool.
    if "-cc-" not in username:
        username = f"{username}-cc-US"
    return ProxySettings(
        host="pr.oxylabs.io",
        port=7777,
        username=username,
        password=password,
        provider_name="oxylabs",
        provider_url="https://oxylabs.io/products/proxy-solutions",
    )
