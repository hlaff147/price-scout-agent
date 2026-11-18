#!/usr/bin/env python3
"""CLI de Rastreamento Black Friday — Monitores 27" Ergonômicos (sobre motor unificado)."""

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
from src.reporting.monitors_dashboard_generator import (
    MonitorsDashboardGenerator,
)

MONITORS_SPEC = CategoryTrackerSpec(
    category_key="monitors_27",
    cli_description='Rastreador Incremental Black Friday — Monitores 27" com Ajuste de Altura',
    banner_title='MONITORES 27"',
    banner_icon="🖥️",
    item_noun_singular="Monitor",
    item_noun_plural="Monitores verificados:",
    default_config_path="src/config/monitors_27.yaml",
    output_html_path="reports/monitores_27_black_friday.html",
    output_md_path="reports/monitors_27_history_summary.md",
    dashboard_cls=MonitorsDashboardGenerator,
    example_product_id="aoc-q27g4f",
)

__all__ = ["MONITORS_SPEC", "record_verified_quote"]


def main() -> int:
    return asyncio.run(run_category_tracker(MONITORS_SPEC))


if __name__ == "__main__":
    raise SystemExit(main())
