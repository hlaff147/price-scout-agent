"""ADK Scraper Agent coordinating marketplace extraction."""

import asyncio
from typing import AsyncGenerator

from google.adk.agents import BaseAgent, InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types
from loguru import logger
from pydantic import PrivateAttr

from src.core.ports.scraper_port import IScraper
from src.data.models import Product, ScrapedData, Source
from src.subagents.scraper_agent.agent import ScraperSubagent


class AdkScraperAgent(BaseAgent):
    """Agente ADK responsável pela coleta paralela de preços nos marketplaces."""

    _scraper: IScraper = PrivateAttr()

    def __init__(self, scraper: IScraper | None = None, name: str = "scraper_agent", **kwargs):
        super().__init__(name=name, **kwargs)
        self._scraper = scraper or ScraperSubagent()

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        product: Product | None = ctx.session.state.get("product")
        sources: list[Source] = ctx.session.state.get("sources", [])

        if not product or not sources:
            msg = f"Nenhum produto ou fontes ativas encontradas no estado da sessão para {self.name}."
            logger.warning(msg)
            yield Event(
                author=self.name,
                actions=EventActions(state_delta={"scraped_pairs": [], "sources_checked": 0, "prices_collected": 0}),
                content=types.Content(parts=[types.Part.from_text(text=msg)]),
            )
            return

        logger.info(f"[{self.name}] Disparando coleta para {len(sources)} fontes de '{product.nome}'...")

        tasks = [self._scraper.run(source, product) for source in sources]
        results: list[ScrapedData | BaseException] = await asyncio.gather(*tasks, return_exceptions=True)

        scraped_pairs = []
        error_count = 0
        no_result_count = 0

        for source, res in zip(sources, results):
            if isinstance(res, Exception):
                error_count += 1
                logger.error(f"Erro não tratado no scraper [{source.marketplace}]: {res}")
            elif isinstance(res, ScrapedData):
                if not res.success:
                    msg = (res.error_message or "").lower()
                    if "nenhum produto" in msg or ("nenhum" in msg and "correspondente" in msg):
                        no_result_count += 1
                    else:
                        error_count += 1
                scraped_pairs.append((source, res))

        prices_collected = len([p for _, p in scraped_pairs if p.preco])

        summary_text = (
            f"Coleta concluída para '{product.nome}': {len(sources)} fontes consultadas, "
            f"{prices_collected} preços encontrados, {no_result_count} sem resultado, {error_count} erros."
        )
        logger.info(f"[{self.name}] {summary_text}")

        yield Event(
            author=self.name,
            actions=EventActions(
                state_delta={
                    "scraped_pairs": scraped_pairs,
                    "sources_checked": len(sources),
                    "prices_collected": prices_collected,
                    "no_results": no_result_count,
                    "errors": error_count,
                }
            ),
            content=types.Content(parts=[types.Part.from_text(text=summary_text)]),
        )
