"""Amazon Brasil parsing skill."""


from bs4 import BeautifulSoup
from loguru import logger

from src.data.models import ScrapedData
from src.skills.base import BaseSkill
from src.skills.normalize_product.normalizer import NormalizeProductSkill


class ParseAmazonSkill(BaseSkill):
    """Skill especializada em extrair informações de ofertas da Amazon Brasil."""

    name = "parse_amazon"
    description = "Parser HTML para Amazon Brasil (produtos e listagens de busca)."

    def execute(
        self,
        html: str,
        url: str,
        keywords: list[str] | None = None,
    ) -> ScrapedData:
        if "captchacharacters" in html or "robot_check" in html or "api-services-support@amazon.com" in html:
            logger.warning("[AMAZON] Desafio anti-bot/captcha temporário detectado.")
            return ScrapedData(
                marketplace="amazon",
                success=False,
                url=url,
                error_message="Desafio anti-bot/captcha temporário da Amazon.",
            )

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
            marketplace="amazon",
            success=False,
            url=url,
            error_message="Nenhum produto ou preço correspondente encontrado na Amazon.",
        )

    def _parse_product_page(self, soup: BeautifulSoup, url: str) -> ScrapedData | None:
        title_tag = soup.select_one("span#productTitle, h1#title")
        if not title_tag:
            return None

        title = title_tag.get_text(strip=True)

        # Preço atual
        price = None
        price_tag = soup.select_one(
            "span.apexPriceToPay span.a-offscreen, "
            "span#priceblock_ourprice, "
            "span#priceblock_dealprice, "
            "div#corePrice_feature_div span.a-price span.a-offscreen, "
            "span.a-price span.a-offscreen"
        )
        if price_tag:
            price = NormalizeProductSkill.parse_price_string(price_tag.get_text(strip=True))

        # Preço original (De:)
        price_orig = None
        orig_tag = soup.select_one(
            "span.basisPrice span.a-offscreen, "
            "span.a-text-price span.a-offscreen, "
            "span#priceblock_saleprice"
        )
        if orig_tag:
            price_orig = NormalizeProductSkill.parse_price_string(orig_tag.get_text(strip=True))

        # Cupom
        coupon = None
        coupon_tag = soup.select_one("span.promoPriceBlockMessage, label[for*='coupon']")
        if coupon_tag:
            coupon = coupon_tag.get_text(strip=True)

        # Disponibilidade
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

        candidates = []
        for item in items:
            title_tag = item.select_one("h2 a span, h2 span")
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)

            if keywords and not NormalizeProductSkill.matches_keywords(title, keywords):
                continue

            link_tag = item.select_one("h2 a")
            item_url = f"https://www.amazon.com.br{link_tag.get('href')}" if link_tag and link_tag.get("href", "").startswith("/") else (link_tag.get("href") if link_tag else url)

            # Preço atual
            price_tag = item.select_one("span.a-price:not(.a-text-price) span.a-offscreen")
            if not price_tag:
                continue

            price = NormalizeProductSkill.parse_price_string(price_tag.get_text(strip=True))
            if not price:
                continue

            # Preço riscado
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
