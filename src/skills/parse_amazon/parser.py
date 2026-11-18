"""Amazon Brasil parsing skill."""

from __future__ import annotations

from typing import ClassVar

from bs4 import BeautifulSoup
from loguru import logger

from src.core.models import ScrapedData
from src.skills.base import BaseSkill
from src.skills.normalize_product.normalizer import NormalizeProductSkill


class ParseAmazonSkill(BaseSkill):
    """Skill especializada em extrair informações de ofertas da Amazon Brasil."""

    name = "parse_amazon"
    description = "Parser HTML para Amazon Brasil (produtos e listagens de busca)."

    SELECTORS: ClassVar[dict[str, str]] = {
        "container": "div[data-component-type='s-search-result']",
        "titulo": "h2 a span, span#productTitle",
        "preco": "span.a-price:not(.a-text-price) span.a-offscreen",
    }

    def execute(
        self,
        html: str,
        url: str,
        keywords: list[str] | None = None,
    ) -> ScrapedData:
        if (
            "captchacharacters" in html
            or "robot_check" in html
            or "api-services-support@amazon.com" in html
        ):
            logger.warning("[AMAZON] Desafio anti-bot/captcha temporário detectado.")
            return ScrapedData(
                marketplace="amazon",
                success=False,
                url=url,
                error_message="Desafio anti-bot/captcha temporário da Amazon.",
            )

        soup = BeautifulSoup(html, "html.parser")
        kw_list = keywords or []

        if soup.select_one("div[data-component-type='s-search-result']") and not soup.select_one(
            "span#productTitle, h1#title"
        ):
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
            marketplace="amazon",
            success=False,
            url=url,
            error_message="Nenhum produto ou preço correspondente encontrado na Amazon.",
        )

    def _parse_product_page(
        self, soup: BeautifulSoup, url: str, keywords: list[str]
    ) -> ScrapedData | None:
        title_tag = soup.select_one("span#productTitle, h1#title")
        if not title_tag:
            return None

        title = title_tag.get_text(strip=True)
        if keywords and not NormalizeProductSkill.matches_keywords(title, keywords):
            return None

        price = None
        price_tag = soup.select_one(
            "span.apexPriceToPay span.a-offscreen, "
            "span#priceblock_ourprice, "
            "span#priceblock_dealprice, "
            "div#corePrice_feature_div span.a-price:not(.a-text-price) span.a-offscreen, "
            "span.a-price:not(.a-text-price) span.a-offscreen"
        )
        if price_tag:
            price = NormalizeProductSkill.parse_price_string(price_tag.get_text(strip=True))

        price_orig = None
        orig_tag = soup.select_one(
            "span.basisPrice span.a-offscreen, "
            "span.a-text-price span.a-offscreen, "
            "span#priceblock_saleprice"
        )
        if orig_tag:
            price_orig = NormalizeProductSkill.parse_price_string(orig_tag.get_text(strip=True))

        coupon = None
        coupon_tag = soup.select_one("span.promoPriceBlockMessage, label[for*='coupon']")
        if coupon_tag:
            coupon = coupon_tag.get_text(strip=True)

        avail_tag = soup.select_one("div#availability span")
        available = True
        if avail_tag:
            text = avail_tag.get_text(strip=True).lower()
            if "não disponível" in text or "indisponível" in text or "esgotado" in text:
                available = False

        return ScrapedData(
            marketplace="amazon",
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
        items = soup.select("div[data-component-type='s-search-result'], div.s-result-item")
        if not items:
            return None

        candidates: list[ScrapedData] = []
        for item in items:
            title_tag = item.select_one("h2 a span, h2 span")
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)

            if keywords and not NormalizeProductSkill.matches_keywords(title, keywords):
                continue

            link_tag = item.select_one("h2 a")
            raw_href = str(link_tag.get("href", "")) if link_tag else ""
            item_url = (
                f"https://www.amazon.com.br{raw_href}"
                if raw_href.startswith("/")
                else (raw_href or url)
            )

            price_tag = item.select_one("span.a-price:not(.a-text-price) span.a-offscreen")
            if not price_tag:
                continue

            price = NormalizeProductSkill.parse_price_string(price_tag.get_text(strip=True))
            if not price:
                continue

            orig_tag = item.select_one("span.a-text-price span.a-offscreen")
            price_orig = None
            if orig_tag:
                price_orig = NormalizeProductSkill.parse_price_string(orig_tag.get_text(strip=True))

            candidates.append(
                ScrapedData(
                    marketplace="amazon",
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
