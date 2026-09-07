"""Tests for Phase 4: Self-Healing CSS selector repair with Gemini and Sandbox validation."""

import pytest

from src.data.database import Database
from src.data.models import Product, Source
from src.data.repository import Repository
from src.subagents.healing_agent.agent import GeminiHealerSubagent
from src.subagents.healing_agent.sanitizer import sanitize_html_for_llm
from src.subagents.scraper_agent.extractor import extract_with_overrides
from src.subagents.scraper_agent.http_adapter import HttpScraperSubagent


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
        id="monitor-dell-27",
        nome="Monitor Dell 27 4K",
        keywords=["Dell", "Monitor", "27"],
        preco_alvo=2000.0,
        preco_maximo=2500.0,
    )


def test_sanitize_html_for_llm():
    raw_html = """
    <html>
        <head>
            <script>alert('malicious')</script>
            <style>.hide { display: none; }</style>
        </head>
        <body>
            <svg><path d="M0 0h24v24H0z"/></svg>
            <!-- Comentário interno -->
            <div class="product-wrapper" id="item-123">
                <h1 class="new-title-class">Monitor Dell 27 4K Ultra HD</h1>
                <span class="new-price-class">R$ 2.199,00</span>
            </div>
            <iframe>publicidade</iframe>
        </body>
    </html>
    """
    cleaned = sanitize_html_for_llm(raw_html)

    assert "<script" not in cleaned
    assert "<style" not in cleaned
    assert "<svg" not in cleaned
    assert "<iframe" not in cleaned
    assert "Comentário interno" not in cleaned
    assert "Monitor Dell 27 4K Ultra HD" in cleaned
    assert "2.199,00" in cleaned
    assert "new-title-class" in cleaned
    assert "new-price-class" in cleaned


def test_validate_selectors_in_sandbox_success(repo, sample_product):
    healer = GeminiHealerSubagent(repository=repo)
    html = """
    <div class="card-container">
        <h2 class="broken-title">Monitor Dell 27 4K S2721QS</h2>
        <div class="price-box">
            <span class="current-price">R$ 2.150,00</span>
        </div>
    </div>
    """
    selectors = {
        "container": "div.card-container",
        "titulo": "h2.broken-title",
        "preco": "span.current-price",
    }
    is_valid, price, title, reason = healer.validate_selectors_in_sandbox(
        html_content=html,
        selectors=selectors,
        product=sample_product,
    )
    assert is_valid is True
    assert price == 2150.0
    assert title == "Monitor Dell 27 4K S2721QS"
    assert "sucesso" in reason.lower()


def test_validate_selectors_in_sandbox_rejects_irrelevant_title(repo, sample_product):
    healer = GeminiHealerSubagent(repository=repo)
    html = """
    <div class="card-container">
        <h2 class="title">Cabo HDMI 2.0 1.5 metros</h2>
        <span class="price">R$ 25,00</span>
    </div>
    """
    selectors = {
        "container": "div.card-container",
        "titulo": "h2.title",
        "preco": "span.price",
    }
    is_valid, _price, _title, reason = healer.validate_selectors_in_sandbox(
        html_content=html,
        selectors=selectors,
        product=sample_product,
    )
    assert is_valid is False
    assert "palavras-chave" in reason.lower()


def test_validate_selectors_in_sandbox_rejects_implausible_price(repo, sample_product):
    healer = GeminiHealerSubagent(repository=repo)
    # Preco alvo = 2000, maximo = 2500. 150.0 está abaixo de 0.3 * 2000 (600.0)
    html = """
    <div class="card-container">
        <h2 class="title">Monitor Dell 27 4K</h2>
        <span class="price">R$ 150,00</span>
    </div>
    """
    selectors = {
        "container": "div.card-container",
        "titulo": "h2.title",
        "preco": "span.price",
    }
    is_valid, _price, _title, reason = healer.validate_selectors_in_sandbox(
        html_content=html,
        selectors=selectors,
        product=sample_product,
    )
    assert is_valid is False
    assert "plausível" in reason.lower()


def test_extract_with_overrides():
    html = """
    <div class="offer">
        <a class="prod-link">Monitor Dell 27 4K Pro</a>
        <div class="price-val">R$ 2.050,50</div>
    </div>
    """
    overrides = {
        "container": "div.offer",
        "titulo": "a.prod-link",
        "preco": "div.price-val",
    }
    res = extract_with_overrides(html, overrides, "https://example.com", "mercadolivre")
    assert res is not None
    assert res.success is True
    assert res.preco == 2050.50
    assert res.titulo == "Monitor Dell 27 4K Pro"


@pytest.mark.asyncio
async def test_healer_full_cycle_with_mock_llm(repo, sample_product):
    html = """
    <div class="new-layout-card">
        <p class="heading">Monitor Dell 27 Polegadas 4K UHD</p>
        <strong class="val">R$ 2.200,00</strong>
    </div>
    """

    async def mock_llm(marketplace, product, sanitized_html, current_selectors):
        return {
            "container": "div.new-layout-card",
            "titulo": "p.heading",
            "preco": "strong.val",
        }

    healer = GeminiHealerSubagent(repository=repo, llm_client=mock_llm)

    result = await healer.heal(
        marketplace="kabum",
        product=sample_product,
        html_content=html,
        current_selectors={"titulo": "span.old-name", "preco": "span.old-price"},
    )

    assert result.healed is True
    assert result.validation_success is True
    assert result.validation_price == 2200.0

    # Verifica se os seletores foram persistidos no banco
    overrides = repo.get_active_overrides("kabum")
    assert overrides["titulo"] == "p.heading"
    assert overrides["preco"] == "strong.val"
    assert overrides["container"] == "div.new-layout-card"


@pytest.mark.asyncio
async def test_healer_circuit_breaker(repo, sample_product):
    # Simula 2 tentativas anteriores nas últimas 24h
    repo.record_healing_attempt("amazon")
    repo.record_healing_attempt("amazon")

    assert repo.has_exceeded_healing_attempts("amazon", max_attempts=2, hours=24) is True

    healer = GeminiHealerSubagent(repository=repo)
    result = await healer.heal(
        marketplace="amazon",
        product=sample_product,
        html_content="<div>Amazon test</div>",
        current_selectors={},
    )

    assert result.healed is False
    assert "circuit breaker" in result.reason.lower()


@pytest.mark.asyncio
async def test_http_scraper_uses_overrides_and_triggers_healing(repo, sample_product):
    class MockHttpClient:
        async def fetch(self, url: str) -> str:
            # HTML com layout alterado onde o parser padrão falharia
            return """
            <div class="custom-card">
                <span class="custom-name">Monitor Dell 27 4K IPS</span>
                <span class="custom-cost">R$ 2.180,00</span>
            </div>
            """

    async def mock_llm(marketplace, product, sanitized_html, current_selectors):
        return {
            "container": "div.custom-card",
            "titulo": "span.custom-name",
            "preco": "span.custom-cost",
        }

    healer = GeminiHealerSubagent(repository=repo, llm_client=mock_llm)
    scraper = HttpScraperSubagent(
        client=MockHttpClient(),
        selector_repo=repo,
        healer=healer,
    )

    source = Source(
        product_id=sample_product.id,
        marketplace="kabum",
        url_produto="https://www.kabum.com.br/produto/123",
    )

    # 1. Primeira execução: parser padrão falha -> healer aciona -> repara seletores -> salva -> retorna preco
    res = await scraper.run(source, sample_product)
    assert res.success is True
    assert res.preco == 2180.0
    assert "Monitor Dell 27 4K IPS" in res.titulo

    # 2. Segunda execução: deve usar diretamente os seletores do banco (sem chamar o healer)
    scraper.healer = None
    res2 = await scraper.run(source, sample_product)
    assert res2.success is True
    assert res2.preco == 2180.0
