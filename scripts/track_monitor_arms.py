#!/usr/bin/env python3
"""CLI de Rastreamento Black Friday — Suportes Articulados para Monitores (sobre motor unificado)."""

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
from src.reporting.monitor_arms_dashboard_generator import (
    MonitorArmsDashboardGenerator,
)

MONITOR_ARMS_SPEC = CategoryTrackerSpec(
    category_key="monitor_arms",
    cli_description="Rastreador Incremental Black Friday — Suportes Articulados para Monitores (Mesa 5 cm)",
    banner_title="SUPORTES DE MONITOR",
    banner_icon="🦾",
    item_noun_singular="Suporte",
    item_noun_plural="Suportes verificados:",
    default_config_path="src/config/monitor_arms.yaml",
    output_html_path="reports/suportes_monitor_black_friday.html",
    output_md_path="reports/monitor_arms_summary.md",
    dashboard_cls=MonitorArmsDashboardGenerator,
    example_product_id="elg-f80n",
)

__all__ = ["MONITOR_ARMS_SPEC", "record_verified_quote"]


def main() -> int:
    return asyncio.run(run_category_tracker(MONITOR_ARMS_SPEC))


if __name__ == "__main__":
    raise SystemExit(main())
