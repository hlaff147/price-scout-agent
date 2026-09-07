"""ADK Notifier Agent managing alerts and notifications."""

from collections.abc import AsyncGenerator

from google.adk.agents import BaseAgent, InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types
from loguru import logger
from pydantic import PrivateAttr

from src.core.ports.notifier_port import INotifier
from src.data.models import DealAnalysis, Product
from src.subagents.notifier_agent.agent import NotifierSubagent


class AdkNotifierAgent(BaseAgent):
    """Agente ADK responsável pela emissão de alertas e proteção anti-spam."""

    _notifier: INotifier = PrivateAttr()

    def __init__(self, notifier: INotifier | None = None, name: str = "notifier_agent", **kwargs):
        super().__init__(name=name, **kwargs)
        self._notifier = notifier or NotifierSubagent()

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        product: Product | None = ctx.session.state.get("product")
        analyses: list[DealAnalysis] = ctx.session.state.get("analyses", [])
        dry_run: bool = ctx.session.state.get("dry_run", False)

        if not product:
            msg = f"Nenhum produto configurado no estado para {self.name}."
            yield Event(
                author=self.name,
                actions=EventActions(state_delta={"notifications_sent": 0}),
                content=types.Content(parts=[types.Part.from_text(text=msg)]),
            )
            return

        deals = [d for d in analyses if d.is_deal]
        sent_count = 0

        for deal in deals:
            success = await self._notifier.run(deal, product, dry_run=dry_run)
            if success:
                sent_count += 1

        if sent_count > 0:
            summary_text = f"Notificações processadas: {sent_count} alerta(s) emitido(s) para '{product.nome}'."
        else:
            summary_text = f"Nenhum alerta novo necessário para '{product.nome}'."

        logger.info(f"[{self.name}] {summary_text}")

        yield Event(
            author=self.name,
            actions=EventActions(state_delta={"notifications_sent": sent_count}),
            content=types.Content(parts=[types.Part.from_text(text=summary_text)]),
        )
