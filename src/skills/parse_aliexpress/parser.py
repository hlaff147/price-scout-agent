"""AliExpress parsing skill."""

from __future__ import annotations

from typing import ClassVar

from bs4 import BeautifulSoup

from src.core.models import ScrapedData
from src.skills.base import BaseSkill
from src.skills.normalize_product.normalizer import NormalizeProductSkill


class ParseAliExpressSkill(BaseSkill):
    """Skill especializada em extrair informações de ofertas do AliExpress."""

    name = "parse_aliexpress"
    description = "Parser HTML para AliExpress (produtos e listagens de busca em BRL)."

    SELECTORS: ClassVar[dict[str, str]] = {
        "container": "div.search-item-card, div[class*='multi--container--']",
        "titulo": "h1[data-pl='product-title'], div[class*='multi--title--'], h3",
        "preco": "span.product-price-value, div[class*='multi--price-sale--']",
    }

    SEARCH_ITEM_SELECTOR = "div.search-item-card, div[class*='multi--container--'], div.list--gallery--item"

    def execute(
        self,
        html: str,
        url: str,
        keywords: list[str] | None = None,
    ) -> ScrapedData:
        soup = BeautifulSoup(html, "html.parser")
        kw_list = keywords or []

        if soup.select_one(self.SEARCH_ITEM_SELECTOR):
            search_data = self._parse_search_listing(soup, url, kw_list)
            if search_data and search_data.preco:
                return search_data
        else:
            product_data = self._parse_product_page(soup, url, kw_list)
            if product_data and product_data.preco:
                return product_data
            search_data = self._parse_search_listing(soup, url, kw_list)
            if search_data and search_data.preco:
                return search_data

        return ScrapedData(
            marketplace="aliexpress",
            success=False,
            url=url,
            error_message="Nenhum produto ou preço correspondente encontrado no AliExpress.",
        )

    def _parse_product_page(
        self, soup: BeautifulSoup, url: str, keywords: list[str]
    ) -> ScrapedData | None:
        title_tag = soup.select_one("h1[data-pl='product-title'], h1.product-title-text, h1")
        if not title_tag:
            return None

        title = title_tag.get_text(strip=True)
        if keywords and not NormalizeProductSkill.matches_keywords(title, keywords):
            return None

        price_tag = soup.select_one(
            "span.product-price-value, div.product-price-current, span.notranslate"
        )
        if not price_tag:
            return None

        price = NormalizeProductSkill.parse_price_string(price_tag.get_text(strip=True))
        if not price:
            return None

        orig_tag = soup.select_one(
            "span.product-price-del, div.product-price-original, span.price-original"
        )
        price_orig = None
        if orig_tag:
            price_orig = NormalizeProductSkill.parse_price_string(orig_tag.get_text(strip=True))

        out_of_stock = soup.find(
            string=lambda t: t and ("desculpe, este item não está mais disponível" in t.lower())
        )
        available = out_of_stock is None

        return ScrapedData(
            marketplace="aliexpress",
            success=True,
            titulo=title,
            preco=price,
            preco_original=price_orig,
            moeda="BRL",
            disponivel=available,
            cupom=None,
            url=url,
        )

    def _parse_search_listing(
        self,
        soup: BeautifulSoup,
        url: str,
        keywords: list[str],
    ) -> ScrapedData | None:
        items = soup.select(self.SEARCH_ITEM_SELECTOR)
        if not items:
            return None

        candidates: list[ScrapedData] = []
        for item in items:
            title_tag = item.select_one(
                "h3, div[class*='multi--title--'], a[class*='multi--title--']"
            )
            if not title_tag:
                continue

            title = title_tag.get_text(strip=True)
            if keywords and not NormalizeProductSkill.matches_keywords(title, keywords):
                continue

            link_tag = item.select_one("a")
            raw_href = str(link_tag.get("href", "")) if link_tag else ""
            item_url = (
                f"https:{raw_href}"
                if raw_href.startswith("//")
                else (raw_href or url)
            )

            price_tag = item.select_one(
                "div[class*='multi--price-sale--'], span[class*='price-value']"
            )
            if not price_tag:
                continue

            price = NormalizeProductSkill.parse_price_string(price_tag.get_text(strip=True))
            if not price:
                continue

            orig_tag = item.select_one(
                "div[class*='multi--price-original--'], span[class*='price-original']"
            )
            price_orig = None
            if orig_tag:
                price_orig = NormalizeProductSkill.parse_price_string(orig_tag.get_text(strip=True))

            candidates.append(
                ScrapedData(
                    marketplace="aliexpress",
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

        candidates.sort(key=lambda x: x.preco or float("inf"))
        return candidates[0]
