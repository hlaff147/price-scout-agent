"""Testes para o rastreador e gerador de dashboard de Smartwatches (Black Friday R$ 800 - R$ 1.200)."""

from pathlib import Path

import pytest

from src.data.database import Database
from src.data.models import PriceRecord, Product, Source
from src.data.repository import Repository
from src.orchestrator.orchestrator import Orchestrator
from src.reporting.smartwatches_dashboard_generator import (
    SmartwatchesDashboardGenerator,
    compute_smartwatch_benefit_score,
)
from src.skills.normalize_product.normalizer import NormalizeProductSkill
from src.subagents.matcher.hybrid_matcher import HybridProductMatcher


def test_smartwatch_keyword_matching_and_exclusions():
    """Valida o casamento de palavras-chave dos smartwatches e a rejeição estrita de pulseiras e acessórios."""
    # HUAWEI WATCH GT Runner 2
    assert NormalizeProductSkill.matches_keywords(
        "Smartwatch HUAWEI WATCH GT Runner 2 GPS Banda Dupla Titânio Preto",
        ["HUAWEI WATCH GT Runner 2", "Huawei GT Runner 2"],
    ) is True

    # Rejeitar pulseira / pulseiras de silicone ou tecido
    assert NormalizeProductSkill.matches_keywords(
        "Pulseira de Silicone 22mm para Smartwatch Huawei Watch GT Runner 2",
        ["HUAWEI WATCH GT Runner 2"],
    ) is False
    assert NormalizeProductSkill.matches_keywords(
        "Bracelete Metal Aço Inox Compatível com Huawei Watch GT Runner 2",
        ["HUAWEI WATCH GT Runner 2"],
    ) is False
    assert NormalizeProductSkill.matches_keywords(
        "Cabo Carregador Para Smartwatch Huawei Watch GT Runner 2",
        ["HUAWEI WATCH GT Runner 2"],
    ) is False

    # Galaxy Watch 7 40mm vs 44mm vs Ultra
    gw7_40_kw = ["Galaxy Watch 7 40mm -44mm -ultra -fe -pro"]
    assert NormalizeProductSkill.matches_keywords(
        "Smartwatch Samsung Galaxy Watch 7 40mm Bluetooth Prata",
        gw7_40_kw,
    ) is True
    assert NormalizeProductSkill.matches_keywords(
        "Smartwatch Samsung Galaxy Watch 7 44mm Bluetooth Grafite",
        gw7_40_kw,
    ) is False
    assert NormalizeProductSkill.matches_keywords(
        "Smartwatch Samsung Galaxy Watch Ultra 47mm LTE",
        gw7_40_kw,
    ) is False

    # Amazfit Balance 2 vs Balance 1
    bal2_kw = ["Amazfit Balance 2"]
    assert NormalizeProductSkill.matches_keywords(
        "Relógio Smartwatch Amazfit Balance 2 GPS L1+L5 Sensor BioTracker 6.0",
        bal2_kw,
    ) is True
    assert NormalizeProductSkill.matches_keywords(
        "Relógio Smartwatch Amazfit Balance 1ª Geração",
        bal2_kw,
    ) is False

    # Garmin Forerunner 55
    fr55_kw = ["Garmin Forerunner 55 -255 -265 -165 -955 -965"]
    assert NormalizeProductSkill.matches_keywords(
        "Relógio Monitor Cardíaco Garmin Forerunner 55 GPS Preto",
        fr55_kw,
    ) is True
    assert NormalizeProductSkill.matches_keywords(
        "Relógio GPS Garmin Forerunner 255 Music",
        fr55_kw,
    ) is False


@pytest.mark.asyncio
async def test_hybrid_matcher_smartwatch_distinction():
    """Garante que o HybridProductMatcher identifica o HUAWEI WATCH GT Runner 2 e rejeita versões antigas."""
    matcher = HybridProductMatcher()
    product = Product(
        id="huawei-gt-runner-2",
        nome="HUAWEI WATCH GT Runner 2",
        keywords=["HUAWEI WATCH GT Runner 2", "Huawei GT Runner 2"],
        preco_alvo=1199.0,
        preco_maximo=1499.0,
    )

    ok_res = await matcher.match(
        target=product,
        candidate_title="Relógio Inteligente Huawei Watch GT Runner 2 GPS L1+L5 Titânio Preto",
    )
    assert ok_res.is_match is True

    # Rejeitar acessório
    acc_res = await matcher.match(
        target=product,
        candidate_title="Pulseira Milanese Loop Compatível com Huawei Watch GT Runner 2",
    )
    assert acc_res.is_match is False


def test_smartwatch_benefit_score_breakdown():
    """Valida o cálculo do Índice de Benefício Vestível (0–100) e ponderação por pilar."""
    runner2_specs = {
        "scores": {
            "gps_running": 9.8,      # 9.8 * 3.0 = 29.4
            "health_sensors": 9.2,   # 9.2 * 2.0 = 18.4
            "battery": 9.3,          # 9.3 * 2.0 = 18.6
            "build_ergonomics": 9.5, # 9.5 * 1.5 = 14.25 -> 14.2
            "ecosystem_smart": 8.0,  # 8.0 * 1.5 = 12.0
        }
    }
    score = compute_smartwatch_benefit_score(runner2_specs)
    assert 90.0 <= score["total"] <= 96.0
    assert score["gps_corrida"] == 29.4
    assert score["sensores_saude"] == 18.4
    assert score["bateria_autonomia"] == 18.6
    assert score["construcao_ergonomia"] == 14.2
    assert score["ecossistema_smart"] == 12.0

    # Modelo básico de entrada
    basic_specs = {
        "scores": {
            "gps_running": 7.0,
            "health_sensors": 6.8,
            "battery": 8.0,
            "build_ergonomics": 6.5,
            "ecosystem_smart": 6.5,
        }
    }
    basic_score = compute_smartwatch_benefit_score(basic_specs)
    assert 65.0 <= basic_score["total"] <= 75.0


def test_smartwatches_dashboard_generation(tmp_path: Path):
    """Valida a compilação completa do catálogo de 11 smartwatches e geração do HTML/Markdown."""
    db = Database(":memory:")
    repo = Repository(db)
    orch = Orchestrator(repository=repo)
    products = orch.load_products_from_yaml("src/config/smartwatches_800_1200.yaml")
    assert len(products) == 11

    # Inserir cotações de teste
    sources_runner = repo.get_sources_for_product("huawei-gt-runner-2")
    assert sources_runner
    repo.save_price_record(
        PriceRecord(
            source_id=sources_runner[0].id or 1,
            preco=1099.00,
            preco_original=1699.00,
            titulo_coletado="Smartwatch Huawei Watch GT Runner 2 GPS Banda Dupla Titânio",
            url_encontrada="https://www.amazon.com.br/dp/B0RUNNER2",
        )
    )

    sources_balance = repo.get_sources_for_product("amazfit-balance-1")
    assert sources_balance
    repo.save_price_record(
        PriceRecord(
            source_id=sources_balance[0].id or 2,
            preco=859.90,
            preco_original=1399.00,
            titulo_coletado="Smartwatch Amazfit Balance Midnight Preto Bioimpedância",
            url_encontrada="https://www.kabum.com.br/produto/AMZBAL1",
        )
    )

    gen = SmartwatchesDashboardGenerator(
        repository=repo,
        config_path="src/config/smartwatches_800_1200.yaml",
        cycles_log_path=tmp_path / "smartwatches_cycles.jsonl",
    )
    gen.record_cycle_log({
        "cycles": [
            {"product_id": p.id, "sources_checked": len(p.sources), "prices_collected": 1, "deals_found": 1}
            for p in products
        ]
    })

    out_html = tmp_path / "smartwatches_black_friday.html"
    out_md = tmp_path / "smartwatches_summary.md"
    gen.generate(output_html_path=out_html, output_md_path=out_md, open_browser=False)

    assert out_html.exists()
    assert out_md.exists()
    html_text = out_html.read_text(encoding="utf-8")
    md_text = out_md.read_text(encoding="utf-8")

    assert "HUAWEI WATCH GT Runner 2" in html_text
    assert "Amazfit Balance" in html_text
    assert "R$ 1.099,00" in html_text
    assert "chartScatterCB" in html_text
    assert "chartBattery" in html_text
    assert "chartRankingCB" in html_text
    assert "HUAWEI WATCH GT Runner 2" in md_text
    assert "R$ 1.099,00" in md_text
