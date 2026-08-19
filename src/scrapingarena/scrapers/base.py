from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from scrapingarena.models import ScrapeRequest, ScrapeResponse
from scrapingarena.settings import ProxySettings


@dataclass(frozen=True, slots=True)
class ScraperMetadata:
    slug: str
    name: str
    kind: str
    homepage: str


class BaseScraper(ABC):
    """Fetch adapter contract.

    Adapters only normalize scraper output. They must not classify responses,
    retry requests, or write reports; those rules belong to the shared runner.
    """

    metadata: ScraperMetadata
    supports_proxy = False

    def __init__(self, proxy: ProxySettings | None = None) -> None:
        self._proxy = proxy

    async def __aenter__(self) -> BaseScraper:
        return self

    async def __aexit__(
        self,
        exc_type: object,
        exc: BaseException | None,
        traceback: object,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        """Release adapter resources."""
        return None

    @abstractmethod
    async def scrape(self, request: ScrapeRequest) -> ScrapeResponse:
        """Fetch one target and return a normalized response."""
