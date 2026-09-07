"""Shopee Brasil parsing skill."""


from bs4 import BeautifulSoup

from src.data.models import ScrapedData
from src.skills.base import BaseSkill
from src.skills.normalize_product.normalizer import NormalizeProductSkill


class ParseShopeeSkill(BaseSkill):
    """Skill especializada em extrair informações de ofertas da Shopee Brasil."""

    name = "parse_shopee"
    description = "Parser HTML para Shopee Brasil (produtos e listagens de busca)."

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

        if soup.select_one("div#main, div.shopee-search-page-root") and not soup.select("div[data-sqe='item']"):
            return ScrapedData(
                marketplace="shopee",
                success=False,
                url=url,
                error_message="Limitação SPA: a Shopee requer renderização JavaScript para exibir produtos.",
            )

        return ScrapedData(
            marketplace="shopee",
            success=False,
            url=url,
            error_message="Nenhum produto ou preço correspondente encontrado na Shopee.",
        )

    def _parse_product_page(self, soup: BeautifulSoup, url: str) -> ScrapedData | None:
        title_tag = soup.select_one("h1, div.vR6vdF, div._44qnta")
        if not title_tag:
            return None

        title = title_tag.get_text(strip=True)

        price_tag = soup.select_one(
            "div.G27ShZ, div.pmmxKx, div[class*='text-shopee-primary'], div.font-medium.text-lg"
        )
        if not price_tag:
            return None

        price = NormalizeProductSkill.parse_price_string(price_tag.get_text(strip=True))
        if not price:
            return None

        orig_tag = soup.select_one("div.line-through, span.line-through, div.Y3_V1b")
        price_orig = None
        if orig_tag:
            price_orig = NormalizeProductSkill.parse_price_string(orig_tag.get_text(strip=True))

        coupon_tag = soup.select_one("span[class*='voucher'], div.mini-vouchers__vouchers")
        coupon = coupon_tag.get_text(strip=True) if coupon_tag else None

        out_of_stock = soup.find(
            string=lambda t: t and ("esgotado" in t.lower() or "indisponível" in t.lower())
        )
        available = out_of_stock is None

        return ScrapedData(
            marketplace="shopee",
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
            "div[data-sqe='item'], li.shopee-search-item-result__item, div.col-xs-2-4"
        )
        if not items:
            return None

        candidates = []
        for item in items:
            title_tag = item.select_one("div[data-sqe='name'], div.line-clamp-2, div.Cve6sh")
            if not title_tag:
                continue

            title = title_tag.get_text(strip=True)
            if keywords and not NormalizeProductSkill.matches_keywords(title, keywords):
                continue

            link_tag = item.select_one("a")
            item_url = (
                f"https://shopee.com.br{link_tag.get('href')}"
                if link_tag and link_tag.get("href", "").startswith("/")
                else (link_tag.get("href") if link_tag else url)
            )

            price_tag = item.select_one(
                "span.truncate, div.truncate, span.vioxXd, div[class*='text-shopee-primary']"
            )
            if not price_tag:
                continue

            price = NormalizeProductSkill.parse_price_string(price_tag.get_text(strip=True))
            if not price:
                continue

            orig_tag = item.select_one("div.line-through, span.line-through")
            price_orig = None
            if orig_tag:
                price_orig = NormalizeProductSkill.parse_price_string(orig_tag.get_text(strip=True))

            candidates.append(
                ScrapedData(
                    marketplace="shopee",
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
