"""End-to-end and unit tests for the 4th vertical: Monitor Arms (1 & 2 screens, 5cm desk)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.track_monitor_arms import MONITOR_ARMS_SPEC
from src.core.models import PriceRecord, Product, ScrapedData, Source
from src.core.ports.scraper_port import IScraper
from src.data.database import Database
from src.data.repository import Repository
from src.orchestrator.category_tracker import run_category_tracker
from src.orchestrator.orchestrator import Orchestrator
from src.reporting.monitor_arms_dashboard_generator import (
    MonitorArmsDashboardGenerator,
    compute_arm_benefit_score,
)
from src.subagents.matcher.hybrid_matcher import HybridProductMatcher


class _MockArmScraper(IScraper):
    async def run(self, source: Source, product: Product) -> ScrapedData:
        return ScrapedData(
            marketplace=source.marketplace,
            success=True,
            titulo=f"Suporte Articulado de Mesa {product.nome.split('(')[0].strip()} Preto",
            preco=149.90,
            preco_original=199.90,
            url=source.url_produto,
        )


@pytest.mark.asyncio
async def test_monitor_arms_matcher_handles_color_alternatives_and_support_head_noun():
    """Regressão P-09: 'ELG F80N (ou F80W Branco)' e 'Zinnia Nimbo 110 V2' aceitam anúncios legítimos."""
    matcher = HybridProductMatcher()

    elg = Product(
        id="elg-f80n",
        nome="ELG F80N (ou F80W Branco)",
        keywords=["ELG F80N -duplo -f160", "Suporte ELG F80N"],
        preco_alvo=155.0,
        preco_maximo=220.0,
    )
    res_black = await matcher.match(
        elg, "Suporte Articulado de Mesa com Pistão a Gás Para Monitor ELG F80N Preto"
    )
    assert res_black.is_match is True

    res_white = await matcher.match(
        elg, "Suporte Articulado de Mesa ELG F80W Branco Pistão a Gás"
    )
    assert res_white.is_match is True

    res_dual = await matcher.match(
        elg, "Suporte Duplo Articulado ELG F160N Para 2 Monitores"
    )
    assert res_dual.is_match is False

    zinnia = Product(
        id="zinnia-nimbo-110",
        nome="Zinnia Nimbo 110 V2",
        keywords=["Zinnia Nimbo 110 -210 -200"],
        preco_alvo=119.0,
        preco_maximo=170.0,
    )
    res_zinnia = await matcher.match(
        zinnia, "Suporte Articulado de Mesa Zinnia Nimbo 110 V2 Pistão a Gás Preto"
    )
    assert res_zinnia.is_match is True


def test_monitor_arms_dashboard_generation_with_live_quotes(tmp_path: Path):
    """Regressão P-02: `MonitorArmsDashboardGenerator` compila com >= 1 cotação no SQLite."""
    db = Database(":memory:")
    repo = Repository(db)
    orch = Orchestrator(repository=repo)
    products = orch.load_products_from_yaml("src/config/monitor_arms.yaml")
    assert len(products) == 10

    sources = repo.get_sources_for_product("elg-f80n")
    assert sources
    repo.save_price_record(
        PriceRecord(
            source_id=sources[0].id or 1,
            preco=144.90,
            preco_original=189.90,
            titulo_coletado="Suporte Articulado ELG F80N Pistão a Gás Preto",
            url_encontrada="https://www.amazon.com.br/dp/B0ELGF80N",
        )
    )

    gen = MonitorArmsDashboardGenerator(
        repository=repo,
        config_path="src/config/monitor_arms.yaml",
        cycles_log_path=tmp_path / "arms_cycles.jsonl",
    )
    gen.record_cycle_log({
        "cycles": [
            {"product_id": p.id, "sources_checked": len(p.sources), "prices_collected": 1, "deals_found": 1}
            for p in products
        ]
    })

    out_html = tmp_path / "suportes_monitor_black_friday.html"
    out_md = tmp_path / "monitor_arms_summary.md"
    returned_path = gen.generate(output_html_path=out_html, output_md_path=out_md, open_browser=False)

    assert returned_path == out_html
    assert out_html.exists()
    assert out_md.exists()

    html_text = out_html.read_text(encoding="utf-8")
    md_text = out_md.read_text(encoding="utf-8")
    assert "ELG F80N" in html_text
    assert "144.9" in html_text
    assert "R$ 144,90" in md_text
    assert "Abaixo do Alvo" in md_text

    benefit = compute_arm_benefit_score({
        "scores": {
            "mechanism_durability": 9.5,
            "clamp_5cm": 9.5,
            "ergonomics_reach": 9.0,
            "load_capacity": 8.5,
            "warranty_build": 9.5,
        }
    })
    assert 90.0 <= benefit["total"] <= 95.0


@pytest.mark.asyncio
async def test_monitor_arms_cli_record_price_and_live_cycle(tmp_path: Path):
    """Regressão P-01: executa `--record-price` e ciclo completo ADK da vertical `/suportes`."""
    db = Database(":memory:")
    repo = Repository(db)

    custom_spec = MONITOR_ARMS_SPEC.__class__(
        category_key=MONITOR_ARMS_SPEC.category_key,
        cli_description=MONITOR_ARMS_SPEC.cli_description,
        banner_title=MONITOR_ARMS_SPEC.banner_title,
        banner_icon=MONITOR_ARMS_SPEC.banner_icon,
        item_noun_singular=MONITOR_ARMS_SPEC.item_noun_singular,
        item_noun_plural=MONITOR_ARMS_SPEC.item_noun_plural,
        default_config_path=MONITOR_ARMS_SPEC.default_config_path,
        output_html_path=str(tmp_path / "suportes.html"),
        output_md_path=str(tmp_path / "suportes.md"),
        dashboard_cls=lambda repository, config_path: MonitorArmsDashboardGenerator(
            repository=repository,
            config_path=config_path,
            cycles_log_path=tmp_path / "cycles.jsonl",
        ),
        example_product_id="elg-f80n",
    )

    rc1 = await run_category_tracker(
        custom_spec,
        [
            "--no-open",
            "--dry-run",
            "--record-price",
            "elg-f80n",
            "amazon",
            "148.50",
            "https://www.amazon.com.br/dp/B0ELGF80N",
            "--title",
            "Suporte Articulado ELG F80N Preto",
        ],
        repository=repo,
    )
    assert rc1 == 0
    assert repo.get_historical_min_price("elg-f80n") == 148.50

    with patch(
        "src.agents.scraper_agent.ScraperSubagent",
        return_value=_MockArmScraper(),
    ):
        rc2 = await run_category_tracker(
            custom_spec,
            ["--no-open", "--dry-run", "--product", "elg-f80n"],
            repository=repo,
        )
    assert rc2 == 0
    assert (tmp_path / "suportes.html").exists()
    assert (tmp_path / "suportes.md").exists()
