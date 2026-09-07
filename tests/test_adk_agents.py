"""Integration and unit tests for Google ADK agents and coordinator."""

import pytest
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from src.agents.adk_runner import AdkMonitoringRunner
from src.agents.coordinator import build_promoradar_adk_pipeline
from src.core.ports.analyst_port import IAnalyst
from src.core.ports.notifier_port import INotifier
from src.core.ports.repository_port import IRepository
from src.core.ports.scraper_port import IScraper
from src.data.models import DealAnalysis, Product, ScrapedData, Source


class MockScraper(IScraper):
    async def run(self, source: Source, product: Product) -> ScrapedData:
        return ScrapedData(
            marketplace=source.marketplace,
            success=True,
            titulo=f"{product.nome} Original",
            preco=700.0,
            url=source.url_produto,
        )


class MockAnalyst(IAnalyst):
    async def run(self, product: Product, scraped_results: list[tuple[Source, ScrapedData]]) -> list[DealAnalysis]:
        return [
            DealAnalysis(
                product_id=product.id,
                source_id=1,
                marketplace="amazon",
                preco_atual=700.0,
                is_below_target=True,
                is_deal=True,
                motivo_alerta="abaixo_do_alvo",
                justificativa="Preço alvo atingido!",
                url="https://amazon.com.br/test",
            )
        ]


class MockNotifier(INotifier):
    async def run(self, deal: DealAnalysis, product: Product, dry_run: bool = False) -> bool:
        return True


class MockRepository(IRepository):
    def upsert_product(self, product: Product) -> Product:
        return product

    def get_product(self, product_id: str) -> Product | None:
        return Product(
            id=product_id,
            nome="Fone Teste",
            preco_alvo=800.0,
            preco_maximo=1000.0,
        )

    def list_active_products(self) -> list[Product]:
        return [
            Product(
                id="fone-teste",
                nome="Fone Teste",
                preco_alvo=800.0,
                preco_maximo=1000.0,
            )
        ]

    def upsert_source(self, source: Source) -> Source:
        return source

    def get_sources_for_product(self, product_id: str) -> list[Source]:
        return [Source(product_id=product_id, marketplace="amazon", url_produto="https://amazon.com/test")]

    def get_active_sources_for_product(self, product_id: str) -> list[Source]:
        return [Source(product_id=product_id, marketplace="amazon", url_produto="https://amazon.com/test")]

    def save_price_record(self, record):
        return record

    def get_price_history(self, product_id, days=90):
        return []

    def get_price_history_by_source(self, source_id, days=90):
        return []

    def get_historical_min_price(self, product_id):
        return 750.0

    def get_historical_average_price(self, product_id, days=60):
        return 850.0

    def save_alert(self, alert):
        return alert

    def has_recent_alert(self, product_id, hours=12):
        return False

    def get_recent_alerts(self, product_id, limit=10):
        return []


@pytest.mark.asyncio
async def test_adk_pipeline_execution_with_mock_adapters():
    pipeline = build_promoradar_adk_pipeline(
        scraper=MockScraper(),
        analyst=MockAnalyst(),
        notifier=MockNotifier(),
        name="test_coordinator",
    )

    session_service = InMemorySessionService()
    product = Product(id="fone-teste", nome="Fone Teste", preco_alvo=800.0, preco_maximo=1000.0)
    sources = [Source(product_id="fone-teste", marketplace="amazon", url_produto="https://amazon.com/test")]

    session = await session_service.create_session(
        app_name="test_app",
        user_id="user1",
        session_id="session_123",
        state={
            "product": product,
            "sources": sources,
            "dry_run": True,
            "generate_report": False,
        },
    )

    runner = Runner(agent=pipeline, session_service=session_service, app_name="test_app")
    trigger = types.Content(parts=[types.Part.from_text(text="run")])

    events = []
    async for event in runner.run_async(session_id=session.id, user_id="user1", new_message=trigger):
        events.append(event)

    assert len(events) >= 3

    final_session = await session_service.get_session(app_name="test_app", user_id="user1", session_id=session.id)
    assert final_session is not None
    assert final_session.state["sources_checked"] == 1
    assert final_session.state["prices_collected"] == 1
    assert final_session.state["deals_found"] == 1
    assert final_session.state["notifications_sent"] == 1


@pytest.mark.asyncio
async def test_adk_monitoring_runner_with_mock_repo():
    mock_repo = MockRepository()
    runner = AdkMonitoringRunner(
        repository=mock_repo,
        scraper=MockScraper(),
        analyst=MockAnalyst(),
        notifier=MockNotifier(),
    )

    summary = await runner.run_cycle(
        product_id="fone-teste",
        dry_run=True,
        generate_report=False,
    )

    assert summary["total_products"] == 1
    cycle = summary["cycles"][0]
    assert cycle["product_id"] == "fone-teste"
    assert cycle["prices_collected"] == 1
    assert cycle["deals_found"] == 1
    assert cycle["errors"] == 0
