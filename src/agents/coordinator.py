"""ADK Coordinator constructing the multi-agent monitoring pipeline."""

from google.adk.agents import BaseAgent, SequentialAgent

from src.agents.analyst_agent import AdkAnalystAgent
from src.agents.notifier_agent import AdkNotifierAgent
from src.agents.report_agent import AdkReportAgent
from src.agents.scraper_agent import AdkScraperAgent
from src.core.ports.analyst_port import IAnalyst
from src.core.ports.notifier_port import INotifier
from src.core.ports.scraper_port import IScraper
from src.reporting.report_generator import ReportGenerator


def build_promoradar_adk_pipeline(
    scraper: IScraper | None = None,
    analyst: IAnalyst | None = None,
    notifier: INotifier | None = None,
    report_generator: ReportGenerator | None = None,
    name: str = "promoradar_coordinator",
) -> BaseAgent:
    """Constrói o pipeline orquestrador do PromoRadar baseado no Google ADK.

    O pipeline executa deterministicamente as 4 etapas sequenciais:
    1. ScraperAgent: Coleta paralela de todas as fontes ativas do produto.
    2. AnalystAgent: Análise histórica, detecção de falso desconto e identificação de deals.
    3. NotifierAgent: Emissão de alertas (Telegram / Console) com proteção anti-spam.
    4. ReportAgent: Geração do relatório visual em HTML com gráficos de preço.

    Args:
        scraper: Adapter opcional de scraping (IScraper).
        analyst: Adapter opcional de análise de preço (IAnalyst).
        notifier: Adapter opcional de notificação (INotifier).
        report_generator: Gerador opcional de relatórios.
        name: Identificador do agente coordenador.

    Returns:
        Instância de SequentialAgent configurada com todos os subagentes.
    """
    scraper_agent = AdkScraperAgent(scraper=scraper, name="scraper_agent")
    analyst_agent = AdkAnalystAgent(analyst=analyst, name="analyst_agent")
    notifier_agent = AdkNotifierAgent(notifier=notifier, name="notifier_agent")
    report_agent = AdkReportAgent(generator=report_generator, name="report_agent")

    return SequentialAgent(
        name=name,
        sub_agents=[
            scraper_agent,
            analyst_agent,
            notifier_agent,
            report_agent,
        ],
    )
