"""HTTP client tool with retry, realistic headers, and domain-based rate limiting."""

import asyncio
import random
import time
from urllib.parse import urlparse

import httpx
from loguru import logger

from src.config.settings import settings
from src.core.ports.http_port import IHttpClient

# Pool de User-Agents realistas para navegadores modernos
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.5; rv:128.0) Gecko/20100101 Firefox/128.0",
]


class HttpClient(IHttpClient):
    """Cliente HTTP assíncrono com resiliência, headers realistas e rate limiting."""

    def __init__(self):
        self._last_request_time: dict[str, float] = {}
        self._min_domain_delay = 1.0  # Mínimo de 1 segundo entre chamadas para o mesmo domínio

    def _get_headers(self, custom_headers: dict | None = None) -> dict:
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Cache-Control": "max-age=0",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Ch-Ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"macOS"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        }
        if custom_headers:
            headers.update(custom_headers)
        return headers

    async def _rate_limit(self, domain: str) -> None:
        """Garante espaçamento mínimo de requisições por domínio."""
        last_time = self._last_request_time.get(domain, 0.0)
        now = time.time()
        elapsed = now - last_time
        if elapsed < self._min_domain_delay:
            await asyncio.sleep(self._min_domain_delay - elapsed)
        self._last_request_time[domain] = time.time()

    async def fetch(
        self,
        url: str,
        custom_headers: dict | None = None,
        timeout: int | None = None,
        follow_redirects: bool = True,
    ) -> str:
        """Executa GET HTTP com backoff exponencial e tratamento de erros."""
        domain = urlparse(url).netloc
        await self._rate_limit(domain)

        timeout_sec = timeout or settings.REQUEST_TIMEOUT
        max_retries = settings.MAX_RETRIES

        async with httpx.AsyncClient(
            timeout=timeout_sec,
            follow_redirects=follow_redirects,
            verify=True,
        ) as client:
            last_exception = None
            for attempt in range(1, max_retries + 1):
                try:
                    headers = self._get_headers(custom_headers)
                    logger.debug(f"HTTP GET [{attempt}/{max_retries}] {url}")
                    response = await client.get(url, headers=headers)

                    if response.status_code == 200:
                        return response.text

                    if response.status_code in (429, 500, 502, 503, 504):
                        backoff = (2**attempt) + random.uniform(0.5, 1.5)
                        logger.warning(
                            f"HTTP {response.status_code} em {url}. Tentativa {attempt}/{max_retries}. Esperando {backoff:.1f}s..."
                        )
                        await asyncio.sleep(backoff)
                        continue

                    response.raise_for_status()

                except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                    last_exception = exc
                    backoff = (2**attempt) + random.uniform(0.5, 1.5)
                    logger.warning(f"Erro de conexão em {url}: {exc}. Aguardando {backoff:.1f}s...")
                    await asyncio.sleep(backoff)

            raise RuntimeError(
                f"Falha ao obter URL {url} após {max_retries} tentativas: {last_exception}"
            )


# Instância padrão
http_client = HttpClient()
