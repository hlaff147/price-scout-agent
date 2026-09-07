"""HTTP Scraper Adapter implementing IScraper for static HTML marketplaces."""

from typing import ClassVar

from loguru import logger

from src.core.ports.http_port import IHttpClient
from src.core.ports.scraper_port import IScraper
from src.core.ports.selector_port import IHealerAgentPort, ISelectorRepositoryPort
from src.data.models import Product, ScrapedData, Source
from src.skills.base import BaseSkill
from src.skills.parse_aliexpress.parser import ParseAliExpressSkill
from src.skills.parse_amazon.parser import ParseAmazonSkill
from src.skills.parse_google_shopping.parser import ParseGoogleShoppingSkill
from src.skills.parse_kabum.parser import ParseKabumSkill
from src.skills.parse_mercadolivre.parser import ParseMercadoLivreSkill
from src.skills.parse_shopee.parser import ParseShopeeSkill
from src.subagents.base import BaseSubagent
from src.subagents.scraper_agent.extractor import extract_with_overrides
from src.tools.http_client import http_client


class HttpScraperSubagent(BaseSubagent, IScraper):
    """Subagente responsável por consultar uma fonte via requisições HTTP estáticas."""

    name = "http_scraper_subagent"
    role = "HTTP Marketplace Web Scraper"

    SKILL_REGISTRY: ClassVar[dict[str, type[BaseSkill]]] = {
        "mercadolivre": ParseMercadoLivreSkill,
        "amazon": ParseAmazonSkill,
        "kabum": ParseKabumSkill,
        "shopee": ParseShopeeSkill,
        "aliexpress": ParseAliExpressSkill,
        "google_shopping": ParseGoogleShoppingSkill,
    }

    def __init__(
        self,
        client: IHttpClient | None = None,
        selector_repo: ISelectorRepositoryPort | None = None,
        healer: IHealerAgentPort | None = None,
    ):
        self.client = client or http_client
        self.selector_repo = selector_repo
        self.healer = healer
        self._skills: dict[str, BaseSkill] = {
            mkt: skill_cls() for mkt, skill_cls in self.SKILL_REGISTRY.items()
        }

    def register_skill(self, marketplace: str, skill: BaseSkill) -> None:
        """Permite registrar dinamicamente novos parsers de marketplace."""
        self._skills[marketplace.lower()] = skill

    async def run(self, source: Source, product: Product) -> ScrapedData:
        """Executa a coleta para uma fonte específica com isolamento de falha e self-healing."""
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

            # 1. Tenta extrair com overrides aprendidos pelo self-healing (se existirem)
            if self.selector_repo:
                overrides = self.selector_repo.get_active_overrides(mkt)
                if overrides:
                    scraped_override = extract_with_overrides(
                        html=html,
                        overrides=overrides,
                        url=source.url_produto,
                        marketplace=mkt,
                    )
                    if scraped_override and scraped_override.success and scraped_override.preco:
                        logger.info(
                            f"[{mkt.upper()}] Preço extraído via seletores reparados: "
                            f"R$ {scraped_override.preco:.2f} (Título: {scraped_override.titulo})"
                        )
                        return scraped_override

            # 2. Execução padrão via skill do marketplace
            scraped = parser.execute(
                html=html,
                url=source.url_produto,
                keywords=product.keywords,
            )
            if scraped.success and scraped.preco:
                logger.info(
                    f"[{mkt.upper()}] Preço encontrado: R$ {scraped.preco:.2f} (Título: {scraped.titulo})"
                )
                return scraped

            # 3. Se a extração falhou e healer está configurado, tenta auto-reparo
            if self.healer:
                logger.warning(
                    f"[{mkt.upper()}] Extração padrão falhou. Acionando subagente de self-healing..."
                )
                base_selectors = getattr(parser, "SELECTORS", {})
                heal_res = await self.healer.heal(
                    marketplace=mkt,
                    product=product,
                    html_content=html,
                    current_selectors=base_selectors,
                )
                if heal_res.healed and heal_res.proposed_selectors:
                    scraped_healed = extract_with_overrides(
                        html=html,
                        overrides=heal_res.proposed_selectors,
                        url=source.url_produto,
                        marketplace=mkt,
                    )
                    if scraped_healed and scraped_healed.success and scraped_healed.preco:
                        logger.info(
                            f"[{mkt.upper()}] Preço recuperado via self-healing: R$ {scraped_healed.preco:.2f}"
                        )
                        return scraped_healed

            msg = scraped.error_message or "Nenhum produto correspondente identificado na página."
            logger.warning(f"[{mkt.upper()}] {msg}")
            return scraped

        except Exception as exc:  # noqa: BLE001
            logger.error(f"Falha na coleta de [{mkt.upper()}]: {exc}")
            return ScrapedData(
                marketplace=mkt,
                success=False,
                url=source.url_produto,
                error_message=str(exc),
            )

