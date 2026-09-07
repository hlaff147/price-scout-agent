"""Abstract port interfaces for PromoRadar (Hexagonal Architecture)."""

from src.core.ports.analyst_port import IAnalyst
from src.core.ports.http_port import IHttpClient
from src.core.ports.notifier_port import INotifier
from src.core.ports.repository_port import IRepository
from src.core.ports.scraper_port import IScraper

__all__ = [
    "IAnalyst",
    "IHttpClient",
    "INotifier",
    "IRepository",
    "IScraper",
]
