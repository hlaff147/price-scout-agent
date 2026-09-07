"""Shared domain-based rate limiter preventing marketplace IP blocking across concurrent products."""

import asyncio
import random
import time
from contextlib import asynccontextmanager
from typing import ClassVar
from urllib.parse import urlparse

from loguru import logger


class DomainRateLimiter:
    """Rate limiter compartilhado por domínio com semáforo/lock e jitter temporal."""

    # Intervalos mínimos customizados em segundos por marketplace/domínio
    DEFAULT_DELAYS: ClassVar[dict[str, float]] = {
        "mercadolivre.com.br": 2.0,
        "lista.mercadolivre.com.br": 2.0,
        "amazon.com.br": 2.5,
        "shopee.com.br": 3.0,
        "kabum.com.br": 2.0,
        "aliexpress.com": 3.0,
        "google.com": 1.5,
    }

    def __init__(self, default_min_delay: float = 1.5):
        self._default_min_delay = default_min_delay
        self._last_request_time: dict[str, float] = {}
        self._domain_locks: dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    def _normalize_domain(self, target: str) -> str:
        """Extrai o netloc normalizado de uma URL ou retorna a string de domínio limpa."""
        if "://" in target:
            netloc = urlparse(target).netloc.lower()
        else:
            netloc = target.lower()
        netloc = netloc.removeprefix("www.")
        return netloc

    async def _get_lock_for_domain(self, domain: str) -> asyncio.Lock:
        """Garante a existência de um lock por domínio de forma concorrente e segura."""
        if domain not in self._domain_locks:
            async with self._global_lock:
                if domain not in self._domain_locks:
                    self._domain_locks[domain] = asyncio.Lock()
        return self._domain_locks[domain]

    def get_min_delay(self, domain: str) -> float:
        """Retorna o delay configurado para o domínio ou o delay padrão."""
        for pattern, delay in self.DEFAULT_DELAYS.items():
            if pattern in domain:
                return delay
        return self._default_min_delay

    @asynccontextmanager
    async def acquire(self, target: str):
        """Context manager assíncrono que bloqueia requisições concorrentes ao mesmo domínio."""
        domain = self._normalize_domain(target)
        lock = await self._get_lock_for_domain(domain)

        async with lock:
            last_time = self._last_request_time.get(domain, 0.0)
            min_delay = self.get_min_delay(domain)
            # Adiciona jitter aleatório de até 30% para simular comportamento humano
            jitter = random.uniform(0.1, 0.4)
            required_delay = min_delay + jitter

            now = time.time()
            elapsed = now - last_time
            if elapsed < required_delay:
                wait_time = required_delay - elapsed
                logger.debug(f"[RateLimiter] Espaçando chamada para {domain} em {wait_time:.2f}s...")
                await asyncio.sleep(wait_time)

            try:
                yield domain
            finally:
                self._last_request_time[domain] = time.time()


# Instância compartilhada global
shared_rate_limiter = DomainRateLimiter()
