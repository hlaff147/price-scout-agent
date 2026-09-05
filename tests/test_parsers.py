"""Tests for product normalization and marketplace parsing skills."""

from pathlib import Path

from src.skills.normalize_product.normalizer import NormalizeProductSkill
from src.skills.parse_aliexpress.parser import ParseAliExpressSkill
from src.skills.parse_amazon.parser import ParseAmazonSkill
from src.skills.parse_google_shopping.parser import ParseGoogleShoppingSkill
from src.skills.parse_kabum.parser import ParseKabumSkill
from src.skills.parse_mercadolivre.parser import ParseMercadoLivreSkill
from src.skills.parse_shopee.parser import ParseShopeeSkill

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestNormalizeProductSkill:
    def test_parse_brazilian_currency_formats(self):
        assert NormalizeProductSkill.parse_price_string("R$ 1.299,90") == 1299.90
        assert NormalizeProductSkill.parse_price_string("R$ 850,00") == 850.00
        assert NormalizeProductSkill.parse_price_string("849,99") == 849.99
        assert NormalizeProductSkill.parse_price_string("R$ 799") == 799.00
        assert NormalizeProductSkill.parse_price_string("1,450.50") == 1450.50
        assert NormalizeProductSkill.parse_price_string("") is None
        assert NormalizeProductSkill.parse_price_string(None) is None

    def test_normalize_text(self):
        text = "Fôné de Óuvido — Sem Fio / Bluetooth (Preto)!"
        normalized = NormalizeProductSkill.normalize_text(text)
        assert normalized == "fone de ouvido sem fio bluetooth preto"

    def test_matches_keywords(self):
        title = "Fone de Ouvido Huawei FreeBuds Pro 5 Bluetooth Original"
        keywords = ["Huawei FreeBuds Pro 5", "FreeBuds Pro 5"]
        assert NormalizeProductSkill.matches_keywords(title, keywords) is True

        # Teste falso positivo de acessório (capinha/case)
        accessory_title = "Capa Case de Silicone Para Huawei FreeBuds Pro 5"
        assert NormalizeProductSkill.matches_keywords(accessory_title, keywords) is False

        unrelated_title = "Fone Xiaomi Redmi Buds 5 Pro"
        assert NormalizeProductSkill.matches_keywords(unrelated_title, keywords) is False


class TestMarketplaceParsers:
    def test_parse_mercadolivre(self):
        html = (FIXTURES_DIR / "mercadolivre_product.html").read_text(encoding="utf-8")
        parser = ParseMercadoLivreSkill()
        result = parser.execute(
            html=html,
            url="https://produto.mercadolivre.com.br/MLB-123",
            keywords=["Huawei FreeBuds Pro 5"],
        )
        assert result.success is True
        assert result.marketplace == "mercadolivre"
        assert result.preco == 799.90
        assert result.preco_original == 1299.00
        assert result.disponivel is True
        assert "PROMO100" in (result.cupom or "")

    def test_parse_amazon(self):
        html = (FIXTURES_DIR / "amazon_product.html").read_text(encoding="utf-8")
        parser = ParseAmazonSkill()
        result = parser.execute(
            html=html,
            url="https://www.amazon.com.br/dp/B0123",
            keywords=["Huawei FreeBuds Pro 5"],
        )
        assert result.success is True
        assert result.marketplace == "amazon"
        assert result.preco == 829.00
        assert result.preco_original == 1199.00
        assert result.disponivel is True

    def test_parse_kabum(self):
        html = (FIXTURES_DIR / "kabum_product.html").read_text(encoding="utf-8")
        parser = ParseKabumSkill()
        result = parser.execute(
            html=html,
            url="https://www.kabum.com.br/produto/123",
            keywords=["Huawei FreeBuds Pro 5"],
        )
        assert result.success is True
        assert result.marketplace == "kabum"
        assert result.preco == 849.90
        assert result.disponivel is True

    def test_parse_shopee(self):
        html = (FIXTURES_DIR / "shopee_product.html").read_text(encoding="utf-8")
        parser = ParseShopeeSkill()
        result = parser.execute(
            html=html,
            url="https://shopee.com.br/product/123/456",
            keywords=["Huawei FreeBuds Pro 5"],
        )
        assert result.success is True
        assert result.marketplace == "shopee"
        assert result.preco == 819.00
        assert result.preco_original == 1150.00
        assert result.disponivel is True
        assert "SHOPEE" in (result.cupom or "")

    def test_parse_aliexpress(self):
        html = (FIXTURES_DIR / "aliexpress_product.html").read_text(encoding="utf-8")
        parser = ParseAliExpressSkill()
        result = parser.execute(
            html=html,
            url="https://pt.aliexpress.com/item/123.html",
            keywords=["Huawei FreeBuds Pro 5"],
        )
        assert result.success is True
        assert result.marketplace == "aliexpress"
        assert result.preco == 689.50
        assert result.preco_original == 950.00
        assert result.disponivel is True

    def test_parse_google_shopping(self):
        html = (FIXTURES_DIR / "google_shopping_product.html").read_text(encoding="utf-8")
        parser = ParseGoogleShoppingSkill()
        result = parser.execute(
            html=html,
            url="https://www.google.com/search?q=huawei+Freebuds+Pro+5&udm=28",
            keywords=["Huawei FreeBuds Pro 5", "FreeBuds Pro 5"],
        )
        assert result.success is True
        assert result.marketplace == "google_shopping"
        # O menor preço correspondente entre as lojas é Amazon R$ 721.64
        assert result.preco == 721.64
        assert result.preco_original == 899.00
        assert "[Amazon.com.br]" in (result.titulo or "")
        assert "Samsung" not in (result.titulo or "")
