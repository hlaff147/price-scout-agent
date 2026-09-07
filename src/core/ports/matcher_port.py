"""Port interface for semantic product variant matcher adapters."""

from abc import ABC, abstractmethod

from src.data.models import MatchResult, Product


class IProductMatcher(ABC):
    """Porta para adapters de correspondência semântica e deduplicação de variantes."""

    @abstractmethod
    async def match(
        self,
        target: Product,
        candidate_title: str,
        candidate_url: str = "",
        metadata: dict | None = None,
    ) -> MatchResult:
        """Avalia se um anúncio coletado corresponde ao produto monitorado e sua variante.

        Args:
            target: Produto monitorado cadastrado.
            candidate_title: Título do anúncio extraído na raspagem.
            candidate_url: URL do anúncio.
            metadata: Informações adicionais (marca, especificações, etc.).

        Returns:
            MatchResult indicando correspondência, confiança e motivos de divergência.
        """
        ...
