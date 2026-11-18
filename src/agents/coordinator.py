"""ADK Coordinator constructing the multi-agent monitoring pipeline with explicit DI."""

from __future__ import annotations

from google.adk.agents import BaseAgent, SequentialAgent

from src.agents.analyst_agent import AdkAnalystAgent
from src.agents.notifier_agent import AdkNotifierAgent
from src.agents.report_agent import AdkReportAgent
from src.agents.scraper_agent import AdkScraperAgent
from src.core.ports.analyst_port import IAnalyst
from src.core.ports.notifier_port import INotifier
from src.core.ports.repository_port import IRepository
from src.core.ports.scraper_port import IScraper
from src.reporting.report_generator import ReportGenerator
from src.subagents.notifier_agent.agent import NotifierSubagent
from src.subagents.price_analyst_agent.agent import PriceAnalystSubagent


def build_promoradar_adk_pipeline(
    scraper: IScraper | None = None,
    analyst: IAnalyst | None = None,
    notifier: INotifier | None = None,
    report_generator: ReportGenerator | None = None,
    repository: IRepository | None = None,
    name: str = "promoradar_coordinator",
) -> BaseAgent:
    """Constrói o pipeline orquestrador do PromoRadar propagando o mesmo `IRepository` a todos os agentes."""
    resolved_analyst = analyst or (
        PriceAnalystSubagent(repository=repository) if repository is not None else None
    )
    resolved_notifier = notifier or (
        NotifierSubagent(repository=repository) if repository is not None else None
    )
    resolved_report_gen = report_generator or (
        ReportGenerator(repository=repository) if repository is not None else None  # type: ignore[arg-type]
    )

    scraper_agent = AdkScraperAgent(scraper=scraper, name="scraper_agent")
    analyst_agent = AdkAnalystAgent(analyst=resolved_analyst, name="analyst_agent")
    notifier_agent = AdkNotifierAgent(notifier=resolved_notifier, name="notifier_agent")
    report_agent = AdkReportAgent(generator=resolved_report_gen, name="report_agent")

    return SequentialAgent(
        name=name,
        sub_agents=[
            scraper_agent,
            analyst_agent,
            notifier_agent,
            report_agent,
        ],
    )
