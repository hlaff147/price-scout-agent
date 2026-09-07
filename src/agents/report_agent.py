"""ADK Report Agent generating interactive HTML reports."""

from pathlib import Path
from typing import AsyncGenerator

from google.adk.agents import BaseAgent, InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types
from loguru import logger
from pydantic import PrivateAttr

from src.data.models import Product
from src.reporting.report_generator import ReportGenerator


class AdkReportAgent(BaseAgent):
    """Agente ADK responsável pela geração do relatório HTML visual pós-ciclo."""

    _generator: ReportGenerator = PrivateAttr()

    def __init__(self, generator: ReportGenerator | None = None, name: str = "report_agent", **kwargs):
        super().__init__(name=name, **kwargs)
        self._generator = generator or ReportGenerator()

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        generate_report: bool = ctx.session.state.get("generate_report", True)
        open_browser: bool = ctx.session.state.get("open_browser", False)
        product: Product | None = ctx.session.state.get("product")

        if not generate_report or not product:
            msg = "Geração de relatório ignorada conforme configuração."
            yield Event(
                author=self.name,
                actions=EventActions(state_delta={"report_path": None}),
                content=types.Content(parts=[types.Part.from_text(text=msg)]),
            )
            return

        # Montar o resumo esperado pelo ReportGenerator a partir do session state
        cycle_summary = {
            "total_products": 1,
            "cycles": [
                {
                    "product_id": product.id,
                    "sources_checked": ctx.session.state.get("sources_checked", 0),
                    "prices_collected": ctx.session.state.get("prices_collected", 0),
                    "deals_found": ctx.session.state.get("deals_found", 0),
                    "no_results": ctx.session.state.get("no_results", 0),
                    "errors": ctx.session.state.get("errors", 0),
                    "analyses": ctx.session.state.get("analyses", []),
                }
            ],
        }

        report_path: Path | None = self._generator.generate(
            summary=cycle_summary,
            open_browser=open_browser,
        )

        resolved_path = str(report_path.resolve()) if report_path else None
        if report_path:
            summary_text = f"Relatório HTML interativo gerado em: {resolved_path}"
        else:
            summary_text = "Nenhum relatório foi gerado."

        logger.info(f"[{self.name}] {summary_text}")

        yield Event(
            author=self.name,
            actions=EventActions(state_delta={"report_path": resolved_path}),
            content=types.Content(parts=[types.Part.from_text(text=summary_text)]),
        )
