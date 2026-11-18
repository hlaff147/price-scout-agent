#!/usr/bin/env python3
"""CLI de Rastreamento Black Friday — Smartphones 512 GB (sobre motor unificado)."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
venv_python = PROJECT_ROOT / ".venv" / "bin" / "python"
if venv_python.exists() and Path(sys.executable).resolve() != venv_python.resolve():
    os.execv(str(venv_python), [str(venv_python), *sys.argv])

os.chdir(PROJECT_ROOT)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.orchestrator.category_tracker import (
    CategoryTrackerSpec,
    record_verified_quote,
    run_category_tracker,
)
from src.reporting.smartphones_dashboard_generator import (
    SmartphonesDashboardGenerator,
)

SMARTPHONES_SPEC = CategoryTrackerSpec(
    category_key="smartphones_512",
    cli_description="Rastreador Incremental Black Friday — Smartphones 512 GB (Custo × Benefício)",
    banner_title="SMARTPHONES 512 GB",
    banner_icon="📱",
    item_noun_singular="Smartphone",
    item_noun_plural="Aparelhos verificados:",
    default_config_path="src/config/smartphones_512.yaml",
    output_html_path="reports/celulares_512gb_black_friday.html",
    output_md_path="reports/celulares_512gb_summary.md",
    dashboard_cls=SmartphonesDashboardGenerator,
    example_product_id="moto-edge-50-ultra-512",
)

__all__ = ["SMARTPHONES_SPEC", "record_verified_quote"]


def main() -> int:
    return asyncio.run(run_category_tracker(SMARTPHONES_SPEC))


if __name__ == "__main__":
    raise SystemExit(main())
