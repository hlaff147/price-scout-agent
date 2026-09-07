from src.core.ports.analyst_port import IAnalyst
from src.core.ports.coupon_port import ICouponRepositoryPort
from src.core.ports.http_port import IHttpClient
from src.core.ports.notifier_port import INotifier
from src.core.ports.product_management_port import IProductManagementPort
from src.core.ports.repository_port import IRepository
from src.core.ports.scraper_port import IScraper
from src.core.ports.selector_port import ISelectorRepositoryPort
from src.data.repository import Repository
from src.subagents.notifier_agent.agent import NotifierSubagent
from src.subagents.price_analyst_agent.agent import PriceAnalystSubagent
from src.subagents.scraper_agent.agent import ScraperSubagent
from src.tools.http_client import HttpClient


def test_scraper_subagent_implements_port():
    scraper = ScraperSubagent()
    assert isinstance(scraper, IScraper)


def test_analyst_subagent_implements_port():
    analyst = PriceAnalystSubagent()
    assert isinstance(analyst, IAnalyst)


def test_notifier_subagent_implements_port():
    notifier = NotifierSubagent()
    assert isinstance(notifier, INotifier)


def test_repository_implements_port():
    repo = Repository()
    assert isinstance(repo, IRepository)
    assert isinstance(repo, IProductManagementPort)
    assert isinstance(repo, ISelectorRepositoryPort)
    assert isinstance(repo, ICouponRepositoryPort)


def test_http_client_implements_port():
    client = HttpClient()
    assert isinstance(client, IHttpClient)

