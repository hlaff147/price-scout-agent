"""Testes para o rastreador incremental de monitores 27" e gerador do dashboard Black Friday."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.data.database import Database
from src.data.models import PriceRecord, Product, ScrapedData, Source
from src.data.repository import Repository
from src.orchestrator.orchestrator import Orchestrator
from src.reporting.monitors_dashboard_generator import MonitorsDashboardGenerator
from src.skills.normalize_product.normalizer import NormalizeProductSkill
from src.skills.parse_kabum.parser import ParseKabumSkill
from src.subagents.price_analyst_agent.agent import PriceAnalystSubagent


def test_kabum_next_data_search_parsing():
    """Garante que o parser do KaBuM! extrai preços PIX do payload __NEXT_DATA__."""
    html = """
    <html><head>
    <script id="__NEXT_DATA__" type="application/json">
    {
      "props": {
        "pageProps": {
          "data": "{\\"catalogServer\\": {\\"data\\": [{\\"code\\": 528921, \\"name\\": \\"Monitor Gamer AOC AGON Q27G4F 27 QHD 180Hz IPS\\", \\"friendlyName\\": \\"monitor-gamer-aoc-agon-q27g4f\\", \\"priceWithDiscount\\": 1149.90, \\"price\\": 1352.82, \\"oldPrice\\": 1499.90, \\"available\\": true}]}}"
        }
      }
    }
    </script>
    </head><body></body></html>
    """
    parser = ParseKabumSkill()
    res = parser.execute(
        html=html,
        url="https://www.kabum.com.br/busca/q27g4f",
        keywords=["Q27G4F", "AOC Q27G4F"],
    )
    assert res.success is True
    assert res.marketplace == "kabum"
    assert res.preco == 1149.90
    assert res.preco_original == 1499.90
    assert "528921" in res.url


def test_monitor_title_with_cable_included_not_rejected_while_accessories_are():
    """Garante que monitores com 'cabo incluso' passam, mas fontes/suportes são filtrados."""
    keywords = ["XG27ACS", "ASUS XG27ACS"]
    valid_monitor = "Monitor Gamer ASUS ROG Strix XG27ACS 27 QHD 180Hz Acompanha Cabo DP"
    power_brick = "Fonte Carregador Para Monitor ASUS ROG Strix XG27ACS 19V"
    vesa_mount = "Suporte Articulado Para Monitor ASUS XG27ACS 27 Polegadas"

    assert NormalizeProductSkill.matches_keywords(valid_monitor, keywords) is True
    assert NormalizeProductSkill.matches_keywords(power_brick, keywords) is False
    assert NormalizeProductSkill.matches_keywords(vesa_mount, keywords) is False


@pytest.mark.asyncio
async def test_analyst_does_not_persist_implausibly_cheap_accessory():
    """Evita que peças baratas (< 30% do preço alvo) contaminem a mínima histórica no SQLite."""
    db = Database(":memory:")
    repo = Repository(db)
    product = Product(
        id="lg-27gs75q",
        nome="LG UltraGear 27GS75Q-B",
        keywords=["27GS75Q"],
        preco_alvo=1350.0,
        preco_maximo=2076.0,
    )
    repo.upsert_product(product)
    source = repo.upsert_source(
        Source(product_id=product.id, marketplace="mercadolivre", url_produto="https://ml.com")
    )

    analyst = PriceAnalystSubagent(repository=repo)
    cheap_part = ScrapedData(
        marketplace="mercadolivre",
        success=True,
        titulo="LG UltraGear 27GS75Q-B Kit Parafusos VESA",
        preco=49.90,
        url="https://ml.com/parafusos",
    )
    analyses = await analyst.run(product, [(source, cheap_part)])
    assert len(analyses) == 1
    assert analyses[0].is_deal is False
    # Não deve ter sido salvo como mínima histórica no banco
    assert repo.get_historical_min_price(product.id) is None


def test_incremental_monitors_dashboard_generation(tmp_path: Path):
    """Testa a acumulação incremental de múltiplos ciclos de 6h no dashboard unificado."""
    db = Database(":memory:")
    repo = Repository(db)
    orch = Orchestrator(repository=repo)
    products = orch.load_products_from_yaml("src/config/monitors_27.yaml")
    assert len(products) == 13

    aoc_sources = repo.get_sources_for_product("aoc-q27g4f")
    kabum_src = next(s for s in aoc_sources if s.marketplace == "kabum")

    t1 = datetime.now(timezone.utc) - timedelta(hours=12)
    t2 = datetime.now(timezone.utc) - timedelta(hours=6)
    t3 = datetime.now(timezone.utc)

    repo.save_price_record(
        PriceRecord(source_id=kabum_src.id, preco=1249.90, coletado_em=t1, url_encontrada="https://kabum.com/1")
    )
    repo.save_price_record(
        PriceRecord(source_id=kabum_src.id, preco=1179.90, coletado_em=t2, url_encontrada="https://kabum.com/1")
    )
    repo.save_price_record(
        PriceRecord(source_id=kabum_src.id, preco=1089.00, coletado_em=t3, url_encontrada="https://kabum.com/1")
    )

    cycles_log = tmp_path / "cycles.jsonl"
    out_html = tmp_path / "monitores_27_black_friday.html"
    out_md = tmp_path / "monitors_27_history_summary.md"

    gen = MonitorsDashboardGenerator(
        repository=repo,
        config_path="src/config/monitors_27.yaml",
        cycles_log_path=cycles_log,
    )
    gen.record_cycle_log({
        "cycles": [{"product_id": "aoc-q27g4f", "sources_checked": 4, "prices_collected": 1, "deals_found": 1}]
    })
    generated_path = gen.generate(output_html_path=out_html, output_md_path=out_md, open_browser=False)

    assert generated_path.exists()
    html_text = generated_path.read_text(encoding="utf-8")
    assert "AOC AGON QUAD Q27G4F" in html_text
    assert "chartHistory" in html_text
    assert "chartPriceHz" in html_text
    assert "chartPPI" in html_text
    assert "1.089,00" in html_text
    assert "<svg" not in html_text.lower()

    md_text = out_md.read_text(encoding="utf-8")
    assert "ABAIXO DO ALVO" in md_text
    assert "R$ 1.089,00" in md_text
