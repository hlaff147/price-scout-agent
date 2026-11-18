"""Regression and security boundary test suite covering P-03 through P-18."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import respx

from src.adapters.telegram_bot.bot_service import TelegramBotService
from src.agents.adk_runner import AdkMonitoringRunner
from src.config.settings import settings
from src.core.domain import (
    extract_storage_capacities_gb,
    parse_brl_money,
    redact_secrets,
    safe_json_for_html_script,
    validate_external_http_url,
)
from src.core.models import (
    Coupon,
    DealAnalysis,
    PriceRecord,
    PriorityLevel,
    Product,
    ScrapedData,
    Source,
)
from src.core.ports.scraper_port import IScraper
from src.data.database import Database
from src.data.repository import Repository
from src.orchestrator.orchestrator import Orchestrator
from src.reporting.monitor_arms_dashboard_generator import MonitorArmsDashboardGenerator
from src.reporting.monitors_dashboard_generator import MonitorsDashboardGenerator
from src.skills.format_alert.formatter import FormatAlertSkill
from src.skills.parse_coupon.parser import ParseCouponSkill
from src.skills.parse_kabum.parser import ParseKabumSkill
from src.skills.parse_mercadolivre.parser import ParseMercadoLivreSkill
from src.subagents.healing_agent.agent import GeminiHealerSubagent
from src.subagents.matcher.hybrid_matcher import HybridProductMatcher
from src.subagents.notifier_agent.agent import NotifierSubagent
from src.subagents.price_analyst_agent.agent import PriceAnalystSubagent
from src.subagents.scraper_agent.extractor import extract_with_overrides
from src.subagents.scraper_agent.http_adapter import HttpScraperSubagent
from src.tools.http_client import HttpClient
from src.tools.notification_tools import send_telegram_notification


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("R$ 2.499", 2499.0),
        ("R$ 3.000", 3000.0),
        ("R$ 10.499", 10499.0),
        ("R$ 1.299,90", 1299.90),
        ("1,450.00", 1450.0),
        ("1,450", 1450.0),
        ("849,99", 849.99),
        ("849.90", 849.90),
        ("R$ 0,00", None),
        ("-R$ 50,00", None),
        ("Indisponível", None),
    ],
)
def test_p03_brl_thousands_without_cents_never_truncates(raw: str, expected: float | None):
    """Regressão P-03: preços inteiros em milhar ('R$ 2.499') nunca são truncados para 2.49."""
    assert parse_brl_money(raw) == expected


@pytest.mark.asyncio
async def test_p04_notifier_never_uses_source_id_as_price_record_fk_and_arms_antispam():
    """Regressão P-04: `alerts.price_record_id` nunca recebe `source_id` e mantém o anti-spam ativo."""
    db = Database(":memory:")
    repo = Repository(db)
    prod = Product(id="prod-1", nome="Monitor Teste", preco_alvo=1000.0, preco_maximo=1400.0)
    repo.upsert_product(prod)

    deal = DealAnalysis(
        product_id=prod.id,
        source_id=9999,  # Não existe em price_records!
        price_record_id=None,
        marketplace="amazon",
        preco_atual=950.0,
        is_below_target=True,
        is_deal=True,
        motivo_alerta="abaixo_do_alvo",
        justificativa="Atingiu alvo",
        url="https://www.amazon.com.br/dp/B0TEST",
    )

    notifier = NotifierSubagent(repository=repo)
    with patch.object(settings, "TELEGRAM_BOT_TOKEN", None):
        first_sent = await notifier.run(deal, prod, dry_run=False)
        second_sent = await notifier.run(deal, prod, dry_run=False)

    assert first_sent is True
    assert second_sent is False  # Suprimido pela janela anti-spam de 6h!
    alerts = repo.get_recent_alerts(prod.id)
    assert len(alerts) == 1
    assert alerts[0].price_record_id is None


@pytest.mark.asyncio
async def test_p05_xss_escaped_in_dashboards_and_telegram_html(tmp_path: Path):
    """Regressão P-05: payloads `</script>` e caracteres `<`/`&` são escapados nas fronteiras."""
    malicious = "</script><script>window.__pwned=1;</script>"
    safe_script = safe_json_for_html_script({"title": malicious})
    assert "</script>" not in safe_script
    assert "\\u003c/script\\u003e" in safe_script

    db = Database(":memory:")
    repo = Repository(db)
    orch = Orchestrator(repository=repo)
    orch.load_products_from_yaml("src/config/monitors_27.yaml")
    orch.load_products_from_yaml("src/config/monitor_arms.yaml")

    mon_src = repo.get_sources_for_product("aoc-q27g4f")[0]
    repo.save_price_record(
        PriceRecord(
            source_id=mon_src.id or 1,
            preco=1199.0,
            titulo_coletado=f"Monitor AOC {malicious}",
            url_encontrada="https://www.kabum.com.br/produto/1?a=1&b=2",
        )
    )
    mon_html = tmp_path / "mon.html"
    MonitorsDashboardGenerator(repo, cycles_log_path=tmp_path / "m.jsonl").generate(
        output_html_path=mon_html, output_md_path=tmp_path / "m.md"
    )
    assert "<script>window.__pwned=1;</script>" not in mon_html.read_text(encoding="utf-8")

    arm_src = repo.get_sources_for_product("elg-f80n")[0]
    repo.save_price_record(
        PriceRecord(
            source_id=arm_src.id or 2,
            preco=149.0,
            titulo_coletado=f"Suporte ELG {malicious}",
            url_encontrada="https://www.amazon.com.br/dp/1?x=1&y=2",
        )
    )
    arm_html = tmp_path / "arm.html"
    MonitorArmsDashboardGenerator(repo, cycles_log_path=tmp_path / "a.jsonl").generate(
        output_html_path=arm_html, output_md_path=tmp_path / "a.md"
    )
    assert "<script>window.__pwned=1;</script>" not in arm_html.read_text(encoding="utf-8")

    # Formatação HTML do Telegram
    prod = Product(id="p<1>", nome="Monitor 27 <HDR & QHD>", preco_alvo=1000, preco_maximo=1500)
    deal = DealAnalysis(
        product_id=prod.id,
        source_id=1,
        marketplace="amazon",
        preco_atual=990.0,
        is_below_target=True,
        is_deal=True,
        cupom="USE <CUPOM10> & GANHE",
        justificativa="Queda <brusca> & validada",
        url="https://www.amazon.com.br/dp/B01?tag=a&ref=b",
    )
    tg_msg = FormatAlertSkill.format_telegram_message(deal, prod)
    assert "&lt;HDR &amp; QHD&gt;" in tg_msg
    assert "&lt;CUPOM10&gt; &amp; GANHE" in tg_msg
    assert "tag=a&amp;ref=b" in tg_msg

    with patch.object(settings, "TELEGRAM_CHAT_ID", "123"):
        bot = TelegramBotService(repository=repo)
        bad_prio = await bot.handle_command("123", "/priority elg-f80n <img/onerror=1>")
        assert "<img" not in bad_prio
        assert "&lt;img/onerror=1&gt;" in bad_prio


@respx.mock
@pytest.mark.asyncio
async def test_p06_telegram_token_redacted_on_network_errors():
    """Regressão P-06: falhas de rede em `httpx` nunca expõem `TELEGRAM_BOT_TOKEN`."""
    secret_tok = "999888777:AAH_SUPER_SECRET_BOT_TOKEN_XYZ"
    url = f"https://api.telegram.org/bot{secret_tok}/sendMessage"
    respx.post(url).mock(
        side_effect=httpx.ConnectError(f"DNS lookup failed for {url}")
    )

    with (
        patch.object(settings, "TELEGRAM_BOT_TOKEN", secret_tok),
        patch.object(settings, "TELEGRAM_CHAT_ID", "12345"),
    ):
        res = await send_telegram_notification("Teste")

    assert res["sent"] is False
    assert secret_tok not in str(res)
    assert "***REDACTED***" in res["error"]
    assert secret_tok not in redact_secrets(f"GET {url} failed", secret_tok)


def test_p07_yaml_sync_preserves_telegram_pause_and_priority(tmp_path: Path):
    """Regressão P-07: `load_products_from_yaml` não sobrescreve `/pause` nem `/priority`."""
    yaml_file = tmp_path / "catalog.yaml"
    yaml_file.write_text(
        """
products:
  - id: "fone-1"
    nome: "Fone Original"
    keywords: ["Fone Original"]
    preco_alvo: 500.0
    preco_maximo: 700.0
    prioridade: "medium"
    ativo: true
    sources:
      - marketplace: "amazon"
        url_produto: "https://www.amazon.com.br/dp/B01"
        ativo: true
""",
        encoding="utf-8",
    )

    db = Database(":memory:")
    repo = Repository(db)
    orch = Orchestrator(repository=repo)
    orch.load_products_from_yaml(str(yaml_file))

    # Usuário altera prioridade para HIGH e pausa o produto via Telegram Bot
    assert repo.set_product_priority("fone-1", PriorityLevel.HIGH) is True
    assert repo.set_product_active("fone-1", False) is True

    # Próximo ciclo recarrega o YAML (onde ativo=true e prioridade=medium)
    orch.load_products_from_yaml(str(yaml_file))

    after = repo.get_product("fone-1")
    assert after is not None
    assert after.ativo is False
    assert after.prioridade == PriorityLevel.HIGH


def test_p08_search_listing_with_h1_does_not_bypass_keyword_filtering():
    """Regressão P-08: páginas de busca com `<h1>` não são tratadas como PDP de item único."""
    ml_search_html = """
    <html><body>
      <h1 class="ui-search-breadcrumb__title andes-typography">Poco X7 Pro 512gb</h1>
      <ol class="ui-search-layout">
        <li class="ui-search-layout__item">
          <h2 class="poly-component__title">Capa Capinha Silicone Para Poco X7 Pro</h2>
          <div class="andes-money-amount--cents-superscript">
            <span class="andes-money-amount__fraction">29</span>
            <span class="andes-money-amount__cents">90</span>
          </div>
          <a class="ui-search-link" href="https://produto.mercadolivre.com.br/capa">Ver</a>
        </li>
        <li class="ui-search-layout__item">
          <h2 class="poly-component__title">Smartphone Xiaomi Poco X7 Pro 5G 512GB 12GB RAM</h2>
          <div class="poly-price__current">
            <span class="andes-money-amount__fraction">2.299</span>
          </div>
          <a class="ui-search-link" href="https://produto.mercadolivre.com.br/poco">Ver</a>
        </li>
      </ol>
    </body></html>
    """
    res = ParseMercadoLivreSkill().execute(
        html=ml_search_html,
        url="https://lista.mercadolivre.com.br/poco-x7-pro-512gb",
        keywords=["Poco X7 Pro 512GB"],
    )
    assert res.success is True
    assert res.preco == 2299.0  # Também valida P-03 ("2.299" sem centavos -> 2299.0!)
    assert "Smartphone" in (res.titulo or "")

    kabum_search_html = """
    <html><body>
      <h1>Resultados para Monitor AOC Q27G4F</h1>
      <article class="productCard">
        <span class="nameCard">Cabo DisplayPort Para Monitor AOC Q27G4F</span>
        <span class="priceCard">R$ 39,90</span>
        <a href="/produto/1">Link</a>
      </article>
      <article class="productCard">
        <span class="nameCard">Monitor Gamer AOC Q27G4F 27 QHD 180Hz</span>
        <span class="priceCard">R$ 1.199</span>
        <a href="/produto/2">Link</a>
      </article>
    </body></html>
    """
    k_res = ParseKabumSkill().execute(
        html=kabum_search_html,
        url="https://www.kabum.com.br/busca/q27g4f",
        keywords=["AOC Q27G4F"],
    )
    assert k_res.success is True
    assert k_res.preco == 1199.0


@pytest.mark.asyncio
async def test_p09_empty_title_rejected_and_tb_vs_gb_normalized():
    """Regressão P-09: título vazio nunca é aceito e '1TB' é distinguido de '1GB'."""
    assert extract_storage_capacities_gb("SSD 1TB NVMe") == [1024]
    assert extract_storage_capacities_gb("Smartphone 12/256 Preto") == [256]

    db = Database(":memory:")
    repo = Repository(db)
    prod = Product(
        id="ssd-1tb",
        nome="SSD Kingston 1TB",
        keywords=["Kingston 1TB"],
        preco_alvo=400.0,
        preco_maximo=600.0,
    )
    repo.upsert_product(prod)
    src = repo.upsert_source(
        Source(product_id=prod.id, marketplace="amazon", url_produto="https://www.amazon.com.br/s?k=ssd")
    )

    analyst = PriceAnalystSubagent(repository=repo)
    empty_scraped = ScrapedData(
        marketplace="amazon",
        success=True,
        titulo=None,
        preco=380.0,
        url="https://www.amazon.com.br/dp/B0EMPTY",
    )
    analyses = await analyst.run(prod, [(src, empty_scraped)])
    assert analyses[0].is_deal is False
    assert repo.get_historical_min_price(prod.id) is None

    matcher = HybridProductMatcher()
    bad_unit = await matcher.match(prod, "Pen Drive Kingston 1GB Antigo")
    assert bad_unit.is_match is False
    assert 0.0 <= bad_unit.match_probability <= 0.1


@pytest.mark.asyncio
async def test_p10_p11_healer_guards_intraday_circuit_breaker_and_auto_rollback():
    """Regressão P-10 e P-11: sintaxe CSS inválida, filtro de keywords, rollback após 3 falhas e CB intra-dia."""
    db = Database(":memory:")
    repo = Repository(db)
    prod = Product(
        id="mon-dell",
        nome="Monitor Dell 27 QHD",
        keywords=["Monitor Dell 27"],
        preco_alvo=1500.0,
        preco_maximo=2200.0,
    )

    # Seletores CSS malformados nunca quebram com SelectorSyntaxError
    bad_overrides = {"container": "div[unclosed", "titulo": "h2", "preco": "span"}
    assert extract_with_overrides("<div><h2>Monitor Dell 27</h2><span>1500</span></div>", bad_overrides, "https://kabum.com.br", "kabum") is None

    # LLM retornando chaves extras ou sintaxe CSS inválida é bloqueada
    async def malicious_llm(*_args, **_kwargs):
        return {
            "container": "div.card",
            "titulo": "h2[broken",
            "preco": "span.p",
            "injected_field": "evil",
        }

    healer = GeminiHealerSubagent(repository=repo, llm_client=malicious_llm)
    res = await healer.heal("kabum", prod, "<div class='card'><h2>Monitor Dell 27</h2><span class='p'>R$ 1.600</span></div>", {})
    assert res.healed is False

    # 2ª tentativa atinge o Circuit Breaker MESMO em janela intra-dia de 1 hora (P-11)!
    repo.record_healing_attempt("kabum")
    assert repo.has_exceeded_healing_attempts("kabum", max_attempts=2, hours=1) is True
    assert repo.has_exceeded_healing_attempts("kabum", max_attempts=2, hours=6) is True

    # Auto-rollback de override após 3 falhas consecutivas
    from src.core.models import SelectorOverride

    repo.save_override(
        SelectorOverride(
            marketplace="shopee",
            target_field="titulo",
            original_selector="h1",
            healed_selector="h2.new",
        )
    )
    repo.save_override(
        SelectorOverride(
            marketplace="shopee",
            target_field="preco",
            original_selector=".old",
            healed_selector=".new-p",
        )
    )
    assert len(repo.get_active_overrides("shopee")) == 2

    class BrokenPageClient:
        async def fetch(self, url: str) -> str:
            return "<html><body><div>Layout mudou de novo</div></body></html>"

    scraper = HttpScraperSubagent(client=BrokenPageClient(), selector_repo=repo)
    src = Source(product_id=prod.id, marketplace="shopee", url_produto="https://shopee.com.br/item")
    for _ in range(3):
        await scraper.run(src, prod)

    assert repo.get_active_overrides("shopee") == {}


@pytest.mark.asyncio
async def test_p12_adk_runner_isolated_repository_and_zero_session_leak(tmp_path: Path):
    """Regressão P-12 e P-15: `AdkMonitoringRunner` usa exclusivamente o repo injetado e limpa sessões."""
    yaml_path = tmp_path / "p.yaml"
    yaml_path.write_text(
        """
products:
  - id: "iso-prod"
    nome: "Produto Isolado"
    keywords: ["Produto Isolado"]
    preco_alvo: 500.0
    preco_maximo: 700.0
    sources:
      - marketplace: "amazon"
        url_produto: "https://www.amazon.com.br/dp/B0ISO"
""",
        encoding="utf-8",
    )

    isolated_db = Database(":memory:")
    isolated_repo = Repository(isolated_db)

    other_db_path = tmp_path / "should_not_be_written.db"

    class StaticScraper(IScraper):
        async def run(self, source: Source, product: Product) -> ScrapedData:
            return ScrapedData(
                marketplace=source.marketplace,
                success=True,
                titulo="Produto Isolado Original",
                preco=450.0,
                url=source.url_produto,
            )

    with (
        patch.object(settings, "DATABASE_PATH", str(other_db_path)),
        patch.object(settings, "TELEGRAM_BOT_TOKEN", None),
    ):
        runner = AdkMonitoringRunner(repository=isolated_repo, scraper=StaticScraper())
        summary = await runner.run_cycle(
            dry_run=False,
            generate_report=False,
            open_browser=False,
            config_path=str(yaml_path),
        )

    assert summary["total_products"] == 1
    assert summary["cycles"][0]["deals_found"] == 1
    assert isolated_repo.get_historical_min_price("iso-prod") == 450.0
    assert len(isolated_repo.get_recent_alerts("iso-prod")) == 1
    assert not other_db_path.exists()
    assert all(
        len(sess_map) == 0
        for users in runner.session_service.sessions.values()
        for sess_map in users.values()
    )


@pytest.mark.asyncio
async def test_p13_coupon_rejects_installments_and_fake_discount_blocks_trivial_coupon():
    """Regressão P-13: parcelas não viram cupons e 'metade do dobro' bloqueia falso deal de cupom."""
    assert ParseCouponSkill.parse("Em até 12x de R$ 249,90 sem juros", "amazon") is None

    min_spend_coupon = ParseCouponSkill.parse(
        "Nas compras acima de R$ 500 ganhe 10% OFF com cupom LOJA10",
        "mercadolivre",
    )
    assert min_spend_coupon is not None
    assert min_spend_coupon.codigo == "LOJA10"
    assert min_spend_coupon.desconto_percentual == 10.0
    assert min_spend_coupon.desconto_fixo is None
    assert min_spend_coupon.preco_minimo == 500.0

    db = Database(":memory:")
    repo = Repository(db)
    prod = Product(
        id="watch-x",
        nome="Smartwatch X",
        keywords=["Smartwatch X"],
        preco_alvo=800.0,
        preco_maximo=1100.0,
    )
    repo.upsert_product(prod)
    src = repo.upsert_source(
        Source(product_id=prod.id, marketplace="amazon", url_produto="https://www.amazon.com.br/dp/B0W")
    )
    repo.save_price_record(PriceRecord(source_id=src.id or 1, preco=1000.0))

    analyst = PriceAnalystSubagent(repository=repo)
    # Preço inflado "De R$ 2.500 por R$ 1.050" com cupom pequeno de 5% (preço efetivo 997.50 > alvo 800)
    scraped = ScrapedData(
        marketplace="amazon",
        success=True,
        titulo="Smartwatch X Bluetooth",
        preco=1050.0,
        preco_original=2500.0,
        cupom="5% OFF com cupom FAKE5",
        url="https://www.amazon.com.br/dp/B0W",
    )
    analyses = await analyst.run(prod, [(src, scraped)])
    assert analyses[0].is_fake_discount is True
    assert analyses[0].is_deal is False

    # Verifica também Coupon com HTML no FormatAlertSkill
    c = Coupon(marketplace="amazon", codigo="A&B", descricao="R$ 50 <OFF>")
    assert "&amp;" in FormatAlertSkill.format_coupon_message(c)


@pytest.mark.asyncio
async def test_p18_anti_ssrf_blocks_internal_and_non_http_urls():
    """Regressão P-18: bloqueia esquemas `file://`, loopback e IPs privados/metadados."""
    for blocked in (
        "file:///etc/passwd",
        "ftp://example.com/file",
        "http://localhost:8000/admin",
        "http://127.0.0.1:9222/json",
        "http://169.254.169.254/latest/meta-data/",
        "http://192.168.1.10/secret",
    ):
        with pytest.raises(ValueError):
            validate_external_http_url(blocked, allow_private=False)

    client = HttpClient()
    with pytest.raises(ValueError):
        await client.fetch("http://127.0.0.1:8080/internal")
