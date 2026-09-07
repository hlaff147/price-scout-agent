"""High-level runner integrating Google ADK Runner with PromoRadar monitoring."""

import uuid
from typing import Any

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from loguru import logger

from src.agents.coordinator import build_promoradar_adk_pipeline
from src.config.settings import settings
from src.core.ports.analyst_port import IAnalyst
from src.core.ports.notifier_port import INotifier
from src.core.ports.repository_port import IRepository
from src.core.ports.scraper_port import IScraper
from src.data.database import default_db
from src.data.models import Product
from src.data.repository import Repository
from src.orchestrator.orchestrator import Orchestrator
from src.reporting.report_generator import ReportGenerator


class AdkMonitoringRunner:
    """Runner de monitoramento baseado no Google ADK e Arquitetura Hexagonal."""

    def __init__(
        self,
        repository: IRepository | None = None,
        scraper: IScraper | None = None,
        analyst: IAnalyst | None = None,
        notifier: INotifier | None = None,
        report_generator: ReportGenerator | None = None,
    ):
        self.repository = repository or Repository(default_db)
        self.scraper = scraper
        self.analyst = analyst
        self.notifier = notifier
        self.report_generator = report_generator
        self.session_service = InMemorySessionService()

    async def run_cycle(
        self,
        product_id: str | None = None,
        dry_run: bool | None = None,
        generate_report: bool = True,
        open_browser: bool = True,
        config_path: str = "src/config/products.yaml",
    ) -> dict[str, Any]:
        """Executa o ciclo completo de monitoramento via pipeline do Google ADK."""
        is_dry_run = dry_run if dry_run is not None else settings.DRY_RUN

        # 1. Carregar produtos sincronizados
        orchestrator_helper = Orchestrator(repository=self.repository)
        orchestrator_helper.load_products_from_yaml(config_path)

        products: list[Product] = self.repository.list_active_products()
        if product_id:
            products = [p for p in products if p.id == product_id]

        if not products:
            logger.warning("Nenhum produto ativo encontrado para monitoramento no ADK Runner.")
            return {"total_products": 0, "cycles": []}

        summary: dict[str, Any] = {"total_products": len(products), "cycles": []}

        for product in products:
            product_cycle = await self._run_single_product_adk(
                product=product,
                dry_run=is_dry_run,
                generate_report=generate_report,
                open_browser=open_browser,
            )
            summary["cycles"].append(product_cycle)

        return summary

    async def _run_single_product_adk(
        self,
        product: Product,
        dry_run: bool,
        generate_report: bool,
        open_browser: bool,
    ) -> dict[str, Any]:
        """Executa uma sessão do Google ADK para um único produto."""
        logger.info(f"=== [Google ADK] Iniciando ciclo para: {product.nome} ===")

        # Obter fontes ativas
        sources = self.repository.get_active_sources_for_product(product.id)

        # 1. Criar sessão isolada no ADK SessionService com estado inicial
        user_id = "promoradar_daemon"
        session_id = str(uuid.uuid4())
        initial_state = {
            "product": product,
            "sources": sources,
            "dry_run": dry_run,
            "generate_report": generate_report,
            "open_browser": open_browser,
        }
        session = await self.session_service.create_session(
            app_name="promoradar",
            user_id=user_id,
            session_id=session_id,
            state=initial_state,
        )

        # 2. Construir pipeline ADK
        clean_id = product.id.replace("-", "_")
        pipeline = build_promoradar_adk_pipeline(
            scraper=self.scraper,
            analyst=self.analyst,
            notifier=self.notifier,
            report_generator=self.report_generator,
            name=f"coordinator_{clean_id}",
        )

        # 3. Executar via ADK Runner
        runner = Runner(
            agent=pipeline,
            session_service=self.session_service,
            app_name="promoradar",
        )

        trigger_msg = types.Content(
            parts=[types.Part.from_text(text=f"Iniciar monitoramento de {product.nome}")]
        )

        async for event in runner.run_async(
            session_id=session.id,
            user_id=user_id,
            new_message=trigger_msg,
        ):
            if event.content:
                for part in event.content.parts:
                    if part.text:
                        logger.info(f"[{event.author}] {part.text}")

        # 4. Extrair resultados consolidados do estado final persistido da sessão
        final_session = await self.session_service.get_session(
            app_name="promoradar",
            user_id=user_id,
            session_id=session.id,
        )
        state = final_session.state if final_session else session.state

        return {
            "product_id": product.id,
            "sources_checked": state.get("sources_checked", len(sources)),
            "prices_collected": state.get("prices_collected", 0),
            "deals_found": state.get("deals_found", 0),
            "no_results": state.get("no_results", 0),
            "errors": state.get("errors", 0),
            "analyses": state.get("analyses", []),
            "report_path": state.get("report_path"),
        }
