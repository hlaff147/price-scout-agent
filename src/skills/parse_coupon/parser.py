"""Skill for parsing and normalizing coupon texts and promotional codes."""

import re

from src.data.models import Coupon
from src.skills.base import BaseSkill


class ParseCouponSkill(BaseSkill):
    """Extrai códigos promocionais e percentuais/valores de desconto de strings de cupom."""

    name = "parse_coupon"
    description = "Parser de texto de cupom para extrair código, desconto percentual e fixo."

    def execute(
        self,
        raw_text: str,
        marketplace: str,
        product_id: str | None = None,
    ) -> Coupon | None:
        return self.parse(raw_text, marketplace, product_id)

    @classmethod
    def parse(
        cls,
        raw_text: str,
        marketplace: str,
        product_id: str | None = None,
    ) -> Coupon | None:
        if not raw_text or not raw_text.strip():
            return None

        clean = raw_text.strip()
        mkt = marketplace.lower()

        # 1. Extração de desconto percentual (ex: "10% OFF", "15% de desconto", "5%")
        percent_match = re.search(r"(\d+(?:[.,]\d+)?)\s*%\s*(?:off|de desconto)?", clean, re.IGNORECASE)
        desconto_percentual = None
        if percent_match:
            try:
                desconto_percentual = float(percent_match.group(1).replace(",", "."))
            except ValueError:
                pass

        # 2. Extração de desconto fixo em R$ (ex: "R$ 50 OFF", "R$ 100 de desconto")
        fixed_match = re.search(r"r\$\s*(\d+(?:[.,]\d+)?)\s*(?:off|de desconto)?", clean, re.IGNORECASE)
        desconto_fixo = None
        if fixed_match:
            try:
                desconto_fixo = float(fixed_match.group(1).replace(".", "").replace(",", "."))
            except ValueError:
                pass

        # 3. Extração do código do cupom
        # Procura por palavras-chave indicativas: cupom, cupom:, use cupom, código, code
        code_match = re.search(
            r"(?:cupom|código|code|use\s+o\s+cupom|cupom\s+de\s+desconto)\s*[:=]?\s*([A-Za-z0-9_\-]+)",
            clean,
            re.IGNORECASE,
        )

        if code_match:
            codigo = code_match.group(1).upper()
        else:
            # Se for uma única palavra alfanumérica em maiúsculas (ex: "MELI15", "BLACKFRIDAY")
            single_word = clean.replace(" ", "")
            if re.fullmatch(r"[A-Za-z0-9_\-]{4,20}", single_word) and not percent_match and not fixed_match:
                codigo = single_word.upper()
            elif desconto_percentual:
                codigo = f"{mkt.upper()}-{int(desconto_percentual)}OFF"
            elif desconto_fixo:
                codigo = f"{mkt.upper()}-{int(desconto_fixo)}OFF"
            else:
                # Gera código derivado seguro
                slug = re.sub(r"[^A-Za-z0-9]", "", clean)[:12].upper()
                codigo = slug or f"{mkt.upper()}-PROMO"

        return Coupon(
            marketplace=mkt,
            product_id=product_id,
            codigo=codigo,
            descricao=clean,
            desconto_percentual=desconto_percentual,
            desconto_fixo=desconto_fixo,
        )
