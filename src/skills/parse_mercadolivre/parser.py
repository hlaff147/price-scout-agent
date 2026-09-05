"""Mercado Livre parsing skill."""


from bs4 import BeautifulSoup

from src.data.models import ScrapedData
from src.skills.base import BaseSkill
from src.skills.normalize_product.normalizer import NormalizeProductSkill


class ParseMercadoLivreSkill(BaseSkill):
    """Skill especializada em extrair informações de ofertas do Mercado Livre."""

    name = "parse_mercadolivre"
    description = "Parser HTML para Mercado Livre (produtos e listagens de busca)."

    def execute(
        self,
        html: str,
        url: str,
        keywords: list[str] | None = None,
    ) -> ScrapedData:
        soup = BeautifulSoup(html, "html.parser")

        # 1. Tentar detectar se é página de produto individual
        product_data = self._parse_product_page(soup, url)
        if product_data and product_data.preco:
            return product_data

        # 2. Se não for página de produto, parsear lista de busca
        listing_data = self._parse_search_listing(soup, url, keywords or [])
        if listing_data and listing_data.preco:
            return listing_data

        return ScrapedData(
            marketplace="mercadolivre",
            success=False,
            url=url,
            error_message="Nenhum produto ou preço correspondente encontrado no Mercado Livre.",
        )

    def _parse_product_page(self, soup: BeautifulSoup, url: str) -> ScrapedData | None:
        title_tag = soup.select_one("h1.ui-pdp-title, h1.andes-typography")
        if not title_tag:
            return None

        title = title_tag.get_text(strip=True)

        # Preço atual
        price_fraction = soup.select_one(
            ".ui-pdp-price__second-line .andes-money-amount__fraction, "
            ".ui-pdp-price__part--medium .andes-money-amount__fraction, "
            ".andes-money-amount--cents-superscript .andes-money-amount__fraction"
        )
        cents_tag = soup.select_one(
            ".ui-pdp-price__second-line .andes-money-amount__cents, "
            ".ui-pdp-price__part--medium .andes-money-amount__cents"
        )
        cents = cents_tag.get_text(strip=True) if cents_tag else "00"

        price = None
        if price_fraction:
            raw_price = f"{price_fraction.get_text(strip=True)},{cents}"
            price = NormalizeProductSkill.parse_price_string(raw_price)

        # Preço original (riscado)
        orig_fraction = soup.select_one(
            "s.andes-money-amount--previous .andes-money-amount__fraction, "
            ".ui-pdp-price__original-value .andes-money-amount__fraction"
        )
        orig_cents_tag = soup.select_one(
            "s.andes-money-amount--previous .andes-money-amount__cents, "
            ".ui-pdp-price__original-value .andes-money-amount__cents"
        )
        orig_cents = orig_cents_tag.get_text(strip=True) if orig_cents_tag else "00"
        price_orig = None
        if orig_fraction:
            raw_orig = f"{orig_fraction.get_text(strip=True)},{orig_cents}"
            price_orig = NormalizeProductSkill.parse_price_string(raw_orig)

        # Cupom
        coupon_tag = soup.select_one(
            "span.ui-pdp-promotions-pill-label, span.ui-pdp-coupon-label, .ui-pdp-badge"
        )
        coupon = coupon_tag.get_text(strip=True) if coupon_tag else None

        # Disponibilidade
        out_of_stock = soup.find(string=lambda t: t and "estoque esgotado" in t.lower())
        available = out_of_stock is None

        return ScrapedData(
            marketplace="mercadolivre",
            success=True,
            titulo=title,
            preco=price,
            preco_original=price_orig,
            moeda="BRL",
            disponivel=available,
            cupom=coupon,
            url=url,
        )

    def _parse_search_listing(
        self,
        soup: BeautifulSoup,
        url: str,
        keywords: list[str],
    ) -> ScrapedData | None:
        items = soup.select(
            "li.ui-search-layout__item, div.ui-search-result__wrapper, li.poly-card, div.poly-card, div.ui-search-result"
        )
        if not items:
            return None

        candidates = []
        for item in items:
            title_tag = item.select_one(
                "h2.ui-search-item__title, h2.poly-component__title, a.poly-component__title, a.ui-search-link, h2"
            )
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)

            if keywords and not NormalizeProductSkill.matches_keywords(title, keywords):
                continue

            # Link do produto
            link_tag = item.select_one("a.ui-search-link, a.poly-component__title, a")
            item_url = link_tag.get("href") if link_tag else url

            # Preço atual
            fraction_tag = item.select_one(
                ".poly-price__current .andes-money-amount__fraction, "
                ".andes-money-amount:not(.andes-money-amount--previous) .andes-money-amount__fraction, "
                ".ui-search-price__second-line .andes-money-amount__fraction, "
                ".andes-money-amount__fraction"
            )
            cents_tag = item.select_one(
                ".poly-price__current .andes-money-amount__cents, "
                ".andes-money-amount:not(.andes-money-amount--previous) .andes-money-amount__cents, "
                ".ui-search-price__second-line .andes-money-amount__cents, "
                ".andes-money-amount__cents"
            )
            cents = cents_tag.get_text(strip=True) if cents_tag else "00"

            if not fraction_tag:
                continue

            raw_price = f"{fraction_tag.get_text(strip=True)},{cents}"
            price = NormalizeProductSkill.parse_price_string(raw_price)
            if not price:
                continue

            # Preço original (riscado)
            prev_tag = item.select_one("s.andes-money-amount--previous .andes-money-amount__fraction")
            orig_cents = item.select_one("s.andes-money-amount--previous .andes-money-amount__cents")
            orig_c = orig_cents.get_text(strip=True) if orig_cents else "00"
            price_orig = None
            if prev_tag:
                raw_orig = f"{prev_tag.get_text(strip=True)},{orig_c}"
                price_orig = NormalizeProductSkill.parse_price_string(raw_orig)

            candidates.append(
                ScrapedData(
                    marketplace="mercadolivre",
                    success=True,
                    titulo=title,
                    preco=price,
                    preco_original=price_orig,
                    moeda="BRL",
                    disponivel=True,
                    cupom=None,
                    url=item_url,
                )
            )

        if not candidates:
            return None

        # Ordenar pelo menor preço encontrado que respeitou as palavras-chave
        candidates.sort(key=lambda x: x.preco or float("inf"))
        return candidates[0]
