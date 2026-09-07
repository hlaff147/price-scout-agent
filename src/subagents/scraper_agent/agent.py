"""Composite scraper subagent dispatching between HTTP and Playwright browser adapters."""

from typing import Any, ClassVar

from loguru import logger

from src.core.ports.http_port import IHttpClient
from src.core.ports.scraper_port import IScraper
from src.data.models import Product, ScrapedData, Source
from src.skills.base import BaseSkill
from src.subagents.base import BaseSubagent
from src.subagents.scraper_agent.http_adapter import HttpScraperSubagent
from src.subagents.scraper_agent.playwright_adapter import PlaywrightScraperSubagent


class ScraperSubagent(BaseSubagent, IScraper):
    """Subagente orquestrador que despacha para HTTP ou Playwright conforme o método de coleta."""

    name = "scraper_subagent"
    role = "Marketplace Multi-Transport Scraper"

    SKILL_REGISTRY: ClassVar[dict[str, type[BaseSkill]]] = HttpScraperSubagent.SKILL_REGISTRY

    def __init__(
        self,
        client: IHttpClient | None = None,
        http_scraper: IScraper | None = None,
        browser_scraper: IScraper | None = None,
        enable_fallback: bool = True,
        selector_repo: Any | None = None,
        healer: Any | None = None,
    ):
        self.selector_repo = selector_repo
        self.healer = healer
        self.http_scraper = http_scraper or HttpScraperSubagent(
            client=client,
            selector_repo=selector_repo,
            healer=healer,
        )
        self.browser_scraper = browser_scraper or PlaywrightScraperSubagent(
            selector_repo=selector_repo,
            healer=healer,
        )
        self.enable_fallback = enable_fallback

    def register_skill(self, marketplace: str, skill: BaseSkill) -> None:
        """Registra uma nova skill de parsing em ambos os adaptadores."""
        if hasattr(self.http_scraper, "register_skill"):
            self.http_scraper.register_skill(marketplace, skill)
        if hasattr(self.browser_scraper, "register_skill"):
            self.browser_scraper.register_skill(marketplace, skill)

    async def run(self, source: Source, product: Product) -> ScrapedData:
        """Despacha a coleta para o adapter apropriado baseado em source.metodo_coleta."""
        metodo = (source.metodo_coleta or "scraping_html").lower()

        # 1. Se configurado explicitamente para browser / playwright
        if metodo in ("browser", "playwright"):
            logger.debug(f"Despachando coleta de {source.marketplace} para PlaywrightBrowser...")
            return await self.browser_scraper.run(source, product)

        # 2. Execução padrão via HTTP
        scraped = await self.http_scraper.run(source, product)

        # 3. Fallback dinâmico opcional: se o parser ou erro acusar necessidade de JS
        if self.enable_fallback and not scraped.success:
            err = (scraped.error_message or "").lower()
            if "javascript" in err or "spa" in err:
                logger.info(
                    f"Detectada necessidade de renderização JS em [{source.marketplace.upper()}]. "
                    f"Acionando fallback automático para Playwright..."
                )
                return await self.browser_scraper.run(source, product)

        return scraped


# Alias semântico
CompositeScraperSubagent = ScraperSubagent
