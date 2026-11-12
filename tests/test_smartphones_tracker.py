"""Testes para o rastreador e gerador de dashboard de Smartphones 512 GB (Black Friday)."""

from pathlib import Path

import pytest

from src.data.database import Database
from src.data.models import PriceRecord, Product, Source
from src.data.repository import Repository
from src.orchestrator.orchestrator import Orchestrator
from src.reporting.smartphones_dashboard_generator import (
    SmartphonesDashboardGenerator,
    compute_benefit_score,
)
from src.skills.normalize_product.normalizer import NormalizeProductSkill
from src.subagents.matcher.hybrid_matcher import HybridProductMatcher


def test_smartphone_keyword_matching_512gb_and_exclusions():
    """Garante que variantes 512 GB casam com '512 GB'/'12/512GB', excluindo 256 GB, '-max', vitrine e capas."""
    assert NormalizeProductSkill.matches_keywords(
        "Smartphone Motorola Edge 50 Ultra 5G 512 GB 12GB RAM Peach Fuzz",
        ["Edge 50 Ultra 512GB"],
    ) is True

    # S25+ deve casar com S25 Plus e rejeitar S25 Ultra
    assert NormalizeProductSkill.matches_keywords(
        "Smartphone Samsung Galaxy S25 Plus 5G 512GB 12GB RAM",
        ["Galaxy S25+ 512GB -ultra -edge -fe"],
    ) is True
    assert NormalizeProductSkill.matches_keywords(
        "Smartphone Samsung Galaxy S25 Ultra 5G 512GB",
        ["Galaxy S25+ 512GB -ultra -edge -fe"],
    ) is False

    # Exclusão -max separa POCO X8 Pro de POCO X8 Pro Max
    assert NormalizeProductSkill.matches_keywords(
        "Smartphone Xiaomi POCO X8 Pro 5G 512GB 12GB RAM",
        ["POCO X8 Pro 512GB -max"],
    ) is True
    assert NormalizeProductSkill.matches_keywords(
        "Smartphone Xiaomi POCO X8 Pro Max 5G 512GB 12GB RAM",
        ["POCO X8 Pro 512GB -max"],
    ) is False

    # Rejeitar 256GB, vitrine/recondicionado e capinha
    assert NormalizeProductSkill.matches_keywords(
        "Smartphone Motorola Edge 50 Ultra 256GB",
        ["Edge 50 Ultra 512GB"],
    ) is False
    assert NormalizeProductSkill.matches_keywords(
        "Smartphone Samsung Galaxy S24 FE 512GB Vitrine Seminovo",
        ["Galaxy S24 FE 512GB"],
    ) is False
    assert NormalizeProductSkill.matches_keywords(
        "Capa Capinha Anti Impacto Para Motorola Edge 50 Ultra 512GB",
        ["Edge 50 Ultra 512GB"],
    ) is False


@pytest.mark.asyncio
async def test_hybrid_matcher_accepts_ram_plus_512gb_and_rejects_256gb():
    """Garante que títulos '12GB RAM 512GB' não falham na checagem de capacidade do HybridProductMatcher."""
    matcher = HybridProductMatcher()
    product = Product(
        id="xiaomi-14t-512",
        nome="Xiaomi 14T 512GB",
        keywords=["Xiaomi 14T 512GB -pro"],
        preco_alvo=2899.0,
        preco_maximo=3300.0,
    )

    ok_res = await matcher.match(
        target=product,
        candidate_title="Smartphone Xiaomi 14T 5G 12GB RAM 512GB Câmera Leica Preto",
    )
    assert ok_res.is_match is True

    bad_cap = await matcher.match(
        target=product,
        candidate_title="Smartphone Xiaomi 14T 5G 12GB RAM 256GB Preto",
    )
    assert bad_cap.is_match is False

    bad_pro = await matcher.match(
        target=product,
        candidate_title="Smartphone Xiaomi 14T Pro 5G 12GB RAM 512GB Preto",
    )
    assert bad_pro.is_match is False


def test_smartphones_dashboard_generation(tmp_path: Path):
    """Valida a compilação completa do catálogo de 15 celulares 512 GB e geração do HTML/Markdown."""
    db = Database(":memory:")
    repo = Repository(db)
    orch = Orchestrator(repository=repo)
    products = orch.load_products_from_yaml("src/config/smartphones_512.yaml")
    assert len(products) == 15

    # Inserir cotação ao vivo para o Motorola Edge 50 Ultra 512GB
    sources = repo.get_sources_for_product("moto-edge-50-ultra-512")
    assert sources
    repo.save_price_record(
        PriceRecord(
            source_id=sources[0].id or 1,
            preco=2489.90,
            preco_original=3299.00,
            titulo_coletado="Smartphone Motorola Edge 50 Ultra 5G 512GB 12GB RAM",
            url_encontrada="https://www.amazon.com.br/dp/B0TEST512",
        )
    )

    gen = SmartphonesDashboardGenerator(
        repository=repo,
        config_path="src/config/smartphones_512.yaml",
        cycles_log_path=tmp_path / "cycles.jsonl",
    )
    gen.record_cycle_log({
        "cycles": [{"product_id": p.id, "sources_checked": len(p.sources), "prices_collected": 1, "deals_found": 1} for p in products]
    })

    out_html = tmp_path / "celulares_512gb_black_friday.html"
    out_md = tmp_path / "celulares_512gb_summary.md"
    gen.generate(output_html_path=out_html, output_md_path=out_md, open_browser=False)

    assert out_html.exists()
    assert out_md.exists()
    html_text = out_html.read_text(encoding="utf-8")
    md_text = out_md.read_text(encoding="utf-8")
    assert "Motorola Edge 50 Ultra 512GB" in html_text
    assert "R$ 2.489,90" in html_text
    assert "chartScatterCB" in html_text
    assert "Motorola Edge 50 Ultra 512GB" in md_text

    score = compute_benefit_score({"scores": {"performance": 8.5, "camera": 9.0, "display": 9.0}, "battery_mah": 4500, "charge_w": 125, "updates_years": 4, "ip": "IP68", "ram_gb": 12, "storage_type": "UFS 4.0"})
    assert 70.0 <= score["total"] <= 95.0
