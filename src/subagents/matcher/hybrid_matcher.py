"""Semantic and heuristic product variant matcher adapter implementing IProductMatcher."""

from __future__ import annotations

import re

from loguru import logger

from src.core.domain import (
    REFURBISHED_TERMS,
    STORAGE_TOKEN_RE,
    extract_canonical_colors,
    extract_storage_capacities_gb,
    is_accessory_or_part_listing,
    match_view,
    target_required_color,
)
from src.core.domain import (
    normalize_text as core_normalize_text,
)
from src.core.models import MatchResult, Product
from src.core.ports.matcher_port import IProductMatcher
from src.skills.normalize_product.normalizer import NormalizeProductSkill


def normalize_text(text: str) -> str:
    """Normaliza texto mantendo hífens internos relevantes."""
    return core_normalize_text(text, keep_hyphen=True)


class HybridProductMatcher(IProductMatcher):
    """Matcher híbrido calibrado que combina invariantes canônicos de variante e overlap de tokens."""

    async def match(
        self,
        target: Product,
        candidate_title: str,
        candidate_url: str = "",
        metadata: dict | None = None,
    ) -> MatchResult:
        """Avalia se `candidate_title` corresponde com precisão e variante compatível a `target`."""
        if not candidate_title or not candidate_title.strip():
            return MatchResult(
                is_match=False,
                confidence=1.0,
                divergence_reason="Título do anúncio vazio",
                method_used="heuristic",
            )

        norm_title = normalize_text(candidate_title)
        norm_target_name = normalize_text(target.nome)
        norm_keywords = [normalize_text(kw) for kw in target.keywords if kw]

        title_words = set(re.findall(r"\b\w+\b", norm_title))
        view_words = set(match_view(candidate_title).split())
        combined_tokens = title_words | view_words

        target_storage_tokens = [
            t
            for kw in [target.nome, *target.keywords]
            for t in match_view(kw).split()
            if STORAGE_TOKEN_RE.match(t)
        ]
        has_anchored_storage = bool(
            target_storage_tokens and any(t in combined_tokens for t in target_storage_tokens)
        )

        # 1. Filtro Canônico Unificado de Acessórios / Peças Secundárias
        is_acc, acc_term = is_accessory_or_part_listing(
            candidate_title=candidate_title,
            target_name=target.nome,
            target_keywords=target.keywords,
            has_anchored_storage=has_anchored_storage,
        )
        if is_acc:
            logger.debug(
                f"[Matcher] Descartado: anúncio '{candidate_title}' parece ser acessório ({acc_term})"
            )
            return MatchResult(
                is_match=False,
                confidence=0.99,
                divergence_reason=f"Anúncio identificado como acessório/peça secundária ('{acc_term}')",
                method_used="heuristic",
            )

        # 1b. Filtro de Produtos Recondicionados / Vitrine / Usados
        target_plain_tokens = set(core_normalize_text(target.nome).split())
        if any(term in title_words and term not in target_plain_tokens for term in REFURBISHED_TERMS):
            logger.debug(
                f"[Matcher] Descartado: anúncio '{candidate_title}' parece ser item usado/vitrine"
            )
            return MatchResult(
                is_match=False,
                confidence=0.99,
                divergence_reason="Anúncio identificado como item usado, vitrine ou recondicionado",
                method_used="heuristic",
            )

        # 2. Edição Global vs Nacional (Premissa de Negócio: NÃO deduplicar)
        is_candidate_global = "global" in title_words or "importado" in title_words
        is_candidate_nacional = (
            "nacional" in title_words or "brasil" in title_words or "anatel" in title_words
        )

        is_target_global = any("global" in kw for kw in norm_keywords) or "global" in norm_target_name
        is_target_nacional = (
            any("nacional" in kw for kw in norm_keywords) or "nacional" in norm_target_name
        )

        if is_target_nacional and is_candidate_global:
            return MatchResult(
                is_match=False,
                confidence=0.95,
                detected_variant="Global / Importado",
                divergence_reason="Produto cadastrado como Nacional, mas o anúncio é Versão Global/Importada",
                method_used="heuristic",
            )
        if is_target_global and is_candidate_nacional:
            return MatchResult(
                is_match=False,
                confidence=0.95,
                detected_variant="Nacional / Anatel",
                divergence_reason="Produto cadastrado como Global, mas o anúncio é Versão Nacional",
                method_used="heuristic",
            )

        # 3. Capacidade de Memória / Armazenamento Canônica em GB (suporta GB, TB e notação RAM/ROM ex.: 12/256)
        target_caps = extract_storage_capacities_gb(target.nome)
        if not target_caps:
            for kw in target.keywords:
                positive_kw = " ".join(p for p in kw.split() if not p.startswith("-"))
                target_caps = extract_storage_capacities_gb(positive_kw)
                if target_caps:
                    break
        candidate_caps = extract_storage_capacities_gb(candidate_title)

        if target_caps and candidate_caps:
            required_storage = max(target_caps)
            if required_storage not in candidate_caps:
                cand_storage = max(candidate_caps)
                cand_fmt = f"{cand_storage // 1024}TB" if cand_storage >= 1024 and cand_storage % 1024 == 0 else f"{cand_storage}GB"
                req_fmt = f"{required_storage // 1024}TB" if required_storage >= 1024 and required_storage % 1024 == 0 else f"{required_storage}GB"
                return MatchResult(
                    is_match=False,
                    confidence=0.98,
                    detected_variant=cand_fmt,
                    divergence_reason=f"Capacidade do anúncio ({cand_fmt}) difere do alvo ({req_fmt})",
                    method_used="heuristic",
                )

        # 3b. Tamanho de Caixa em Milímetros (ex.: Smartwatches 40mm vs 44mm)
        target_mm = re.findall(r"\b(\d+)\s*mm\b", norm_target_name)
        candidate_mm = re.findall(r"\b(\d+)\s*mm\b", norm_title)
        if target_mm and candidate_mm and target_mm[0] not in candidate_mm:
            return MatchResult(
                is_match=False,
                confidence=0.98,
                detected_variant=f"{candidate_mm[0]}mm",
                divergence_reason=(
                    f"Tamanho de caixa do anúncio ({candidate_mm[0]}mm) difere do alvo ({target_mm[0]}mm)"
                ),
                method_used="heuristic",
            )

        # 4. Detecção de Variante de Cor (respeitando alternativas 'ou'/'/' no catálogo)
        candidate_colors = extract_canonical_colors(candidate_title)
        detected_color = candidate_colors[0] if candidate_colors else None
        required_color = target_required_color(target.nome)

        if required_color and candidate_colors and required_color not in candidate_colors:
            return MatchResult(
                is_match=False,
                confidence=0.90,
                detected_variant=f"Cor: {detected_color}",
                divergence_reason=f"Cor {detected_color} difere da cor desejada ({required_color})",
                method_used="heuristic",
            )

        # 5. Validação Estrita de Exclusões Explícitas (-max, -ultra, -duplo, -f160)
        all_negatives = [
            p[1:] for kw in target.keywords for p in kw.split() if p.startswith("-") and len(p) > 1
        ]
        if all_negatives:
            for neg in all_negatives:
                neg_tokens = match_view(neg).split()
                if neg_tokens and all(t in combined_tokens for t in neg_tokens):
                    return MatchResult(
                        is_match=False,
                        confidence=0.99,
                        divergence_reason=f"Anúncio corresponde a uma variante explicitamente excluída ('-{neg}')",
                        method_used="heuristic",
                    )

        # 6. Overlap de Termos Essenciais + Keywords Estritas
        target_tokens = set(re.findall(r"\b\w{2,}\b", match_view(target.nome)))
        stop_words = {"com", "para", "sem", "pro", "plus", "ultra", "max", "ou", "de", "do", "da"}
        meaningful_target = target_tokens - stop_words

        matched_tokens = meaningful_target.intersection(combined_tokens)
        overlap_ratio = len(matched_tokens) / len(meaningful_target) if meaningful_target else 1.0

        keyword_matched = bool(
            target.keywords and NormalizeProductSkill.matches_keywords(candidate_title, target.keywords)
        )

        if overlap_ratio >= 0.70 or keyword_matched:
            variant_desc = f"Cor: {detected_color}" if detected_color else None
            decision_conf = round(min(1.0, max(overlap_ratio, 0.92 if keyword_matched else 0.85)), 4)
            return MatchResult(
                is_match=True,
                confidence=decision_conf,
                detected_variant=variant_desc,
                method_used="heuristic",
            )

        # Invariante de calibração: quando rejeitado por baixo overlap, `confidence` expressa
        # a certeza da rejeição (1 - overlap_ratio), de modo que `match_probability` == overlap_ratio.
        rejection_conf = round(max(0.55, min(0.99, 1.0 - overlap_ratio)), 4)
        return MatchResult(
            is_match=False,
            confidence=rejection_conf,
            divergence_reason=f"Correspondência insuficiente de termos ({overlap_ratio:.0%})",
            method_used="heuristic",
        )


default_matcher = HybridProductMatcher()
