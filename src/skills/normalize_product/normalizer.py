"""Product and price normalization skill."""

import re
import unicodedata

from src.skills.base import BaseSkill


class NormalizeProductSkill(BaseSkill):
    """Normaliza strings de preços, títulos e validações de produto."""

    name = "normalize_product"
    description = "Normaliza textos, preços e variantes de produtos."

    def execute(self, text: str) -> str:
        return self.normalize_text(text)

    @staticmethod
    def normalize_text(text: str) -> str:
        """Remove acentos, converte para minúsculas e remove espaços redundantes."""
        if not text:
            return ""
        # Decompor caracteres acentuados
        nfkd = unicodedata.normalize("NFKD", text)
        only_ascii = "".join([c for c in nfkd if not unicodedata.combining(c)])
        # Manter apenas alfanuméricos e espaços
        clean = re.sub(r"[^\w\s]", " ", only_ascii.lower())
        return re.sub(r"\s+", " ", clean).strip()

    @staticmethod
    def parse_price_string(raw: str | None) -> float | None:
        """Converte strings monetárias variadas (BRL) para float.
        
        Exemplos:
        - "R$ 1.299,90" -> 1299.90
        - "R$ 850" -> 850.00
        - "1,450.00" -> 1450.00
        - "849,99" -> 849.99
        """
        if not raw:
            return None

        # Limpar espaços e prefixos comuns
        cleaned = raw.replace("R$", "").replace("\xa0", " ").strip()

        # Se tiver formato brasileiro 1.234,56
        if re.search(r"\d+\.\d{3},\d{2}", cleaned):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        # Se tiver formato com vírgula decimal simples: 1299,90 ou 850,00
        elif "," in cleaned and "." not in cleaned:
            cleaned = cleaned.replace(",", ".")
        # Se tiver formato com ponto decimal e vírgula de milhar: 1,299.90
        elif "," in cleaned and "." in cleaned:
            # Caso a vírgula venha antes do ponto (formato americano)
            if cleaned.find(",") < cleaned.find("."):
                cleaned = cleaned.replace(",", "")
            else:
                cleaned = cleaned.replace(".", "").replace(",", ".")

        # Extrair primeiro padrão numérico válido
        match = re.search(r"(\d+(?:\.\d{1,2})?)", cleaned)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None
        return None

    # "512 GB" / "512gb" / "512 Gb" -> token único "512gb" (essencial para variantes de celulares)
    STORAGE_PATTERN = re.compile(r"\b(\d+)\s*(gb|tb)\b")
    STORAGE_TOKEN = re.compile(r"^\d+(?:gb|tb)$")

    # Anúncios que não representam produto novo (contaminariam a mínima histórica)
    REFURBISHED_TERMS = frozenset({
        "recondicionado", "recondicionada", "seminovo", "seminova", "usado", "usada",
        "vitrine", "refurbished", "reembalado", "reembalada", "mostruario",
    })

    @classmethod
    def match_view(cls, text: str) -> str:
        """Visão normalizada para matching: 'S25+' -> 's25 plus' e '512 GB' -> '512gb'."""
        if not text:
            return ""
        expanded = re.sub(r"(?<=\w)\+", " plus ", text)
        return cls.STORAGE_PATTERN.sub(r"\1\2", cls.normalize_text(expanded))

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

        for kw in keywords:
            raw_parts = kw.split()
            negatives = [p[1:] for p in raw_parts if p.startswith("-") and len(p) > 1]
            positive_raw = " ".join(p for p in raw_parts if not (p.startswith("-") and len(p) > 1))
            kw_tokens = cls.match_view(positive_raw).split()
            if not kw_tokens:
                continue
            # Se todos os tokens da palavra-chave estiverem presentes no título
            if not all(token in title_tokens for token in kw_tokens):
                continue
            # Exclusões explícitas da keyword
            if any(
                (neg_tokens := cls.match_view(neg).split())
                and all(t in title_tokens for t in neg_tokens)
                for neg in negatives
            ):
                continue
            # Itens usados / recondicionados / vitrine nunca entram na série de preços de novos
            if any(t in title_tokens and t not in kw_tokens for t in cls.REFURBISHED_TERMS):
                continue
            # Keyword ancorada em capacidade (ex.: '512gb') presente no título = anúncio do aparelho
            device_title = any(cls.STORAGE_TOKEN.match(t) for t in kw_tokens)
            # Filtrar falsos positivos comuns para eletrônicos (como capinhas/cases se o produto for o fone)
            if cls._is_accessory_false_positive(norm_title, kw_tokens, device_title=device_title):
                continue
            return True

        return False

    @staticmethod
    def _is_accessory_false_positive(
        norm_title: str,
        kw_tokens: list[str],
        device_title: bool = False,
    ) -> bool:
        """Detecta se o item parece ser apenas um acessório (capa, case, fonte, suporte, peça).

        Com ``device_title=True`` (título contém a capacidade de armazenamento procurada),
        brindes citados no meio do título ('+ Capa + Película', 'Cabo incluso') são tolerados;
        apenas títulos que COMEÇAM com o acessório são descartados.
        """
        if device_title:
            accessory_starts = (
                "capa ", "capinha ", "case ", "pelicula ", "protetor ", "kit capa", "kit pelicula",
                "cabo ", "fonte ", "carregador ", "suporte ", "adaptador ", "tela ", "display ",
                "bateria ", "tampa ", "lente ", "placa ", "pulseira ", "bracelete ", "strap ",
            )
            return norm_title.startswith(accessory_starts)

        strict_accessory_words = {
            "capa", "case", "capinha", "pelicula", "ponteira", "silicone", "protetor",
            "pulseira", "bracelete", "strap", "bezel",
        }
        title_tokens = set(norm_title.split())
        if (
            not any(token in strict_accessory_words for token in kw_tokens)
            and any(acc in title_tokens for acc in strict_accessory_words)
        ):
            return True

        # Para "cabo", descartar apenas se o título não começar com "monitor" (muitos monitores citam "cabo DP incluso")
        if (
            "cabo" not in kw_tokens
            and "cabo" in title_tokens
            and not norm_title.startswith("monitor ")
        ):
            return True

        accessory_phrases = (
            "fonte para ",
            "fonte carregador",
            "carregador para ",
            "cabo carregador para ",
            "dock de carregamento",
            "pulseira para ",
            "pulseira compativel",
            "bracelete para ",
            "suporte para ",
            "suporte articulado",
            "adaptador para ",
            "placa principal",
            "base pedestal",
            "tela reposicao",
            "display reposicao",
        )
        norm_kw_str = " ".join(kw_tokens)
        if any(phrase in norm_title and phrase.strip() not in norm_kw_str for phrase in accessory_phrases):
            return True

        accessory_prefixes = (
            "cabo ", "fonte ", "carregador ", "suporte ", "adaptador ", "placa ", "pedestal ",
            "pulseira ", "bracelete ", "strap ",
        )
        return bool(
            norm_title.startswith(accessory_prefixes)
            and not norm_kw_str.startswith(accessory_prefixes)
        )
