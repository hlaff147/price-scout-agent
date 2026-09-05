"""AliExpress parsing skill."""


from bs4 import BeautifulSoup

from src.data.models import ScrapedData
from src.skills.base import BaseSkill
from src.skills.normalize_product.normalizer import NormalizeProductSkill


class ParseAliExpressSkill(BaseSkill):
    """Skill especializada em extrair informações de ofertas do AliExpress."""

    name = "parse_aliexpress"
    description = "Parser HTML para AliExpress (produtos e listagens de busca em BRL)."

    def execute(
        self,
        html: str,
        url: str,
        keywords: list[str] | None = None,
    ) -> ScrapedData:
        soup = BeautifulSoup(html, "html.parser")

        # 1. Página de produto individual
        product_data = self._parse_product_page(soup, url)
        if product_data and product_data.preco:
            return product_data

        # 2. Listagem de busca
        search_data = self._parse_search_listing(soup, url, keywords or [])
        if search_data and search_data.preco:
            return search_data

        return ScrapedData(
            marketplace="aliexpress",
            success=False,
            url=url,
            error_message="Nenhum produto ou preço correspondente encontrado no AliExpress.",
        )

    def _parse_product_page(self, soup: BeautifulSoup, url: str) -> ScrapedData | None:
        title_tag = soup.select_one(
            "h1[data-pl='product-title'], h1.product-title-text, h1"
        )
        if not title_tag:
            return None

        title = title_tag.get_text(strip=True)

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
        items = soup.select(
            "div.search-item-card, div[class*='multi--container--'], div.list--gallery--item"
        )
        if not items:
            return None

        candidates = []
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
            item_url = (
                f"https:{link_tag.get('href')}"
                if link_tag and link_tag.get("href", "").startswith("//")
                else (link_tag.get("href") if link_tag else url)
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
