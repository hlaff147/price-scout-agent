"""Scraper subagent for isolated marketplace data extraction."""


from typing import ClassVar

from loguru import logger

from src.data.models import Product, ScrapedData, Source
from src.skills.base import BaseSkill
from src.skills.parse_aliexpress.parser import ParseAliExpressSkill
from src.skills.parse_amazon.parser import ParseAmazonSkill
from src.skills.parse_google_shopping.parser import ParseGoogleShoppingSkill
from src.skills.parse_kabum.parser import ParseKabumSkill
from src.skills.parse_mercadolivre.parser import ParseMercadoLivreSkill
from src.skills.parse_shopee.parser import ParseShopeeSkill
from src.subagents.base import BaseSubagent
from src.tools.http_client import HttpClient, http_client


class ScraperSubagent(BaseSubagent):
    """Subagente responsável por consultar uma fonte e extrair dados de preço."""

    name = "scraper_subagent"
    role = "Marketplace Web Scraper"

    # Mapeamento de skills de parsing por marketplace
    SKILL_REGISTRY: ClassVar[dict[str, type[BaseSkill]]] = {
        "mercadolivre": ParseMercadoLivreSkill,
        "amazon": ParseAmazonSkill,
        "kabum": ParseKabumSkill,
        "shopee": ParseShopeeSkill,
        "aliexpress": ParseAliExpressSkill,
        "google_shopping": ParseGoogleShoppingSkill,
    }

    def __init__(self, client: HttpClient | None = None):
        self.client = client or http_client
        self._skills: dict[str, BaseSkill] = {
            mkt: skill_cls() for mkt, skill_cls in self.SKILL_REGISTRY.items()
        }

    def register_skill(self, marketplace: str, skill: BaseSkill) -> None:
        """Permite registrar dinamicamente novos parsers de marketplace."""
        self._skills[marketplace.lower()] = skill

    async def run(self, source: Source, product: Product) -> ScrapedData:
        """Executa a coleta para uma fonte específica com isolamento de falha."""
        mkt = source.marketplace.lower()
        parser = self._skills.get(mkt)
        if not parser:
            return ScrapedData(
                marketplace=mkt,
                success=False,
                url=source.url_produto,
                error_message=f"Nenhuma skill de parsing configurada para o marketplace '{mkt}'.",
            )

        try:
            logger.info(f"Coletando preços em [{mkt.upper()}] para '{product.nome}'...")
            html = await self.client.fetch(source.url_produto)
            scraped = parser.execute(
                html=html,
                url=source.url_produto,
                keywords=product.keywords,
            )
            if scraped.success and scraped.preco:
                logger.info(
                    f"[{mkt.upper()}] Preço encontrado: R$ {scraped.preco:.2f} (Título: {scraped.titulo})"
                )
            else:
                logger.warning(
                    f"[{mkt.upper()}] Nenhum produto correspondente identificado na página."
                )
            return scraped

        except Exception as exc:
            logger.error(f"Falha na coleta de [{mkt.upper()}]: {exc}")
            return ScrapedData(
                marketplace=mkt,
                success=False,
                url=source.url_produto,
                error_message=str(exc),
            )
