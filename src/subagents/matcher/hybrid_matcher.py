"""Semantic and heuristic product variant matcher adapter implementing IProductMatcher."""

import re
import unicodedata

from loguru import logger

from src.core.ports.matcher_port import IProductMatcher
from src.data.models import MatchResult, Product
from src.skills.normalize_product.normalizer import NormalizeProductSkill


def normalize_text(text: str) -> str:
    """Normaliza texto removendo acentos, pontuação redundante e espaços extras."""
    if not text:
        return ""
    # Remove acentos
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(c for c in normalized if not unicodedata.combining(c))
    # Converte para minúsculas e remove pontuação estranha mantendo alfanuméricos
    cleaned = re.sub(r"[^\w\s-]", " ", ascii_text.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


class HybridProductMatcher(IProductMatcher):
    """Matcher híbrido que combina regras heurísticas rígidas e similaridade de tokens."""

    # Palavras-chave indicativas de acessórios não desejados
    ACCESSORY_KEYWORDS = (
        "capa", "capas", "capinha", "capinhas", "case", "cases", "pelicula", "peliculas",
        "protecao", "cabo", "cabos", "carregador", "carregadores", "carregador para",
        "suporte", "suportes", "suporte para", "bracadeira", "cordao", "alca",
        "adaptador", "adaptadores", "adaptador para", "protetor", "protetores",
        "pulseira", "pulseiras", "bracelete", "braceletes", "strap", "straps",
        "bezel", "dock", "docks", "fonte", "fontes",
    )

    # Cores conhecidas
    COMMON_COLORS = (
        "preto", "preta", "black",
        "branco", "branca", "white",
        "cinza", "gray", "grey",
        "azul", "blue",
        "verde", "green",
        "prata", "silver",
        "dourado", "gold",
        "rosa", "pink",
    )

    async def match(
        self,
        target: Product,
        candidate_title: str,
        candidate_url: str = "",
        metadata: dict | None = None,
    ) -> MatchResult:
        """Avalia se candidate_title corresponde com precisão a target."""
        if not candidate_title:
            return MatchResult(
                is_match=False,
                confidence=0.0,
                divergence_reason="Título do anúncio vazio",
                method_used="heuristic",
            )

        norm_title = normalize_text(candidate_title)
        norm_target_name = normalize_text(target.nome)
        norm_keywords = [normalize_text(kw) for kw in target.keywords if kw]

        title_words = set(re.findall(r"\b\w+\b", norm_title))

        # 1. Filtro de Acessórios (evita casquinha/película/fonte/suporte no lugar do produto principal)
        for acc in self.ACCESSORY_KEYWORDS:
            # Só descarta se o produto original não for ele próprio um acessório
            if acc in norm_target_name:
                continue
            if acc == "cabo" and norm_title.startswith("monitor "):
                continue
            matched_acc = (acc in norm_title) if " " in acc else (acc in title_words)
            if matched_acc:
                logger.debug(f"[Matcher] Descartado: anúncio '{candidate_title}' parece ser acessório ({acc})")
                return MatchResult(
                    is_match=False,
                    confidence=0.99,
                    divergence_reason=f"Anúncio identificado como acessório/peça secundária ('{acc}')",
                    method_used="heuristic",
                )

        # 1b. Filtro de Produtos Recondicionados / Vitrine / Usados
        if any(term in title_words for term in NormalizeProductSkill.REFURBISHED_TERMS):
            logger.debug(f"[Matcher] Descartado: anúncio '{candidate_title}' parece ser item usado/vitrine")
            return MatchResult(
                is_match=False,
                confidence=0.99,
                divergence_reason="Anúncio identificado como item usado, vitrine ou recondicionado",
                method_used="heuristic",
            )

        # 2. Edição Global vs Nacional (Premissa de Negócio: NÃO deduplicar)
        is_candidate_global = "global" in title_words or "importado" in title_words
        is_candidate_nacional = "nacional" in title_words or "brasil" in title_words or "anatel" in title_words

        is_target_global = any("global" in kw for kw in norm_keywords) or "global" in norm_target_name
        is_target_nacional = any("nacional" in kw for kw in norm_keywords) or "nacional" in norm_target_name

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

        # 3. Capacidade de Memória / Armazenamento (ex.: 16GB, 128GB, 256GB)
        # Celulares costumam listar RAM + armazenamento ("12GB RAM 512GB" / "12/512GB"):
        # o anúncio só diverge se a capacidade-alvo não aparecer em nenhuma posição.
        target_capacity_match = re.findall(r"\b(\d+)\s*(?:gb|tb)\b", norm_target_name)
        candidate_capacity_match = re.findall(r"\b(\d+)\s*(?:gb|tb)\b", norm_title)

        if (
            target_capacity_match
            and candidate_capacity_match
            and target_capacity_match[-1] not in candidate_capacity_match
        ):
            return MatchResult(
                    is_match=False,
                    confidence=0.98,
                    detected_variant=f"{candidate_capacity_match[-1]}GB",
                    divergence_reason=(
                        f"Capacidade do anúncio ({candidate_capacity_match[-1]}GB) difere "
                        f"do alvo ({target_capacity_match[-1]}GB)"
                    ),
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

        # 4. Detecção de Variante de Cor
        detected_color = None
        for color in self.COMMON_COLORS:
            if color in title_words:
                detected_color = color.capitalize()
                break

        # Se o produto requer cor específica
        target_color = None
        for color in self.COMMON_COLORS:
            if color in norm_target_name:
                target_color = color
                break

        if target_color and detected_color and target_color != detected_color.lower():
            return MatchResult(
                is_match=False,
                confidence=0.90,
                detected_variant=f"Cor: {detected_color}",
                divergence_reason=f"Cor {detected_color} difere da cor desejada ({target_color})",
                method_used="heuristic",
            )

        # 5. Overlap de Termos Essenciais e Validação Estrita de Exclusões
        all_negatives = [
            p[1:] for kw in target.keywords for p in kw.split() if p.startswith("-") and len(p) > 1
        ]
        if all_negatives:
            combined_tokens = title_words | set(NormalizeProductSkill.match_view(candidate_title).split())
            for neg in all_negatives:
                neg_tokens = NormalizeProductSkill.match_view(neg).split()
                if neg_tokens and all(t in combined_tokens for t in neg_tokens):
                    return MatchResult(
                        is_match=False,
                        confidence=0.99,
                        divergence_reason=f"Anúncio corresponde a uma variante explicitamente excluída ('-{neg}')",
                        method_used="heuristic",
                    )

        target_tokens = set(re.findall(r"\b\w{2,}\b", norm_target_name))
        # Remove palavras genéricas
        stop_words = {"com", "para", "sem", "pro", "plus", "ultra", "max"}
        meaningful_target = target_tokens - stop_words

        matched_tokens = meaningful_target.intersection(title_words)
        if meaningful_target:
            overlap_ratio = len(matched_tokens) / len(meaningful_target)
        else:
            overlap_ratio = 1.0

        # Verifica se alguma keyword atende aos critérios estritos da skill
        keyword_matched = False
        if target.keywords:
            keyword_matched = NormalizeProductSkill.matches_keywords(candidate_title, target.keywords)

        if overlap_ratio >= 0.70 or keyword_matched:
            variant_desc = f"Cor: {detected_color}" if detected_color else None
            return MatchResult(
                is_match=True,
                confidence=max(overlap_ratio, 0.85),
                detected_variant=variant_desc,
                method_used="heuristic",
            )

        return MatchResult(
            is_match=False,
            confidence=overlap_ratio,
            divergence_reason=f"Correspondência insuficiente de termos ({overlap_ratio:.0%})",
            method_used="heuristic",
        )


# Instância padrão
default_matcher = HybridProductMatcher()
