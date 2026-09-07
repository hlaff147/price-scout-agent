"""Tests for Playwright scraper adapter, browser pool and composite dispatcher."""

from unittest.mock import AsyncMock

import pytest

from src.data.models import Product, ScrapedData, Source
from src.subagents.scraper_agent.agent import ScraperSubagent
from src.subagents.scraper_agent.playwright_adapter import PlaywrightScraperSubagent
from src.tools.browser_pool import PlaywrightBrowserPool


@pytest.fixture
def sample_product():
    return Product(
        id="huawei-freebuds-pro-5",
        nome="Huawei FreeBuds Pro 5",
        keywords=["FreeBuds", "Huawei"],
        preco_alvo=850.0,
        preco_maximo=1100.0,
    )


def test_browser_pool_initialization():
    """Valida configuração inicial e concorrência do pool de navegadores."""
    pool = PlaywrightBrowserPool(max_concurrent=3, timeout_ms=15000)
    assert pool.max_concurrent == 3
    assert pool.timeout_ms == 15000
    assert pool._semaphore._value == 3


@pytest.mark.asyncio
async def test_scraper_subagent_routes_to_browser(sample_product):
    """Testa se fontes com metodo_coleta='browser' são encaminhadas para o Playwright."""
    mock_http = AsyncMock()
    mock_browser = AsyncMock()
    mock_browser.run.return_value = ScrapedData(
        marketplace="shopee", success=True, url="http://shopee.com", preco=799.0
    )

    composite = ScraperSubagent(
        http_scraper=mock_http,
        browser_scraper=mock_browser,
    )

    source = Source(
        product_id=sample_product.id,
        marketplace="shopee",
        url_produto="https://shopee.com.br/search?keyword=Huawei",
        metodo_coleta="browser",
    )

    result = await composite.run(source, sample_product)

    assert result.success is True
    assert result.preco == 799.0
    mock_browser.run.assert_awaited_once_with(source, sample_product)
    mock_http.run.assert_not_called()


@pytest.mark.asyncio
async def test_scraper_subagent_routes_to_http(sample_product):
    """Testa se fontes com metodo_coleta='scraping_html' usam HTTP."""
    mock_http = AsyncMock()
    mock_browser = AsyncMock()
    mock_http.run.return_value = ScrapedData(
        marketplace="amazon", success=True, url="http://amazon.com", preco=820.0
    )

    composite = ScraperSubagent(
        http_scraper=mock_http,
        browser_scraper=mock_browser,
    )

    source = Source(
        product_id=sample_product.id,
        marketplace="amazon",
        url_produto="https://amazon.com.br/s?k=Huawei",
        metodo_coleta="scraping_html",
    )

    result = await composite.run(source, sample_product)

    assert result.success is True
    assert result.preco == 820.0
    mock_http.run.assert_awaited_once_with(source, sample_product)
    mock_browser.run.assert_not_called()


@pytest.mark.asyncio
async def test_scraper_subagent_dynamic_fallback(sample_product):
    """Testa fallback automático para Playwright quando HTTP indica necessidade de JS."""
    mock_http = AsyncMock()
    mock_browser = AsyncMock()

    # HTTP falha com indicação de JS/SPA
    mock_http.run.return_value = ScrapedData(
        marketplace="shopee",
        success=False,
        url="http://shopee.com",
        error_message="Página SPA requer JavaScript para renderização",
    )
    # Browser é acionado em fallback e obtém o preço com sucesso
    mock_browser.run.return_value = ScrapedData(
        marketplace="shopee",
        success=True,
        url="http://shopee.com",
        preco=849.0,
    )

    composite = ScraperSubagent(
        http_scraper=mock_http,
        browser_scraper=mock_browser,
        enable_fallback=True,
    )

    source = Source(
        product_id=sample_product.id,
        marketplace="shopee",
        url_produto="https://shopee.com.br/search?keyword=Huawei",
        metodo_coleta="scraping_html",
    )

    result = await composite.run(source, sample_product)

    assert result.success is True
    assert result.preco == 849.0
    mock_http.run.assert_awaited_once_with(source, sample_product)
    mock_browser.run.assert_awaited_once_with(source, sample_product)


@pytest.mark.asyncio
async def test_playwright_scraper_subagent_with_mock_pool(sample_product):
    """Testa o PlaywrightScraperSubagent isolado usando mock do browser pool."""
    mock_pool = AsyncMock()
    mock_pool.fetch_page_content.return_value = """
    <html>
        <body>
            <div class="ui-search-layout">
                <li class="ui-search-layout__item">
                    <h2 class="poly-component__title">Huawei FreeBuds Pro 5 Fone Bluetooth</h2>
                    <span class="andes-money-amount__fraction">789</span>
                    <span class="andes-money-amount__cents">50</span>
                    <a href="https://produto.mercadolivre.com.br/item-123">Comprar</a>
                </li>
            </div>
        </body>
    </html>
    """

    adapter = PlaywrightScraperSubagent(pool=mock_pool)
    source = Source(
        product_id=sample_product.id,
        marketplace="mercadolivre",
        url_produto="https://lista.mercadolivre.com.br/huawei",
        metodo_coleta="browser",
    )

    result = await adapter.run(source, sample_product)

    assert result.success is True
    assert result.preco == 789.50
    assert "FreeBuds Pro 5" in result.titulo
    mock_pool.fetch_page_content.assert_awaited_once()


@pytest.mark.asyncio
async def test_playwright_scraper_subagent_handles_timeout(sample_product):
    """Testa se o adapter Playwright trata exceções de timeout sem derrubar a execução."""
    mock_pool = AsyncMock()
    mock_pool.fetch_page_content.side_effect = TimeoutError("Navegador atingiu o timeout de 30s")

    adapter = PlaywrightScraperSubagent(pool=mock_pool)
    source = Source(
        product_id=sample_product.id,
        marketplace="mercadolivre",
        url_produto="https://lista.mercadolivre.com.br/huawei",
        metodo_coleta="browser",
    )

    result = await adapter.run(source, sample_product)

    assert result.success is False
    assert "timeout" in result.error_message.lower()
