"""Tests for Phase 5: Coupon and promotional code detection, persistence, and alerts."""

import pytest

from src.data.database import Database
from src.data.models import Coupon, Product, ScrapedData, Source
from src.data.repository import Repository
from src.skills.format_alert.formatter import FormatAlertSkill
from src.skills.parse_coupon.parser import ParseCouponSkill
from src.subagents.notifier_agent.agent import NotifierSubagent
from src.subagents.price_analyst_agent.agent import PriceAnalystSubagent


@pytest.fixture
def memory_db():
    db = Database(":memory:")
    db.init_db()
    return db


@pytest.fixture
def repo(memory_db):
    return Repository(memory_db)


@pytest.fixture
def sample_product():
    return Product(
        id="tv-samsung-55",
        nome="Smart TV Samsung 55 4K",
        keywords=["Samsung", "55", "TV"],
        preco_alvo=2500.0,
        preco_maximo=3000.0,
    )


def test_parse_coupon_skill_percentage():
    raw = "Aproveite 10% OFF com o cupom SAMSUNG10"
    coupon = ParseCouponSkill.parse(raw, marketplace="mercadolivre", product_id="tv-samsung-55")

    assert coupon is not None
    assert coupon.codigo == "SAMSUNG10"
    assert coupon.desconto_percentual == 10.0
    assert coupon.desconto_fixo is None
    assert coupon.marketplace == "mercadolivre"


def test_parse_coupon_skill_fixed_amount():
    raw = "R$ 150 OFF no carrinho usando código DESC150"
    coupon = ParseCouponSkill.parse(raw, marketplace="amazon", product_id="tv-samsung-55")

    assert coupon is not None
    assert coupon.codigo == "DESC150"
    assert coupon.desconto_fixo == 150.0
    assert coupon.desconto_percentual is None


def test_parse_coupon_skill_simple_code():
    raw = "PROMOTV"
    coupon = ParseCouponSkill.parse(raw, marketplace="kabum")

    assert coupon is not None
    assert coupon.codigo == "PROMOTV"


def test_parse_coupon_skill_derived_code_when_missing():
    raw = "5% de desconto à vista"
    coupon = ParseCouponSkill.parse(raw, marketplace="shopee")

    assert coupon is not None
    assert coupon.codigo == "SHOPEE-5OFF"
    assert coupon.desconto_percentual == 5.0


def test_coupon_repository_crud_and_recency(repo):
    c1 = Coupon(
        marketplace="amazon",
        codigo="AMZTECH",
        descricao="10% OFF em eletrônicos",
        desconto_percentual=10.0,
    )
    saved = repo.save_coupon(c1)
    assert saved.id is not None

    # Busca específica
    fetched = repo.get_coupon("amazon", "AMZTECH")
    assert fetched is not None
    assert fetched.codigo == "AMZTECH"
    assert fetched.desconto_percentual == 10.0

    # Teste de recência
    assert repo.is_coupon_recent("amazon", "AMZTECH", hours=24) is True
    assert repo.is_coupon_recent("amazon", "CUPOM_INEXISTENTE", hours=24) is False

    # Listagem por marketplace
    c2 = Coupon(
        marketplace="kabum",
        codigo="KABUM5",
        desconto_percentual=5.0,
    )
    repo.save_coupon(c2)

    active_amz = repo.list_active_coupons(marketplace="amazon")
    assert len(active_amz) == 1
    assert active_amz[0].codigo == "AMZTECH"

    all_active = repo.list_active_coupons()
    assert len(all_active) == 2


@pytest.mark.asyncio
async def test_price_analyst_triggers_deal_due_to_coupon(repo, sample_product):
    repo.upsert_product(sample_product)
    source = Source(
        product_id=sample_product.id,
        marketplace="mercadolivre",
        url_produto="https://mercadolivre.com.br/tv",
    )
    source = repo.upsert_source(source)

    # Preço anunciado = 2.700 (acima do alvo de 2.500).
    # Com cupom de 10% (R$ 270 de desconto) -> R$ 2.430 (abaixo do alvo de 2.500)!
    scraped = ScrapedData(
        marketplace="mercadolivre",
        success=True,
        titulo="Smart TV Samsung 55 4K Crystal UHD",
        preco=2700.0,
        preco_original=3000.0,
        cupom="10% OFF com cupom SMART10",
        url=source.url_produto,
    )

    analyst = PriceAnalystSubagent(repository=repo)
    analyses = await analyst.run(sample_product, [(source, scraped)])

    assert len(analyses) == 1
    analysis = analyses[0]
    assert analysis.is_deal is True
    assert analysis.motivo_alerta == "cupom_promocional"
    assert "SMART10" in analysis.justificativa

    # Verifica se o cupom foi automaticamente registrado no banco
    saved_coupon = repo.get_coupon("mercadolivre", "SMART10")
    assert saved_coupon is not None
    assert saved_coupon.desconto_percentual == 10.0


def test_format_coupon_alert_message(sample_product):
    coupon = Coupon(
        marketplace="kabum",
        codigo="GAMER10",
        desconto_percentual=10.0,
    )
    msg = FormatAlertSkill.format_coupon_message(
        coupon=coupon,
        product=sample_product,
        final_price=2250.0,
        url="https://kabum.com.br/tv",
    )
    assert "NOVO CUPOM DE DESCONTO DETECTADO!" in msg
    assert "GAMER10" in msg
    assert "10% OFF" in msg
    assert sample_product.nome in msg
    assert "2.250,00" in msg


@pytest.mark.asyncio
async def test_notifier_subagent_notify_coupon_dry_run(repo, sample_product):
    notifier = NotifierSubagent(repository=repo)
    coupon = Coupon(
        marketplace="shopee",
        codigo="SHOPEE50",
        desconto_fixo=50.0,
    )
    success = await notifier.notify_coupon(
        coupon=coupon,
        product=sample_product,
        final_price=2450.0,
        url="https://shopee.com.br/tv",
        dry_run=True,
    )
    assert success is True
