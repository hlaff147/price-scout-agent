"""Google Shopping and Sponsored Products parsing skill."""

from bs4 import BeautifulSoup
from loguru import logger

from src.data.models import ScrapedData
from src.skills.base import BaseSkill
from src.skills.normalize_product.normalizer import NormalizeProductSkill


class ParseGoogleShoppingSkill(BaseSkill):
    """Skill para extrair e filtrar ofertas do Google Shopping e carrossel Sponsored Products."""

    name = "parse_google_shopping"
    description = "Meta-agregador de ofertas a partir de Sponsored Products e Google Shopping."

    def execute(
        self,
        html: str,
        url: str,
        keywords: list[str] | None = None,
    ) -> ScrapedData:
        if "google.com/sorry" in html or "recaptcha" in html.lower():
            logger.warning("[GOOGLE_SHOPPING] Desafio anti-bot/captcha temporário do Google.")
            return ScrapedData(
                marketplace="google_shopping",
                success=False,
                url=url,
                error_message="Desafio anti-bot/captcha temporário do Google.",
            )

        soup = BeautifulSoup(html, "html.parser")

        # Localizar os cards de produtos (PLA e Shopping Grid)
        cards = soup.select(
            "div[data-flt-ve='pla_unit'], "
            "div.pla-unit, "
            "div.pla-unit-container, "
            "div.sh-dgr__content, "
            "div.sh-dgr__grid-result, "
            "div.sh-np__click-target, "
            "div.pla-hovercard, "
            "div[class*='pla-unit'], "
            "div.KZmu8e, "
            "div.gkQHve, "
            "div.mnr-c"
        )

        candidates: list[ScrapedData] = []

        for card in cards:
            # 1. Título do anúncio
            title_tag = card.select_one(
                "div.pla-unit-title, "
                "span.pla-unit-title, "
                "h3.sh-np__product-title, "
                "h3, "
                "div[role='heading'], "
                "a[aria-label]"
            )
            if not title_tag:
                continue

            title = title_tag.get("aria-label") or title_tag.get_text(strip=True)

            # 2. Filtrar estritamente palavras-chave para descartar produtos sugeridos irrelevantes (ex: Galaxy Buds3)
            if keywords and not NormalizeProductSkill.matches_keywords(title, keywords):
                continue

            # 3. Loja anunciante
            merchant_tag = card.select_one(
                "div.pla-unit-source, "
                "span.E5ocAb, "
                "span.I1HL6b, "
                "span.sh-np__seller-container, "
                "div[class*='merchant-name'], "
                "span.b5zAEc"
            )
            merchant_name = merchant_tag.get_text(strip=True) if merchant_tag else "Loja Online"

            # 4. Preço Atual e Preço Original
            # Se houver preço riscado em <s> ou classe específica:
            orig_tag = card.select_one(
                "span.pla-unit-price s, "
                "span.kHq4Pe s, "
                "s, "
                "span[class*='original-price']"
            )
            price_orig = None
            if orig_tag:
                price_orig = NormalizeProductSkill.parse_price_string(orig_tag.get_text(strip=True))

            price_tag = card.select_one(
                "span.pla-unit-price, "
                "span.a8Pemb, "
                "span.T149du, "
                "span.hn9kf, "
                "div[class*='price']"
            )
            if not price_tag:
                continue

            price_text = price_tag.get_text(strip=True)
            # Se o texto de preço continha o preço original embutido (ex: "R$721.64 R$899"), separar
            if orig_tag and orig_tag.get_text(strip=True) in price_text:
                price_text = price_text.replace(orig_tag.get_text(strip=True), "").strip()

            price = NormalizeProductSkill.parse_price_string(price_text)
            if not price:
                continue

            # 5. Link de redirecionamento para o anúncio da loja
            link_tag = card.select_one("a[href]")
            item_url = url
            if link_tag and link_tag.get("href"):
                raw_href = link_tag.get("href", "")
                if raw_href.startswith("/"):
                    item_url = f"https://www.google.com{raw_href}"
                else:
                    item_url = raw_href

            # Compor título enriquecido com o nome do marketplace
            composed_title = f"[{merchant_name}] {title}"

            candidates.append(
                ScrapedData(
                    marketplace="google_shopping",
                    success=True,
                    titulo=composed_title,
                    preco=price,
                    preco_original=price_orig,
                    moeda="BRL",
                    disponivel=True,
                    cupom=None,
                    url=item_url,
                )
            )

        if not candidates:
            return ScrapedData(
                marketplace="google_shopping",
                success=False,
                url=url,
                error_message="Nenhum produto correspondente identificado no carrossel do Google Shopping.",
            )

        # Ordenar pelo menor preço encontrado entre todas as lojas do carrossel
        candidates.sort(key=lambda x: x.preco or float("inf"))
        return candidates[0]
