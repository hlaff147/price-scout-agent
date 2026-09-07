"""Port interface for HTTP client adapters."""

from abc import ABC, abstractmethod


class IHttpClient(ABC):
    """Porta para adapters de clientes HTTP (Httpx, Playwright, Requests, etc.)."""

    @abstractmethod
    async def fetch(
        self,
        url: str,
        custom_headers: dict | None = None,
        timeout: int | None = None,
        follow_redirects: bool = True,
    ) -> str:
        """Executa uma requisição HTTP GET retornando o conteúdo textual (HTML).

        Args:
            url: URL de destino.
            custom_headers: Cabeçalhos HTTP adicionais.
            timeout: Tempo limite em segundos.
            follow_redirects: Se deve seguir redirecionamentos HTTP 3xx.

        Returns:
            Corpo textual da resposta.
        """
        pass
