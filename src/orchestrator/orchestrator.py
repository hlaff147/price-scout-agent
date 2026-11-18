"""Main orchestrator coordinating scrapers, price analyst, and notifier."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from src.core.models import (
    MonitoringCycleSummary,
    Product,
    ProductCycleResult,
    ScrapedData,
    Source,
)
from src.core.ports.analyst_port import IAnalyst
from src.core.ports.notifier_port import INotifier
from src.core.ports.repository_port import IRepository
from src.core.ports.scraper_port import IScraper
from src.data.database import default_db
from src.data.repository import Repository
from src.subagents.notifier_agent.agent import NotifierSubagent
from src.subagents.price_analyst_agent.agent import PriceAnalystSubagent
from src.subagents.scraper_agent.agent import ScraperSubagent


class Orchestrator:
    """Agente orquestrador procedural e sincronizador de catálogos YAML do PromoRadar."""

    def __init__(
        self,
        repository: IRepository | None = None,
        scraper: IScraper | None = None,
        analyst: IAnalyst | None = None,
        notifier: INotifier | None = None,
    ):
        self.repository = repository or Repository(default_db)
        self.scraper = scraper or ScraperSubagent()
        self.analyst = analyst or PriceAnalystSubagent(self.repository)
        self.notifier = notifier or NotifierSubagent(self.repository)

    def load_products_from_yaml(self, config_path: str = "src/config/products.yaml") -> list[Product]:
        """Carrega catálogo YAML e sincroniza metadados sem apagar overrides manuais do usuário."""
        path = Path(config_path)
        if not path.exists():
            logger.warning(f"Arquivo de configuração {config_path} não encontrado.")
            return []

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        products: list[Product] = []
        for p_data in data.get("products", []):
            sources = [
                Source(
                    product_id=p_data["id"],
                    marketplace=s["marketplace"],
                    url_produto=s["url_produto"],
                    metodo_coleta=s.get("metodo_coleta", "scraping_html"),
                    ativo=s.get("ativo", True),
                    motivo_desativacao=s.get("motivo_desativacao"),
                )
                for s in p_data.get("sources", [])
            ]
            prioridade_val = p_data.get("prioridade", "medium")
            product = Product(
                id=p_data["id"],
                nome=p_data["nome"],
                keywords=p_data.get("keywords", []),
                preco_alvo=float(p_data["preco_alvo"]),
                preco_maximo=float(p_data["preco_maximo"]),
                prioridade=prioridade_val,
                intervalo_customizado_min=p_data.get("intervalo_customizado_min"),
                ativo=p_data.get("ativo", True),
                sources=sources,
            )
            self.repository.sync_catalog_product(product)
            products.append(self.repository.get_product(product.id) or product)

        return products

    async def run_cycle_for_product(
        self,
        product: Product,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Executa um ciclo completo de monitoramento para um único produto com retorno uniforme."""
        logger.info(f"=== Iniciando ciclo de monitoramento para: {product.nome} ===")
        sources = self.repository.get_active_sources_for_product(product.id)
        if not sources:
            logger.warning(f"Nenhuma fonte ativa configurada para {product.nome}.")
            return ProductCycleResult(
                product_id=product.id,
                product_name=product.nome,
            ).to_summary_dict()

        tasks = [self.scraper.run(source, product) for source in sources]
        results: list[ScrapedData | BaseException] = await asyncio.gather(
            *tasks, return_exceptions=True
        )

        scraped_pairs: list[tuple[Source, ScrapedData]] = []
        error_count = 0
        no_result_count = 0

        for source, res in zip(sources, results):
            if isinstance(res, Exception):
                error_count += 1
                logger.error(f"Erro não tratado no scraper [{source.marketplace}]: {res}")
            elif isinstance(res, ScrapedData):
                if not res.success:
                    msg = (res.error_message or "").lower()
                    if "nenhum produto" in msg or ("nenhum" in msg and "correspondente" in msg):
                        no_result_count += 1
                    else:
                        error_count += 1
                scraped_pairs.append((source, res))

        analyses = await self.analyst.run(product, scraped_pairs)

        deal_count = 0
        sent_count = 0
        for deal in analyses:
            if deal.is_deal:
                deal_count += 1
                if await self.notifier.run(deal, product, dry_run=dry_run):
                    sent_count += 1

        prices_collected = len(
            [p for _, p in scraped_pairs if p.success and p.preco is not None and p.preco > 0]
        )

        logger.info(
            f"=== Ciclo concluído para {product.nome}: "
            f"{len(sources)} fontes consultadas, {deal_count} ofertas, "
            f"{no_result_count} sem resultado, {error_count} erros ==="
        )

        return ProductCycleResult(
            product_id=product.id,
            product_name=product.nome,
            sources_checked=len(sources),
            prices_collected=prices_collected,
            deals_found=deal_count,
            notifications_sent=sent_count,
            no_results=no_result_count,
            errors=error_count,
            analyses=analyses,
        ).to_summary_dict()

    async def run_all_products(
        self,
        specific_product_id: str | None = None,
        dry_run: bool = False,
        config_path: str = "src/config/products.yaml",
    ) -> dict[str, Any]:
        """Executa o ciclo completo de monitoramento para todos os produtos ativos."""
        self.load_products_from_yaml(config_path)

        products = self.repository.list_active_products()
        if specific_product_id:
            products = [p for p in products if p.id == specific_product_id]

        cycle_id = uuid.uuid4().hex[:8]
        if not products:
            logger.warning("Nenhum produto ativo encontrado para monitoramento.")
            return MonitoringCycleSummary(cycle_id=cycle_id, total_products=0).to_legacy_dict()

        cycles_dicts = []
        for product in products:
            res = await self.run_cycle_for_product(product, dry_run=dry_run)
            cycles_dicts.append(res)

        return {
            "cycle_id": cycle_id,
            "total_products": len(products),
            "cycles": cycles_dicts,
        }
