"""ADK Analyst Agent evaluating price history and deals."""

from typing import AsyncGenerator

from google.adk.agents import BaseAgent, InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types
from loguru import logger
from pydantic import PrivateAttr

from src.core.ports.analyst_port import IAnalyst
from src.data.models import DealAnalysis, Product, ScrapedData, Source
from src.subagents.price_analyst_agent.agent import PriceAnalystSubagent


class AdkAnalystAgent(BaseAgent):
    """Agente ADK responsável pela análise de ofertas, desconto real e mínimo histórico."""

    _analyst: IAnalyst = PrivateAttr()

    def __init__(self, analyst: IAnalyst | None = None, name: str = "analyst_agent", **kwargs):
        super().__init__(name=name, **kwargs)
        self._analyst = analyst or PriceAnalystSubagent()

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        product: Product | None = ctx.session.state.get("product")
        scraped_pairs: list[tuple[Source, ScrapedData]] = ctx.session.state.get("scraped_pairs", [])

        if not product:
            msg = f"Nenhum produto encontrado no estado para {self.name}."
            logger.warning(msg)
            yield Event(
                author=self.name,
                actions=EventActions(state_delta={"analyses": [], "deals_found": 0}),
                content=types.Content(parts=[types.Part.from_text(text=msg)]),
            )
            return

        logger.info(f"[{self.name}] Analisando {len(scraped_pairs)} cotações para '{product.nome}'...")

        analyses: list[DealAnalysis] = await self._analyst.run(product, scraped_pairs)
        deals = [d for d in analyses if d.is_deal]

        if deals:
            summary_text = (
                f"Análise concluída: {len(deals)} oportunidade(s) detectada(s) para '{product.nome}'! "
                f"Melhor preço: R$ {min(d.preco_atual for d in deals):.2f}"
            )
        else:
            summary_text = f"Análise concluída: Nenhuma oferta vantajosa no momento para '{product.nome}'."

        logger.info(f"[{self.name}] {summary_text}")

        yield Event(
            author=self.name,
            actions=EventActions(
                state_delta={
                    "analyses": analyses,
                    "deals_found": len(deals),
                }
            ),
            content=types.Content(parts=[types.Part.from_text(text=summary_text)]),
        )
