"""Port interface for price analyst adapters."""

from abc import ABC, abstractmethod

from src.data.models import DealAnalysis, Product, ScrapedData, Source


class IAnalyst(ABC):
    """Porta para adapters de análise de preços, histórico e falso desconto."""

    @abstractmethod
    async def run(
        self,
        product: Product,
        scraped_results: list[tuple[Source, ScrapedData]],
    ) -> list[DealAnalysis]:
        """Analisa os dados coletados das fontes em relação ao histórico.

        Args:
            product: Produto analisado.
            scraped_results: Lista de pares (fonte, dados coletados).

        Returns:
            Lista de DealAnalysis contendo pareceres de compra.
        """
        pass
