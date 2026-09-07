"""Tests for search listing parsing, accessory filtering, anti-bot challenges, and edge cases."""

from pathlib import Path

import pytest

from src.skills.parse_amazon.parser import ParseAmazonSkill
from src.skills.parse_google_shopping.parser import ParseGoogleShoppingSkill
from src.skills.parse_mercadolivre.parser import ParseMercadoLivreSkill
from src.skills.parse_shopee.parser import ParseShopeeSkill

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestMercadoLivreSearchListing:
    def test_finds_cheapest_matching_product_and_filters_accessories(self):
        html = (FIXTURES_DIR / "mercadolivre_search.html").read_text(encoding="utf-8")
        parser = ParseMercadoLivreSkill()
        result = parser.execute(
            html=html,
            url="https://lista.mercadolivre.com.br/huawei-freebuds-pro-5",
            keywords=["Huawei FreeBuds Pro 5", "FreeBuds Pro 5"],
        )
        assert result.success is True
        assert result.marketplace == "mercadolivre"
        # Deve escolher o item mais barato entre os legítimos (R$ 849.90 vs R$ 899.50)
        # e ignorar o case de silicone (R$ 39.90) e o Xiaomi
        assert result.preco == 849.90
        assert "Huawei FreeBuds Pro 5" in (result.titulo or "")
        assert "Capa" not in (result.titulo or "")
        assert "Xiaomi" not in (result.titulo or "")

    def test_accessories_only_returns_no_results(self):
        html = (FIXTURES_DIR / "mercadolivre_search_accessories_only.html").read_text(encoding="utf-8")
        parser = ParseMercadoLivreSkill()
        result = parser.execute(
            html=html,
            url="https://lista.mercadolivre.com.br/huawei-freebuds-pro-5",
            keywords=["Huawei FreeBuds Pro 5"],
        )
        assert result.success is False
        assert result.preco is None
        assert "Nenhum produto" in (result.error_message or "")

    def test_mercadolivre_account_verification_returns_antibot_error(self):
        html = '<html><head><title>Mercado Libre</title></head><body>Olá! Para continuar, acesse sua conta trace-id: 123</body></html>'
        parser = ParseMercadoLivreSkill()
        result = parser.execute(
            html=html,
            url="https://lista.mercadolivre.com.br/huawei-freebuds-pro-5",
            keywords=["Huawei FreeBuds Pro 5"],
        )
        assert result.success is False
        assert result.preco is None
        assert "anti-bot" in (result.error_message or "").lower()


class TestAmazonSearchListing:
    def test_finds_cheapest_matching_product_and_filters_accessories(self):
        html = (FIXTURES_DIR / "amazon_search.html").read_text(encoding="utf-8")
        parser = ParseAmazonSkill()
        result = parser.execute(
            html=html,
            url="https://www.amazon.com.br/s?k=Huawei+FreeBuds+Pro+5",
            keywords=["Huawei FreeBuds Pro 5", "FreeBuds Pro 5"],
        )
        assert result.success is True
        assert result.marketplace == "amazon"
        # Deve escolher o mais barato entre os válidos (R$ 789.90 vs R$ 829.00)
        # e ignorar a capa (R$ 49.90) e o Galaxy Buds (R$ 699.00)
        assert result.preco == 789.90
        assert "huawei" in (result.titulo or "").lower()
        assert "Capa" not in (result.titulo or "")
        assert "Galaxy" not in (result.titulo or "")

    def test_amazon_captcha_returns_error_gracefully_without_name_error(self):
        html = (FIXTURES_DIR / "amazon_captcha.html").read_text(encoding="utf-8")
        parser = ParseAmazonSkill()
        result = parser.execute(
            html=html,
            url="https://www.amazon.com.br/s?k=Huawei+FreeBuds+Pro+5",
            keywords=["Huawei FreeBuds Pro 5"],
        )
        assert result.success is False
        assert result.preco is None
        assert "anti-bot/captcha" in (result.error_message or "")


class TestGoogleShoppingSearchListing:
    def test_finds_cheapest_store_and_filters_irrelevant_sponsored(self):
        html = (FIXTURES_DIR / "google_shopping_search.html").read_text(encoding="utf-8")
        parser = ParseGoogleShoppingSkill()
        result = parser.execute(
            html=html,
            url="https://www.google.com/search?q=huawei+Freebuds+Pro+5&udm=28",
            keywords=["Huawei FreeBuds Pro 5", "FreeBuds Pro 5"],
        )
        assert result.success is True
        assert result.marketplace == "google_shopping"
        # Deve escolher Amazon (R$ 749.00) e não Magalu (R$ 819.00) nem Galaxy Buds (R$ 399.00)
        assert result.preco == 749.00
        assert result.preco_original == 950.00
        assert "[Amazon.com.br]" in (result.titulo or "")
        assert "Galaxy Buds" not in (result.titulo or "")

    def test_google_sorry_challenge_returns_error(self):
        html = (FIXTURES_DIR / "google_sorry.html").read_text(encoding="utf-8")
        parser = ParseGoogleShoppingSkill()
        result = parser.execute(
            html=html,
            url="https://www.google.com/search?q=huawei+Freebuds+Pro+5&udm=28",
            keywords=["Huawei FreeBuds Pro 5"],
        )
        assert result.success is False
        assert result.preco is None
        assert "anti-bot/captcha" in (result.error_message or "")


class TestShopeeSearchListing:
    def test_empty_spa_shell_returns_no_results(self):
        html = (FIXTURES_DIR / "shopee_search_empty.html").read_text(encoding="utf-8")
        parser = ParseShopeeSkill()
        result = parser.execute(
            html=html,
            url="https://shopee.com.br/search?keyword=Huawei%20FreeBuds%20Pro%205",
            keywords=["Huawei FreeBuds Pro 5"],
        )
        assert result.success is False
        assert result.preco is None
        assert "spa" in (result.error_message or "").lower()


class TestEdgeCases:
    @pytest.mark.parametrize(
        "parser_cls,marketplace",
        [
            (ParseMercadoLivreSkill, "mercadolivre"),
            (ParseAmazonSkill, "amazon"),
            (ParseGoogleShoppingSkill, "google_shopping"),
            (ParseShopeeSkill, "shopee"),
        ],
    )
    def test_empty_html_string_returns_no_result(self, parser_cls, marketplace):
        parser = parser_cls()
        result = parser.execute(
            html="",
            url=f"https://example.com/{marketplace}",
            keywords=["Huawei FreeBuds Pro 5"],
        )
        assert result.success is False
        assert result.preco is None

    @pytest.mark.parametrize(
        "parser_cls,marketplace",
        [
            (ParseMercadoLivreSkill, "mercadolivre"),
            (ParseAmazonSkill, "amazon"),
            (ParseGoogleShoppingSkill, "google_shopping"),
            (ParseShopeeSkill, "shopee"),
        ],
    )
    def test_html_without_matching_elements_returns_no_result(self, parser_cls, marketplace):
        parser = parser_cls()
        html = "<html><head><title>Página Qualquer</title></head><body><div>Sem dados de compra</div></body></html>"
        result = parser.execute(
            html=html,
            url=f"https://example.com/{marketplace}",
            keywords=["Huawei FreeBuds Pro 5"],
        )
        assert result.success is False
        assert result.preco is None
