"""Main orchestrator coordinating scrapers, price analyst, and notifier."""

import asyncio
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from src.core.ports.analyst_port import IAnalyst
from src.core.ports.notifier_port import INotifier
from src.core.ports.repository_port import IRepository
from src.core.ports.scraper_port import IScraper
from src.data.database import default_db
from src.data.models import Product, ScrapedData, Source
from src.data.repository import Repository
from src.subagents.notifier_agent.agent import NotifierSubagent
from src.subagents.price_analyst_agent.agent import PriceAnalystSubagent
from src.subagents.scraper_agent.agent import ScraperSubagent


class Orchestrator:
    """Agente orquestrador principal do PromoRadar."""

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
        """Carrega produtos cadastrados a partir do arquivo YAML e sincroniza com o banco."""
        path = Path(config_path)
        if not path.exists():
            logger.warning(f"Arquivo de configuração {config_path} não encontrado.")
            return []

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        products = []
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
            product = Product(
                id=p_data["id"],
                nome=p_data["nome"],
                keywords=p_data.get("keywords", []),
                preco_alvo=float(p_data["preco_alvo"]),
                preco_maximo=float(p_data["preco_maximo"]),
                ativo=p_data.get("ativo", True),
                sources=sources,
            )
            # Sincronizar com banco de dados
            self.repository.upsert_product(product)
            products.append(self.repository.get_product(product.id) or product)

        return products

    async def run_cycle_for_product(
        self,
        product: Product,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Executa um ciclo completo de monitoramento para um único produto."""
        logger.info(f"=== Iniciando ciclo de monitoramento para: {product.nome} ===")
        # Consultar apenas fontes ativas para este produto
        sources = self.repository.get_active_sources_for_product(product.id)
        if not sources:
            logger.warning(f"Nenhuma fonte ativa configurada para {product.nome}.")
            return {"product_id": product.id, "scraped": 0, "deals": 0, "errors": 0}

        # 1. Executar scrapers em paralelo com isolamento total de falhas
        tasks = [self.scraper.run(source, product) for source in sources]
        results: list[ScrapedData | BaseException] = await asyncio.gather(*tasks, return_exceptions=True)

        scraped_pairs = []
        error_count = 0
        no_result_count = 0

        for source, res in zip(sources, results):
            if isinstance(res, Exception):
                error_count += 1
                logger.error(f"Erro não tratado no scraper [{source.marketplace}]: {res}")
            elif isinstance(res, ScrapedData):
                if not res.success:
                    # "Nenhum produto" = sem resultado; qualquer outro = erro real
                    msg = (res.error_message or "").lower()
                    if "nenhum produto" in msg or "nenhum" in msg and "correspondente" in msg:
                        no_result_count += 1
                    else:
                        error_count += 1
                scraped_pairs.append((source, res))

        # 2. Encaminhar resultados ao Analista de Preços
        analyses = await self.analyst.run(product, scraped_pairs)

        # 3. Notificar ofertas vantajosas
        deal_count = 0
        for deal in analyses:
            if deal.is_deal:
                deal_count += 1
                await self.notifier.run(deal, product, dry_run=dry_run)

        logger.info(
            f"=== Ciclo concluído para {product.nome}: "
            f"{len(scraped_pairs)} fontes consultadas, {deal_count} ofertas, "
            f"{no_result_count} sem resultado, {error_count} erros ==="
        )

        return {
            "product_id": product.id,
            "sources_checked": len(sources),
            "prices_collected": len([p for _, p in scraped_pairs if p.preco]),
            "deals_found": deal_count,
            "no_results": no_result_count,
            "errors": error_count,
            "analyses": analyses,
        }

    async def run_all_products(
        self,
        specific_product_id: str | None = None,
        dry_run: bool = False,
        config_path: str = "src/config/products.yaml",
    ) -> dict[str, Any]:
        """Executa o ciclo completo de monitoramento para todos os produtos ativos."""
        # Sincronizar produtos do arquivo YAML
        self.load_products_from_yaml(config_path)

        products = self.repository.list_active_products()
        if specific_product_id:
            products = [p for p in products if p.id == specific_product_id]

        if not products:
            logger.warning("Nenhum produto ativo encontrado para monitoramento.")
            return {"total_products": 0, "cycles": []}

        summary = {"total_products": len(products), "cycles": []}
        for product in products:
            res = await self.run_cycle_for_product(product, dry_run=dry_run)
            summary["cycles"].append(res)

        return summary
