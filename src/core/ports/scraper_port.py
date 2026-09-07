"""Port interface for marketplace scraper adapters."""

from abc import ABC, abstractmethod

from src.data.models import Product, ScrapedData, Source


class IScraper(ABC):
    """Porta para adapters de scraping e extração de preços de marketplaces."""

    @abstractmethod
    async def run(self, source: Source, product: Product) -> ScrapedData:
        """Executa a coleta de preço para uma determinada fonte e produto.

        Args:
            source: Fonte configurada (marketplace, URL base, método).
            product: Produto com palavras-chave e critérios de busca.

        Returns:
            ScrapedData contendo o resultado da extração.
        """
        pass
