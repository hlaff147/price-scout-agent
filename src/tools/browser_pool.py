"""Playwright Browser Pool managing shared headless browser instances with resource limits."""

import asyncio
import random

from loguru import logger
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from src.tools.http_client import USER_AGENTS


class PlaywrightBrowserPool:
    """Pool gerenciador de instâncias do Chromium headless para scraping de SPAs e JS-pesados."""

    def __init__(self, max_concurrent: int = 2, timeout_ms: int = 30000):
        self.max_concurrent = max_concurrent
        self.timeout_ms = timeout_ms
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._playwright = None
        self._browser: Browser | None = None
        self._lock = asyncio.Lock()

    async def _ensure_browser(self) -> Browser:
        """Garante que a instância única do navegador esteja ativa."""
        if self._browser is None or not self._browser.is_connected():
            async with self._lock:
                if self._browser is None or not self._browser.is_connected():
                    logger.info("Iniciando instância headless do Chromium (Playwright)...")
                    self._playwright = await async_playwright().start()
                    self._browser = await self._playwright.chromium.launch(
                        headless=True,
                        args=[
                            "--no-sandbox",
                            "--disable-setuid-sandbox",
                            "--disable-dev-shm-usage",
                            "--disable-blink-features=AutomationControlled",
                        ],
                    )
        return self._browser

    async def _configure_page(self, context: BrowserContext) -> Page:
        """Cria e configura uma página isolada com bloqueio de recursos pesados."""
        page = await context.new_page()

        # Interceptação de rotas: aborta imagens, mídias e fontes para poupar CPU e largura de banda
        async def _intercept(route):
            req_type = route.request.resource_type
            if req_type in ("image", "media", "font"):
                await route.abort()
            else:
                await route.continue_()

        await page.route("**/*", _intercept)
        return page

    async def fetch_page_content(
        self,
        url: str,
        wait_selector: str | None = None,
        timeout_ms: int | None = None,
        wait_until: str = "domcontentloaded",
    ) -> str:
        """Carrega uma URL no navegador renderizando JavaScript e retorna o HTML final.

        Args:
            url: URL a ser carregada.
            wait_selector: Seletor CSS opcional para esperar ser renderizado.
            timeout_ms: Timeout em milissegundos.
            wait_until: Condição de parada do carregamento ("domcontentloaded" | "networkidle").

        Returns:
            HTML completo renderizado após execução de scripts.
        """
        timeout = timeout_ms or self.timeout_ms
        user_agent = random.choice(USER_AGENTS)

        async with self._semaphore:
            browser = await self._ensure_browser()
            context = await browser.new_context(
                user_agent=user_agent,
                locale="pt-BR",
                timezone_id="America/Sao_Paulo",
                viewport={"width": 1366, "height": 768},
            )

            try:
                page = await self._configure_page(context)
                logger.debug(f"[Playwright] Navegando para {url} (timeout: {timeout}ms)...")
                await page.goto(url, wait_until=wait_until, timeout=timeout)

                if wait_selector:
                    try:
                        logger.debug(f"[Playwright] Aguardando seletor '{wait_selector}'...")
                        await page.wait_for_selector(wait_selector, timeout=min(timeout, 10000))
                    except Exception as wait_exc:  # noqa: BLE001
                        logger.warning(f"[Playwright] Seletor '{wait_selector}' não apareceu: {wait_exc}")

                # Pequena pausa para permitir renderização de scripts hidratados
                await asyncio.sleep(0.5)
                html_content = await page.content()
                return html_content

            finally:
                await context.close()

    async def close(self) -> None:
        """Fecha o navegador e encerra o runtime do Playwright."""
        async with self._lock:
            if self._browser:
                await self._browser.close()
                self._browser = None
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
            logger.info("Instância do Playwright encerrada.")


# Instância compartilhada
browser_pool = PlaywrightBrowserPool()
