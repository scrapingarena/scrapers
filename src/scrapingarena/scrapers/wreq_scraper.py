from __future__ import annotations

import re
import time
from datetime import timedelta
from typing import Any

from wreq import Client, Emulation, Proxy
from wreq import exceptions as wreq_exceptions

from scrapingarena.models import ScrapeRequest, ScrapeResponse
from scrapingarena.scrapers.base import BaseScraper, ScraperMetadata
from scrapingarena.settings import ProxySettings


def latest_chrome_emulation() -> Any:
    """Return the newest Chrome profile shipped by the installed wreq."""
    profiles = [
        (int(name.removeprefix("Chrome")), getattr(Emulation, name))
        for name in dir(Emulation)
        if re.fullmatch(r"Chrome\d+", name)
    ]
    if not profiles:
        raise RuntimeError("installed wreq exposes no Chrome emulation profiles")
    return max(profiles, key=lambda profile: profile[0])[1]


WREQ_ERRORS = (
    wreq_exceptions.BodyError,
    wreq_exceptions.BuilderError,
    wreq_exceptions.ConnectionError,
    wreq_exceptions.ConnectionResetError,
    wreq_exceptions.DecodingError,
    wreq_exceptions.RedirectError,
    wreq_exceptions.RequestError,
    wreq_exceptions.TimeoutError,
    wreq_exceptions.UpgradeError,
)


class WreqScraper(BaseScraper):
    supports_proxy = True
    metadata = ScraperMetadata(
        slug="wreq",
        name="wreq",
        kind="http",
        homepage="https://github.com/0x676e67/wreq-python",
    )

    def __init__(self, proxy: ProxySettings | None = None) -> None:
        super().__init__(proxy)
        # Do not pass or modify headers: the emulation profile owns the complete
        # browser fingerprint, including its matching browser headers.
        self._client = Client(emulation=latest_chrome_emulation())

    async def close(self) -> None:
        self._client.close()

    async def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        started = time.perf_counter()
        try:
            kwargs: dict[str, Any] = {}
            if request.proxy:
                kwargs["proxy"] = Proxy.all(request.proxy.url)
            response = await self._client.get(
                request.target.url_string,
                timeout=timedelta(seconds=request.timeout_seconds),
                **kwargs,
            )
            duration_ms = (time.perf_counter() - started) * 1000
            return ScrapeResponse(
                requested_url=request.target.url_string,
                final_url=str(response.url),
                status_code=response.status.as_int(),
                headers={
                    key.decode("latin-1").lower(): value.decode("latin-1")
                    for key, value in response.headers
                },
                html=await response.text(),
                duration_ms=duration_ms,
            )
        except WREQ_ERRORS as exc:
            duration_ms = (time.perf_counter() - started) * 1000
            return ScrapeResponse(
                requested_url=request.target.url_string,
                duration_ms=duration_ms,
                error=f"{type(exc).__name__}: {exc}",
            )
