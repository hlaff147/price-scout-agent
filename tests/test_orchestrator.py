"""Tests for orchestrator coordination and fault isolation."""

from unittest.mock import AsyncMock

import pytest

from src.data.database import Database
from src.data.models import Product, ScrapedData, Source
from src.data.repository import Repository
from src.orchestrator.orchestrator import Orchestrator
from src.subagents.notifier_agent.agent import NotifierSubagent
from src.subagents.price_analyst_agent.agent import PriceAnalystSubagent
from src.subagents.scraper_agent.agent import ScraperSubagent


@pytest.mark.asyncio
class TestOrchestrator:
    async def test_fault_isolation_when_one_scraper_crashes(self):
        """Verifica que o erro em uma fonte não derruba o ciclo das demais."""
        db = Database(":memory:")
        repo = Repository(db)

        product = Product(
            id="test-p",
            nome="Test Product",
            keywords=["Test"],
            preco_alvo=500.0,
            preco_maximo=800.0,
            sources=[
                Source(product_id="test-p", marketplace="mercadolivre", url_produto="https://ml.com"),
                Source(product_id="test-p", marketplace="amazon", url_produto="https://amazon.com"),
                Source(product_id="test-p", marketplace="kabum", url_produto="https://kabum.com"),
            ],
        )
        repo.upsert_product(product)

        # Mock scraper onde o Mercado Livre quebra/lança exceção
        mock_scraper = AsyncMock(spec=ScraperSubagent)

        async def fake_run(source: Source, prod: Product):
            if source.marketplace == "mercadolivre":
                raise ConnectionResetError("Conexão interrompida pelo servidor")
            elif source.marketplace == "amazon":
                return ScrapedData(
                    marketplace="amazon",
                    success=True,
                    titulo="Test Product Amazon",
                    preco=480.0,  # Abaixo do alvo!
                    url="https://amazon.com",
                )
            else:
                return ScrapedData(
                    marketplace="kabum",
                    success=False,
                    url="https://kabum.com",
                    error_message="Produto esgotado",
                )

        mock_scraper.run.side_effect = fake_run

        analyst = PriceAnalystSubagent(repository=repo)
        mock_notifier = AsyncMock(spec=NotifierSubagent)
        mock_notifier.run.return_value = True

        orchestrator = Orchestrator(
            repository=repo,
            scraper=mock_scraper,
            analyst=analyst,
            notifier=mock_notifier,
        )

        result = await orchestrator.run_cycle_for_product(product, dry_run=True)

        # Asserções de isolamento de falha
        assert result["sources_checked"] == 3
        assert result["errors"] == 2  # 1 exceção (ML) + 1 falha sem preço (Kabum)
        assert result["prices_collected"] == 1  # Apenas Amazon
        assert result["deals_found"] == 1  # Amazon com R$ 480 foi identificada como deal

        # Notificador deve ter sido acionado para a Amazon
        assert mock_notifier.run.called
        deal_arg = mock_notifier.run.call_args[0][0]
        assert deal_arg.marketplace == "amazon"
        assert deal_arg.preco_atual == 480.0

    async def test_disabled_sources_are_not_queried(self):
        """Verifica que fontes com ativo=False são ignoradas pelo orquestrador."""
        db = Database(":memory:")
        repo = Repository(db)

        product = Product(
            id="test-p2",
            nome="Test Product 2",
            keywords=["Test"],
            preco_alvo=500.0,
            preco_maximo=800.0,
            sources=[
                Source(
                    product_id="test-p2",
                    marketplace="mercadolivre",
                    url_produto="https://ml.com",
                    ativo=True,
                ),
                Source(
                    product_id="test-p2",
                    marketplace="kabum",
                    url_produto="https://kabum.com",
                    ativo=False,
                    motivo_desativacao="preco_muito_caro",
                ),
                Source(
                    product_id="test-p2",
                    marketplace="aliexpress",
                    url_produto="https://aliexpress.com",
                    ativo=False,
                    motivo_desativacao="imposto_importacao_elevado",
                ),
            ],
        )
        repo.upsert_product(product)

        mock_scraper = AsyncMock(spec=ScraperSubagent)
        mock_scraper.run.return_value = ScrapedData(
            marketplace="mercadolivre",
            success=True,
            titulo="Test Product ML",
            preco=450.0,
            url="https://ml.com",
        )

        orchestrator = Orchestrator(
            repository=repo,
            scraper=mock_scraper,
            analyst=PriceAnalystSubagent(repository=repo),
            notifier=AsyncMock(spec=NotifierSubagent),
        )

        result = await orchestrator.run_cycle_for_product(product, dry_run=True)

        # Apenas 1 fonte ativa deve ter sido checada (Mercado Livre)
        assert result["sources_checked"] == 1
        assert mock_scraper.run.call_count == 1
        called_source = mock_scraper.run.call_args[0][0]
        assert called_source.marketplace == "mercadolivre"
