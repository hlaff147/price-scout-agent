"""Skill for parsing and normalizing coupon texts and promotional codes with strict context validation."""

from __future__ import annotations

import re

from src.core.domain import parse_brl_money
from src.core.models import Coupon
from src.skills.base import BaseSkill

INSTALLMENT_RE = re.compile(r"\b\d{1,2}\s*x\s*(?:de\s*)?r\$", re.IGNORECASE)
EXPLICIT_COUPON_WORD_RE = re.compile(
    r"\b(?:cupom|cupons|voucher|código|codigo|code|off|desconto)\b",
    re.IGNORECASE,
)
PERCENT_DISCOUNT_RE = re.compile(
    r"(\d{1,2}(?:[.,]\d+)?)\s*%\s*(?:off|de\s+desconto|no\s+cupom|com\s+cupom|à\s+vista|a\s+vista)?",
    re.IGNORECASE,
)
# Exige marcador semântico explícito de desconto antes ou depois do valor em R$,
# excluindo pisos mínimos ("acima de R$ 500") e parcelas ("10x de R$ 18,99").
FIXED_AFTER_RE = re.compile(
    r"(?<!acima\s)(?<!acima\sde\s)(?<!partir\sde\s)(?<!compras\sde\s)(?<!x\s)(?<!x\sde\s)"
    r"r\$\s*(\d+(?:[.,]\d+)*)\s*(?:de\s+)?(?:off|desconto|no\s+cupom|com\s+cupom)\b",
    re.IGNORECASE,
)
FIXED_BEFORE_RE = re.compile(
    r"\b(?:cupom|desconto|economize|abatimento)\s+(?:de\s+)?r\$\s*(\d+(?:[.,]\d+)*)",
    re.IGNORECASE,
)
MIN_SPEND_RE = re.compile(
    r"(?:acima|a\s+partir|mínimo|minimo|compras\s+acima)\s+(?:de\s+)?r\$\s*(\d+(?:[.,]\d+)*)",
    re.IGNORECASE,
)
CODE_EXTRACT_RE = re.compile(
    r"(?:use\s+o\s+cupom|cupom\s+de\s+desconto|cupom|código|codigo|code)\s*[:=]?\s*"
    r"(?!de\b|off\b|r\$)([A-Za-z0-9_\-]{3,24})",
    re.IGNORECASE,
)


class ParseCouponSkill(BaseSkill):
    """Extrai códigos promocionais e valores de desconto reais, rejeitando parcelas e textos genéricos."""

    name = "parse_coupon"
    description = "Parser estrito de texto de cupom para extrair código, desconto percentual e fixo."

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
        mkt = marketplace.lower().strip()

        # Rejeita textos puramente de parcelamento (ex.: "Em até 10x de R$ 18,99 sem juros")
        if INSTALLMENT_RE.search(clean) and not re.search(
            r"\b(?:cupom|voucher|código|codigo|code|off)\b", clean, re.IGNORECASE
        ):
            return None

        # 1. Extração de desconto percentual
        desconto_percentual: float | None = None
        percent_match = PERCENT_DISCOUNT_RE.search(clean)
        if percent_match:
            try:
                pct = float(percent_match.group(1).replace(",", "."))
                if 0 < pct <= 90:
                    desconto_percentual = pct
            except ValueError:
                desconto_percentual = None

        # 2. Extração estrita de desconto fixo em R$
        desconto_fixo: float | None = None
        fixed_match = FIXED_AFTER_RE.search(clean) or FIXED_BEFORE_RE.search(clean)
        if fixed_match:
            desconto_fixo = parse_brl_money(fixed_match.group(1))

        # 3. Extração opcional de piso mínimo ("acima de R$ 500")
        preco_minimo: float | None = None
        min_match = MIN_SPEND_RE.search(clean)
        if min_match:
            preco_minimo = parse_brl_money(min_match.group(1))

        # 4. Extração do código promocional
        code_match = CODE_EXTRACT_RE.search(clean)
        codigo: str | None = None
        if code_match:
            codigo = code_match.group(1).upper()
        else:
            single_word = clean.replace(" ", "")
            if (
                re.fullmatch(r"[A-Za-z0-9_\-]{4,20}", single_word)
                and not percent_match
                and not fixed_match
            ):
                codigo = single_word.upper()
            elif desconto_percentual is not None:
                codigo = f"{mkt.upper()}-{int(desconto_percentual)}OFF"
            elif desconto_fixo is not None:
                codigo = f"{mkt.upper()}-{int(desconto_fixo)}OFF"
            elif EXPLICIT_COUPON_WORD_RE.search(clean):
                slug = re.sub(r"[^A-Za-z0-9]", "", clean)[:12].upper()
                codigo = slug or f"{mkt.upper()}-PROMO"

        if not codigo:
            return None

        return Coupon(
            marketplace=mkt,
            product_id=product_id,
            codigo=codigo,
            descricao=clean,
            desconto_percentual=desconto_percentual,
            desconto_fixo=desconto_fixo,
            preco_minimo=preco_minimo,
        )
