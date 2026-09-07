"""Tests for price analyst subagent and fake discount detection skill."""

import pytest

from src.data.database import Database
from src.data.models import PriceRecord, Product, ScrapedData, Source
from src.data.repository import Repository
from src.skills.detect_fake_discount.detector import DetectFakeDiscountSkill
from src.subagents.price_analyst_agent.agent import PriceAnalystSubagent


class TestDetectFakeDiscount:
    def test_detect_fake_discount_heuristic(self):
        detector = DetectFakeDiscountSkill()

        # Loja anuncia "De R$ 2.400 por R$ 850", mas a média histórica real é R$ 900
        announced_disc, real_disc, is_fake = detector.execute(
            current_price=850.0,
            original_price_announced=2400.0,
            historical_avg=900.0,
            user_max_price=1100.0,
        )

        assert is_fake is True
        assert announced_disc > 60.0
        assert real_disc < 10.0  # O desconto real é pequeno vs a média de 900

    def test_legitimate_discount(self):
        detector = DetectFakeDiscountSkill()

        # Preço original consistente com histórico (R$ 1.100 vs R$ 1.050 histórico)
        _announced_disc, real_disc, is_fake = detector.execute(
            current_price=750.0,
            original_price_announced=1050.0,
            historical_avg=1000.0,
            user_max_price=1100.0,
        )

        assert is_fake is False
        assert real_disc == 25.0

    def test_detect_fake_discount_without_historical_avg(self):
        detector = DetectFakeDiscountSkill()

        # Dia 1: Sem média histórica (None), mas preço original anunciado muito superior ao user_max_price
        announced_disc, real_disc, is_fake = detector.execute(
            current_price=800.0,
            original_price_announced=2000.0,
            historical_avg=None,
            user_max_price=1000.0,
        )

        assert is_fake is True
        assert real_disc is None
        assert announced_disc == 60.0


@pytest.mark.asyncio
class TestPriceAnalystSubagent:
    async def test_detects_all_time_low_and_target_hit(self):
        db = Database(":memory:")
        repo = Repository(db)

        product = Product(
            id="test-earbuds",
            nome="Test Earbuds",
            keywords=["Test Earbuds"],
            preco_alvo=850.0,
            preco_maximo=1000.0,
        )
        repo.upsert_product(product)

        source = Source(
            product_id="test-earbuds",
            marketplace="mercadolivre",
            url_produto="https://test.com",
        )
        repo.upsert_source(source)

        analyst = PriceAnalystSubagent(repository=repo)

        # Primeiro ciclo: Preço regular R$ 920 (acima do alvo 850)
        scraped_1 = ScrapedData(
            marketplace="mercadolivre",
            success=True,
            titulo="Test Earbuds",
            preco=920.0,
            url="https://test.com",
        )
        analyses_1 = await analyst.run(product, [(source, scraped_1)])
        assert len(analyses_1) == 1
        assert analyses_1[0].is_deal is False  # Não é oferta ainda

        # Segundo ciclo: Preço cai para R$ 799 (Abaixo do alvo E Menor Histórico)
        scraped_2 = ScrapedData(
            marketplace="mercadolivre",
            success=True,
            titulo="Test Earbuds",
            preco=799.0,
            url="https://test.com",
        )
        analyses_2 = await analyst.run(product, [(source, scraped_2)])
        assert len(analyses_2) == 1
        assert analyses_2[0].is_deal is True
        assert analyses_2[0].is_all_time_low is True
        assert analyses_2[0].is_below_target is True
        assert analyses_2[0].motivo_alerta == "minimo_historico"

    async def test_multiple_sources_in_same_cycle_share_stable_baseline(self):
        db = Database(":memory:")
        repo = Repository(db)

        product = Product(
            id="multi-test",
            nome="Multi Test",
            preco_alvo=850.0,
            preco_maximo=1000.0,
        )
        repo.upsert_product(product)

        src_a = repo.upsert_source(Source(product_id="multi-test", marketplace="amazon", url_produto="https://a.com"))
        src_b = repo.upsert_source(Source(product_id="multi-test", marketplace="mercadolivre", url_produto="https://b.com"))

        # Histórico prévio no banco: R$ 900
        repo.save_price_record(PriceRecord(source_id=src_a.id, preco=900.0))

        analyst = PriceAnalystSubagent(repository=repo)

        # No ciclo atual, Amazon acha R$ 800 e Mercado Livre acha R$ 810.
        # Ambos estão abaixo da mínima histórica prévia (900.0).
        # A inserção de R$ 800 da Amazon NÃO deve contaminar a análise do Mercado Livre no mesmo lote!
        scraped_a = ScrapedData(marketplace="amazon", success=True, preco=800.0, url="https://a.com")
        scraped_b = ScrapedData(marketplace="mercadolivre", success=True, preco=810.0, url="https://b.com")

        results = await analyst.run(product, [(src_a, scraped_a), (src_b, scraped_b)])
        assert len(results) == 2

        # Ambos os marketplaces devem ter comparado com o prev_min pré-ciclo (900.0)
        assert results[0].preco_minimo_historico == 900.0
        assert results[1].preco_minimo_historico == 900.0
        assert results[0].is_all_time_low is True
        assert results[1].is_all_time_low is True
