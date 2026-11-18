"""KaBuM! parsing skill."""

from __future__ import annotations

import json
from typing import ClassVar

from bs4 import BeautifulSoup

from src.core.models import ScrapedData
from src.skills.base import BaseSkill
from src.skills.normalize_product.normalizer import NormalizeProductSkill


class ParseKabumSkill(BaseSkill):
    """Skill especializada em extrair informações de ofertas do KaBuM!."""

    name = "parse_kabum"
    description = "Parser HTML para KaBuM! (produtos e listagens de busca)."

    SELECTORS: ClassVar[dict[str, str]] = {
        "container": "article.productCard, div.productCard",
        "titulo": "span.nameCard, h1",
        "preco": "span.priceCard, h4.finalPrice, .finalPrice",
    }

    def execute(
        self,
        html: str,
        url: str,
        keywords: list[str] | None = None,
    ) -> ScrapedData:
        soup = BeautifulSoup(html, "html.parser")
        kw_list = keywords or []

        json_ld_data = self._parse_json_ld(soup, url, kw_list)
        if json_ld_data and json_ld_data.preco:
            return json_ld_data

        next_data = self._parse_next_data(soup, url, kw_list)
        if next_data and next_data.preco:
            return next_data

        # Se existirem cards de listagem de busca, avalia a listagem ANTES de h1 genérico
        if soup.select_one("article.productCard, div.productCard"):
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
            marketplace="kabum",
            success=False,
            url=url,
            error_message="Nenhum produto ou preço correspondente encontrado no KaBuM!.",
        )

    def _parse_next_data(
        self,
        soup: BeautifulSoup,
        url: str,
        keywords: list[str],
    ) -> ScrapedData | None:
        script_tag = soup.find("script", id="__NEXT_DATA__")
        if not script_tag or not script_tag.string:
            return None

        try:
            payload = json.loads(script_tag.string)
            page_props = payload.get("props", {}).get("pageProps", {})
            raw_data = page_props.get("data")
            if isinstance(raw_data, str):
                raw_data = json.loads(raw_data)
            if not isinstance(raw_data, dict):
                raw_data = page_props
        except (json.JSONDecodeError, TypeError, ValueError):
            return None

        catalog_items = (
            raw_data.get("catalogServer", {}).get("data")
            if isinstance(raw_data.get("catalogServer"), dict)
            else None
        )
        if isinstance(catalog_items, list) and catalog_items:
            candidates: list[ScrapedData] = []
            for item in catalog_items:
                if not isinstance(item, dict) or item.get("available") is False:
                    continue
                title = str(item.get("name") or "")
                if not title:
                    continue
                if keywords and not NormalizeProductSkill.matches_keywords(title, keywords):
                    continue

                raw_price = item.get("priceWithDiscount") or item.get("price")
                price = NormalizeProductSkill.parse_price_string(str(raw_price)) if raw_price else None
                if not price or price <= 0:
                    continue

                raw_old = item.get("oldPrice")
                price_orig_val = NormalizeProductSkill.parse_price_string(str(raw_old)) if raw_old else None
                price_orig = price_orig_val if price_orig_val and price_orig_val > price else None

                code = item.get("code")
                slug = item.get("friendlyName") or ""
                item_url = (
                    f"https://www.kabum.com.br/produto/{code}/{slug}".rstrip("/")
                    if code
                    else url
                )
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
            if candidates:
                candidates.sort(key=lambda x: x.preco or float("inf"))
                return candidates[0]

        prod_obj = raw_data.get("product") if isinstance(raw_data.get("product"), dict) else raw_data
        if isinstance(prod_obj, dict) and prod_obj.get("name"):
            title = str(prod_obj["name"])
            if keywords and not NormalizeProductSkill.matches_keywords(title, keywords):
                return None
            prices_obj = prod_obj.get("prices") if isinstance(prod_obj.get("prices"), dict) else prod_obj
            raw_price = prices_obj.get("priceWithDiscount") or prices_obj.get("price")
            price = NormalizeProductSkill.parse_price_string(str(raw_price)) if raw_price else None
            if price and price > 0:
                raw_old = prices_obj.get("oldPrice")
                old_val = NormalizeProductSkill.parse_price_string(str(raw_old)) if raw_old else None
                price_orig = old_val if old_val and old_val > price else None
                available = prod_obj.get("available", True) is not False
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

        return None

    def _parse_json_ld(
        self, soup: BeautifulSoup, url: str, keywords: list[str]
    ) -> ScrapedData | None:
        scripts = soup.find_all("script", type="application/ld+json")
        for s in scripts:
            if not s.string:
                continue
            try:
                data = json.loads(s.string)
                if isinstance(data, dict) and data.get("@type") == "Product":
                    title = str(data.get("name") or "")
                    if not title:
                        continue
                    if keywords and not NormalizeProductSkill.matches_keywords(title, keywords):
                        continue
                    offers = data.get("offers", {})
                    price = (
                        NormalizeProductSkill.parse_price_string(str(offers.get("price")))
                        if "price" in offers
                        else None
                    )
                    available = "InStock" in str(offers.get("availability", ""))
                    if price:
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

    def _parse_product_page(
        self, soup: BeautifulSoup, url: str, keywords: list[str]
    ) -> ScrapedData | None:
        title_tag = soup.select_one("h1")
        if not title_tag:
            return None

        title = title_tag.get_text(strip=True)
        if keywords and not NormalizeProductSkill.matches_keywords(title, keywords):
            return None

        price_tag = soup.select_one("h4.finalPrice, .finalPrice")
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

        candidates: list[ScrapedData] = []
        for card in cards:
            title_tag = card.select_one("span.nameCard, h2")
            if not title_tag:
                continue

            title = title_tag.get_text(strip=True)
            if keywords and not NormalizeProductSkill.matches_keywords(title, keywords):
                continue

            link_tag = card.select_one("a")
            raw_href = str(link_tag.get("href", "")) if link_tag else ""
            item_url = (
                f"https://www.kabum.com.br{raw_href}"
                if raw_href.startswith("/")
                else (raw_href or url)
            )

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
