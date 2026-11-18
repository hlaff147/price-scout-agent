"""Product and price normalization skill backed by canonical core domain primitives."""

from __future__ import annotations

from src.core.domain import (
    REFURBISHED_TERMS as CORE_REFURBISHED_TERMS,
)
from src.core.domain import (
    STORAGE_EXPLICIT_RE,
    STORAGE_TOKEN_RE,
    is_accessory_or_part_listing,
    parse_brl_money,
)
from src.core.domain import (
    match_view as core_match_view,
)
from src.core.domain import (
    normalize_text as core_normalize_text,
)
from src.skills.base import BaseSkill


class NormalizeProductSkill(BaseSkill):
    """Normaliza strings de preços, títulos e validações de produto."""

    name = "normalize_product"
    description = "Normaliza textos, preços e variantes de produtos."

    STORAGE_PATTERN = STORAGE_EXPLICIT_RE
    STORAGE_TOKEN = STORAGE_TOKEN_RE
    REFURBISHED_TERMS = CORE_REFURBISHED_TERMS

    def execute(self, text: str) -> str:
        return self.normalize_text(text)

    @staticmethod
    def normalize_text(text: str) -> str:
        """Remove acentos, converte para minúsculas e remove espaços redundantes."""
        return core_normalize_text(text)

    @staticmethod
    def parse_price_string(raw: str | None) -> float | None:
        """Converte strings monetárias variadas (BRL/US, com ou sem centavos) para float positivo."""
        return parse_brl_money(raw)

    @classmethod
    def match_view(cls, text: str) -> str:
        """Visão normalizada para matching: 'S25+' -> 's25 plus' e '512 GB' -> '512gb'."""
        return core_match_view(text)

    @classmethod
    def matches_keywords(cls, title: str, keywords: list[str]) -> bool:
        """Verifica se o título normalizado contém todas as palavras essenciais de ao menos uma keyword.

        Tokens de keyword prefixados com '-' funcionam como exclusão
        (ex.: 'POCO X8 Pro 512GB -max' não casa com 'POCO X8 Pro Max 512GB').
        """
        if not title or not keywords:
            return False

        norm_title = cls.normalize_text(title)
        title_tokens = set(norm_title.split()) | set(cls.match_view(title).split())

        all_negatives = [
            p[1:] for kw in keywords for p in kw.split() if p.startswith("-") and len(p) > 1
        ]
        for neg in all_negatives:
            neg_tokens = cls.match_view(neg).split()
            if neg_tokens and all(t in title_tokens for t in neg_tokens):
                return False

        for kw in keywords:
            raw_parts = kw.split()
            positive_raw = " ".join(
                p for p in raw_parts if not (p.startswith("-") and len(p) > 1)
            )
            kw_tokens = cls.match_view(positive_raw).split()
            if not kw_tokens:
                continue
            if not all(token in title_tokens for token in kw_tokens):
                continue
            if any(t in title_tokens and t not in kw_tokens for t in cls.REFURBISHED_TERMS):
                continue
            device_title = any(cls.STORAGE_TOKEN.match(t) for t in kw_tokens)
            if cls._is_accessory_false_positive(
                norm_title, kw_tokens, device_title=device_title, raw_keywords=keywords
            ):
                continue
            return True

        return False

    @staticmethod
    def _is_accessory_false_positive(
        norm_title: str,
        kw_tokens: list[str],
        device_title: bool = False,
        raw_keywords: list[str] | None = None,
    ) -> bool:
        """Delega para a regra canônica unificada de detecção de acessórios/peças."""
        is_acc, _ = is_accessory_or_part_listing(
            candidate_title=norm_title,
            target_name=" ".join(kw_tokens),
            target_keywords=raw_keywords or [" ".join(kw_tokens)],
            has_anchored_storage=device_title,
        )
        return is_acc
