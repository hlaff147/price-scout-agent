"""Tests for semantic variant deduplication (4a) and Telegram Bot driving adapter (4b)."""

from unittest.mock import patch

import pytest

from src.adapters.telegram_bot.bot_service import TelegramBotService
from src.config.settings import settings
from src.data.database import Database
from src.data.models import Product, ScrapedData, Source
from src.data.repository import Repository
from src.subagents.matcher.hybrid_matcher import HybridProductMatcher
from src.subagents.price_analyst_agent.agent import PriceAnalystSubagent


@pytest.fixture
def temp_repo():
    db = Database(db_path=":memory:")
    return Repository(db)


@pytest.fixture
def matcher():
    return HybridProductMatcher()


# =========================================================================
# 4a. Testes de Deduplicação Semântica de Variantes
# =========================================================================

@pytest.mark.asyncio
async def test_matcher_rejects_accessory_listings(matcher):
    """Testa se anúncios que são apenas acessórios (capinhas/películas) são descartados."""
    product = Product(
        id="kindle-paperwhite-16gb",
        nome="Kindle Paperwhite 16GB",
        keywords=["Kindle Paperwhite"],
        preco_alvo=650.0,
        preco_maximo=800.0,
    )

    result = await matcher.match(
        target=product,
        candidate_title="Capa Capinha Magnética Protetora Para Kindle Paperwhite 16GB",
    )
    assert result.is_match is False
    assert "acessório" in result.divergence_reason.lower() or "secundária" in result.divergence_reason.lower()


@pytest.mark.asyncio
async def test_matcher_rejects_global_vs_national_divergence(matcher):
    """Testa a premissa de negócio: Edição Global NÃO deve ser deduplicada como Nacional."""
    product_national = Product(
        id="huawei-br",
        nome="Huawei FreeBuds Pro 5 Nacional Anatel",
        keywords=["Nacional", "Anatel", "FreeBuds Pro 5"],
        preco_alvo=850.0,
        preco_maximo=1100.0,
    )

    result = await matcher.match(
        target=product_national,
        candidate_title="Huawei FreeBuds Pro 5 Versão Global Importado Sem Taxa",
    )
    assert result.is_match is False
    assert "global" in result.divergence_reason.lower() or "importada" in result.divergence_reason.lower()


@pytest.mark.asyncio
async def test_matcher_rejects_divergent_memory_capacity(matcher):
    """Testa se variações de capacidade de memória diferente são rejeitadas."""
    product = Product(
        id="kindle-16gb",
        nome="Kindle Paperwhite 16GB",
        keywords=["Kindle Paperwhite 16GB"],
        preco_alvo=650.0,
        preco_maximo=800.0,
    )

    result = await matcher.match(
        target=product,
        candidate_title="Novo Kindle Paperwhite 32GB Signature Edition À Prova D'água",
    )
    assert result.is_match is False
    assert "32gb" in result.divergence_reason.lower()


@pytest.mark.asyncio
async def test_matcher_accepts_valid_product_and_detects_color(matcher):
    """Testa produto correspondente com extração de variante de cor."""
    product = Product(
        id="huawei-freebuds-pro-5",
        nome="Huawei FreeBuds Pro 5",
        keywords=["Huawei FreeBuds Pro 5", "FreeBuds Pro 5"],
        preco_alvo=850.0,
        preco_maximo=1100.0,
    )

    result = await matcher.match(
        target=product,
        candidate_title="Fone de Ouvido Bluetooth Huawei FreeBuds Pro 5 Cancelamento de Ruído Branco",
    )
    assert result.is_match is True
    assert result.detected_variant == "Cor: Branco"


@pytest.mark.asyncio
async def test_analyst_ignores_deal_when_variant_diverges(temp_repo):
    """Testa se o Analista de Preço ignora ofertas mesmo muito baratas caso seja variante errada."""
    product = Product(
        id="huawei-freebuds-pro-5",
        nome="Huawei FreeBuds Pro 5",
        keywords=["FreeBuds Pro 5"],
        preco_alvo=850.0,
        preco_maximo=1100.0,
    )
    temp_repo.upsert_product(product)

    source = temp_repo.upsert_source(
        Source(product_id=product.id, marketplace="mercadolivre", url_produto="http://ml.com")
    )
    analyst = PriceAnalystSubagent(repository=temp_repo)

    # Anúncio de capinha muito barato (R$ 39.90) que estaria abaixo do alvo de 850
    scraped_pairs = [
        (
            source,
            ScrapedData(
                marketplace="mercadolivre",
                success=True,
                preco=39.90,
                titulo="Capa Case Protetora de Silicone Para Huawei FreeBuds Pro 5",
                url="http://ml.com/capa",
            ),
        )
    ]

    analyses = await analyst.run(product, scraped_pairs)
    assert len(analyses) == 1
    analysis = analyses[0]
    # NÃO deve ser considerado deal por ser acessório
    assert analysis.is_deal is False
    assert "desconsiderada" in analysis.justificativa.lower() or "divergente" in analysis.justificativa.lower()


# =========================================================================
# 4b. Testes do Bot Conversacional no Telegram (Driving Adapter)
# =========================================================================

@pytest.mark.asyncio
async def test_telegram_bot_unauthorized_access(temp_repo):
    """Testa se o bot bloqueia comandos originados de chat_ids não autorizados."""
    with patch.object(settings, "TELEGRAM_CHAT_ID", "12345"):
        bot = TelegramBotService(repository=temp_repo)
        response = await bot.handle_command(chat_id=99999, text="/list")
        assert "Acesso Negado" in response
        assert "99999" in response


@pytest.mark.asyncio
async def test_telegram_bot_authorized_commands(temp_repo):
    """Testa a execução de comandos administrativos por usuário autorizado."""
    with patch.object(settings, "TELEGRAM_CHAT_ID", "12345"):
        bot = TelegramBotService(repository=temp_repo)
        auth_chat = "12345"

        # 1. /help
        help_resp = await bot.handle_command(auth_chat, "/help")
        assert "Comandos disponíveis" in help_resp

        # 2. /add
        add_resp = await bot.handle_command(
            auth_chat,
            "/add fone-sony Sony WH-1000XM5 1500 1800 high",
        )
        assert "cadastrado com sucesso" in add_resp.lower()

        # 3. /list
        list_resp = await bot.handle_command(auth_chat, "/list")
        assert "Sony WH-1000XM5" in list_resp
        assert "HIGH" in list_resp

        # 4. /priority
        prio_resp = await bot.handle_command(auth_chat, "/priority fone-sony low")
        assert "LOW" in prio_resp
        assert "alterada para" in prio_resp

        # 5. /pause e /resume
        pause_resp = await bot.handle_command(auth_chat, "/pause fone-sony")
        assert "pausado com sucesso" in pause_resp
        p_paused = temp_repo.get_product("fone-sony")
        assert p_paused.ativo is False

        resume_resp = await bot.handle_command(auth_chat, "/resume fone-sony")
        assert "retomado com sucesso" in resume_resp
        p_resumed = temp_repo.get_product("fone-sony")
        assert p_resumed.ativo is True

        # 6. /status
        status_resp = await bot.handle_command(auth_chat, "/status")
        assert "Online e operante" in status_resp

        # 7. /coupons
        coupons_empty = await bot.handle_command(auth_chat, "/coupons")
        assert "Nenhum cupom ativo" in coupons_empty

        from src.data.models import Coupon
        temp_repo.save_coupon(Coupon(marketplace="amazon", codigo="BOTTEST10", desconto_percentual=10.0))
        coupons_resp = await bot.handle_command(auth_chat, "/coupons")
        assert "BOTTEST10" in coupons_resp
        assert "10% OFF" in coupons_resp

