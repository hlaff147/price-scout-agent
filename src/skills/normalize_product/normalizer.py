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

    @classmethod
    def matches_keywords(cls, title: str, keywords: list[str]) -> bool:
        """Verifica se o título normalizado contém todas as palavras essenciais de ao menos uma keyword."""
        if not title or not keywords:
            return False

        norm_title = cls.normalize_text(title)
        title_tokens = set(norm_title.split())

        for kw in keywords:
            norm_kw = cls.normalize_text(kw)
            kw_tokens = norm_kw.split()
            # Se todos os tokens da palavra-chave estiverem presentes no título
            if all(token in title_tokens for token in kw_tokens):
                # Filtrar falsos positivos comuns para eletrônicos (como capinhas/cases se o produto for o fone)
                if cls._is_accessory_false_positive(norm_title, kw_tokens):
                    continue
                return True

        return False

    @staticmethod
    def _is_accessory_false_positive(norm_title: str, kw_tokens: list[str]) -> bool:
        """Detecta se o item parece ser apenas um acessório (capa, case, ponta de silicone)."""
        accessory_words = {"capa", "case", "capinha", "pelicula", "ponteira", "silicone", "protetor", "cabo"}
        title_tokens = set(norm_title.split())
        return bool(
            not any(token in accessory_words for token in kw_tokens)
            and any(acc in title_tokens for acc in accessory_words)
        )
