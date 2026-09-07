"""Diagnostic tests using real live HTML captured from active marketplaces.

These tests explain and assert the exact live behavior for each marketplace:
- Amazon: SSR search listing returns real matching product
- Mercado Livre: SSR search listing returns real matching product (when Brotli is properly decoded)
- Shopee: Pure SPA (React/CSR) where raw HTML contains 0 product elements (architectural limitation)
- Google Shopping: Interstitial redirect / anti-bot challenge served to automated HTTP clients
"""

from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from src.skills.parse_amazon.parser import ParseAmazonSkill
from src.skills.parse_google_shopping.parser import ParseGoogleShoppingSkill
from src.skills.parse_mercadolivre.parser import ParseMercadoLivreSkill
from src.skills.parse_shopee.parser import ParseShopeeSkill

LIVE_DIR = Path(__file__).parent / "fixtures" / "live"
KEYWORDS = ["Huawei FreeBuds Pro 5", "FreeBuds Pro 5"]


@pytest.mark.diagnosis
class TestLiveMarketplaceDiagnosis:
    def test_diagnose_amazon_live_html_succeeds(self):
        """Amazon: Coleta em tempo real obtém com sucesso preço e produto correspondente."""
        live_file = LIVE_DIR / "amazon_search_live.html"
        assert live_file.exists(), "HTML real da Amazon não capturado. Execute scripts/capture_live_html.py"

        html = live_file.read_text(encoding="utf-8")
        parser = ParseAmazonSkill()
        result = parser.execute(
            html=html,
            url="https://www.amazon.com.br/s?k=Huawei+FreeBuds+Pro+5",
            keywords=KEYWORDS,
        )

        assert result.success is True, f"Amazon falhou inesperadamente: {result.error_message}"
        assert result.preco is not None and result.preco > 0
        assert "freebuds" in (result.titulo or "").lower()

    def test_diagnose_mercadolivre_live_html_succeeds(self):
        """Mercado Livre: Coleta obtém preço quando a descompressão (gzip/deflate) é tratada corretamente."""
        live_file = LIVE_DIR / "mercadolivre_search_live.html"
        assert live_file.exists(), "HTML real do Mercado Livre não capturado. Execute scripts/capture_live_html.py"

        html = live_file.read_text(encoding="utf-8")
        parser = ParseMercadoLivreSkill()
        result = parser.execute(
            html=html,
            url="https://lista.mercadolivre.com.br/huawei-freebuds-pro-5",
            keywords=KEYWORDS,
        )

        assert result.success is True, f"Mercado Livre falhou: {result.error_message}"
        assert result.preco is not None and result.preco > 0
        assert "freebuds" in (result.titulo or "").lower()

    def test_diagnose_shopee_live_html_demonstrates_spa_limitation(self):
        """Shopee: Diagnóstico confirma que o HTML cru é apenas uma SPA vazia (0 cards de produto)."""
        live_file = LIVE_DIR / "shopee_search_live.html"
        assert live_file.exists(), "HTML real da Shopee não capturado. Execute scripts/capture_live_html.py"

        html = live_file.read_text(encoding="utf-8")
        soup = BeautifulSoup(html, "html.parser")

        # Verifica que o HTML retornado não contém os cards renderizados por JS
        items = soup.select("div[data-sqe='item'], li.shopee-search-item-result__item")
        assert len(items) == 0, "Shopee inesperadamente retornou cards renderizados no SSR"

        # O parser deve retornar 'Sem Resultado' devido à limitação arquitetural de SPA
        parser = ParseShopeeSkill()
        result = parser.execute(
            html=html,
            url="https://shopee.com.br/search?keyword=Huawei%20FreeBuds%20Pro%205",
            keywords=KEYWORDS,
        )
        assert result.success is False
        assert result.preco is None
        assert "spa" in (result.error_message or "").lower()

    def test_diagnose_google_shopping_live_html_demonstrates_bot_challenge(self):
        """Google Shopping: Diagnóstico confirma que o Google serviu página intermediária / desafio de redirecionamento."""
        live_file = LIVE_DIR / "google_shopping_search_live.html"
        assert live_file.exists(), "HTML real do Google Shopping não capturado. Execute scripts/capture_live_html.py"

        html = live_file.read_text(encoding="utf-8")
        soup = BeautifulSoup(html, "html.parser")

        # Verifica se caiu na página intermediária de redirecionamento do Google
        is_redirect_challenge = "redirecionamento não iniciar" in html.lower() or "google.com/sorry" in html
        assert is_redirect_challenge is True

        cards = soup.select("div[data-flt-ve='pla_unit'], div.pla-unit, div.sh-dgr__content")
        # Sem cards válidos de carrossel
        assert len(cards) == 0

        parser = ParseGoogleShoppingSkill()
        result = parser.execute(
            html=html,
            url="https://www.google.com/search?q=huawei+Freebuds+Pro+5&udm=28",
            keywords=KEYWORDS,
        )
        assert result.success is False
        assert result.preco is None
