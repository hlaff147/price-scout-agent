"""HTTP client tool with retry, realistic headers, anti-SSRF validation, and per-attempt rate limiting."""

from __future__ import annotations

import asyncio
import random
from contextlib import asynccontextmanager

import httpx
from loguru import logger
from typing_extensions import Self

from src.config.settings import settings
from src.core.domain import validate_external_http_url
from src.core.ports.http_port import IHttpClient
from src.tools.rate_limiter import DomainRateLimiter, shared_rate_limiter

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.5; rv:128.0) Gecko/20100101 Firefox/128.0",
]


class HttpClient(IHttpClient):
    """Cliente HTTP assíncrono com validação anti-SSRF, rate limiting por tentativa e pool opcional."""

    def __init__(self, rate_limiter: DomainRateLimiter | None = None):
        self.rate_limiter = rate_limiter or shared_rate_limiter
        self._shared_client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> Self:
        if self._shared_client is None or self._shared_client.is_closed:
            self._shared_client = httpx.AsyncClient(
                timeout=settings.REQUEST_TIMEOUT,
                follow_redirects=True,
                verify=True,
            )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def close(self) -> None:
        """Encerra o pool HTTP compartilhado se estiver ativo."""
        if self._shared_client is not None and not self._shared_client.is_closed:
            await self._shared_client.aclose()
        self._shared_client = None

    @asynccontextmanager
    async def _client_scope(self, timeout_sec: int, follow_redirects: bool):
        if self._shared_client is not None and not self._shared_client.is_closed:
            yield self._shared_client
        else:
            async with httpx.AsyncClient(
                timeout=timeout_sec,
                follow_redirects=follow_redirects,
                verify=True,
            ) as ephemeral:
                yield ephemeral

    def _get_headers(self, custom_headers: dict | None = None) -> dict:
        ua = random.choice(USER_AGENTS)
        headers = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate",
            "Cache-Control": "max-age=0",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        }
        if "Chrome/" in ua:
            ver = ua.split("Chrome/")[1].split(".")[0]
            platform = (
                '"Windows"'
                if "Windows" in ua
                else ('"Linux"' if "Linux" in ua else '"macOS"')
            )
            headers["Sec-Ch-Ua"] = (
                f'"Chromium";v="{ver}", "Not;A=Brand";v="24", "Google Chrome";v="{ver}"'
            )
            headers["Sec-Ch-Ua-Mobile"] = "?0"
            headers["Sec-Ch-Ua-Platform"] = platform
        if custom_headers:
            headers.update(custom_headers)
        return headers

    async def fetch(
        self,
        url: str,
        custom_headers: dict | None = None,
        timeout: int | None = None,
        follow_redirects: bool = True,
    ) -> str:
        """Executa GET HTTP validando URL externa e liberando o lock de domínio durante o backoff."""
        validated_url = validate_external_http_url(url, allow_private=settings.ALLOW_PRIVATE_URLS)
        timeout_sec = timeout or settings.REQUEST_TIMEOUT
        max_retries = settings.MAX_RETRIES

        async with self._client_scope(timeout_sec, follow_redirects) as client:
            last_exception: Exception | None = None
            for attempt in range(1, max_retries + 1):
                try:
                    headers = self._get_headers(custom_headers)
                    async with self.rate_limiter.acquire(validated_url):
                        logger.debug(f"HTTP GET [{attempt}/{max_retries}] {validated_url}")
                        response = await client.get(
                            validated_url,
                            headers=headers,
                            timeout=timeout_sec,
                            follow_redirects=follow_redirects,
                        )

                    if response.status_code == 200:
                        return response.text

                    if response.status_code in (429, 500, 502, 503, 504):
                        last_exception = httpx.HTTPStatusError(
                            f"HTTP {response.status_code}",
                            request=response.request,
                            response=response,
                        )
                        if attempt < max_retries:
                            backoff = (2**attempt) + random.uniform(0.5, 1.5)
                            logger.warning(
                                f"HTTP {response.status_code} em {validated_url}. "
                                f"Tentativa {attempt}/{max_retries}. Esperando {backoff:.1f}s..."
                            )
                            await asyncio.sleep(backoff)
                        continue

                    response.raise_for_status()

                except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                    last_exception = exc
                    if attempt < max_retries:
                        backoff = (2**attempt) + random.uniform(0.5, 1.5)
                        logger.warning(
                            f"Erro de conexão em {validated_url}: {exc}. Aguardando {backoff:.1f}s..."
                        )
                        await asyncio.sleep(backoff)

            raise RuntimeError(
                f"Falha ao obter URL {validated_url} após {max_retries} tentativas: {last_exception}"
            )


http_client = HttpClient()
