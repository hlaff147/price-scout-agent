"""KaBuM! parsing skill."""

import json

from bs4 import BeautifulSoup

from src.data.models import ScrapedData
from src.skills.base import BaseSkill
from src.skills.normalize_product.normalizer import NormalizeProductSkill


class ParseKabumSkill(BaseSkill):
    """Skill especializada em extrair informações de ofertas do KaBuM!."""

    name = "parse_kabum"
    description = "Parser HTML para KaBuM! (produtos e listagens de busca)."

    def execute(
        self,
        html: str,
        url: str,
        keywords: list[str] | None = None,
    ) -> ScrapedData:
        soup = BeautifulSoup(html, "html.parser")

        # 1. Tentar extrair de dados estruturados JSON-LD primeiro (mais estável)
        json_ld_data = self._parse_json_ld(soup, url)
        if json_ld_data and json_ld_data.preco:
            return json_ld_data

        # 2. Tentar página de produto individual via seletores
        product_data = self._parse_product_page(soup, url)
        if product_data and product_data.preco:
            return product_data

        # 3. Listagem de busca
        search_data = self._parse_search_listing(soup, url, keywords or [])
        if search_data and search_data.preco:
            return search_data

        return ScrapedData(
            marketplace="kabum",
            success=False,
            url=url,
            error_message="Nenhum produto ou preço correspondente encontrado no KaBuM!.",
        )

    def _parse_json_ld(self, soup: BeautifulSoup, url: str) -> ScrapedData | None:
        scripts = soup.find_all("script", type="application/ld+json")
        for s in scripts:
            try:
                data = json.loads(s.string)
                if isinstance(data, dict) and data.get("@type") == "Product":
                    title = data.get("name")
                    offers = data.get("offers", {})
                    price = float(offers.get("price")) if "price" in offers else None
                    available = "InStock" in offers.get("availability", "")
                    if title and price:
                        return ScrapedData(
                            marketplace="kabum",
                            success=True,
                            titulo=title,
                            preco=price,
                            preco_original=None,
                            moeda="BRL",
                            disponivel=available,
                            cupom=None,
                            url=url,
                        )
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
        return None

    def _parse_product_page(self, soup: BeautifulSoup, url: str) -> ScrapedData | None:
        title_tag = soup.select_one("h1")
        if not title_tag:
            return None

        title = title_tag.get_text(strip=True)

        price_tag = soup.select_one("h4.finalPrice, .finalPrice, span.priceCard")
        if not price_tag:
            return None

        price = NormalizeProductSkill.parse_price_string(price_tag.get_text(strip=True))
        if not price:
            return None

        orig_tag = soup.select_one("span.oldPrice, .oldPrice")
        price_orig = None
        if orig_tag:
            price_orig = NormalizeProductSkill.parse_price_string(orig_tag.get_text(strip=True))

        out_of_stock = soup.find(
            string=lambda t: t and ("indisponível" in t.lower() or "esgotado" in t.lower())
        )
        available = out_of_stock is None

        return ScrapedData(
            marketplace="kabum",
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
        cards = soup.select("article.productCard, div.productCard")
        if not cards:
            return None

        candidates = []
        for card in cards:
            title_tag = card.select_one("span.nameCard, h2")
            if not title_tag:
                continue

            title = title_tag.get_text(strip=True)
            if keywords and not NormalizeProductSkill.matches_keywords(title, keywords):
                continue

            link_tag = card.select_one("a")
            item_url = f"https://www.kabum.com.br{link_tag.get('href')}" if link_tag and link_tag.get("href", "").startswith("/") else (link_tag.get("href") if link_tag else url)

            price_tag = card.select_one("span.priceCard, .finalPrice")
            if not price_tag:
                continue

            price = NormalizeProductSkill.parse_price_string(price_tag.get_text(strip=True))
            if not price:
                continue

            orig_tag = card.select_one("span.oldPriceCard, .oldPrice")
            price_orig = None
            if orig_tag:
                price_orig = NormalizeProductSkill.parse_price_string(orig_tag.get_text(strip=True))

            candidates.append(
                ScrapedData(
                    marketplace="kabum",
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
