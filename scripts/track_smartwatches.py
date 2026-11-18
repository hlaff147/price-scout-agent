#!/usr/bin/env python3
"""CLI de Rastreamento Black Friday — Smartwatches R$ 800 a R$ 1.200 (sobre motor unificado)."""

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
from src.reporting.smartwatches_dashboard_generator import (
    SmartwatchesDashboardGenerator,
)

SMARTWATCHES_SPEC = CategoryTrackerSpec(
    category_key="smartwatches",
    cli_description="Rastreador Incremental Black Friday — Smartwatches (R$ 800 - R$ 1.200 Custo × Benefício)",
    banner_title="SMARTWATCHES R$ 800 - R$ 1.200",
    banner_icon="⌚",
    item_noun_singular="Smartwatch",
    item_noun_plural="Relógios verificados:",
    default_config_path="src/config/smartwatches_800_1200.yaml",
    output_html_path="reports/smartwatches_black_friday.html",
    output_md_path="reports/smartwatches_summary.md",
    dashboard_cls=SmartwatchesDashboardGenerator,
    example_product_id="huawei-gt-runner-2",
)

__all__ = ["SMARTWATCHES_SPEC", "record_verified_quote"]


def main() -> int:
    return asyncio.run(run_category_tracker(SMARTWATCHES_SPEC))


if __name__ == "__main__":
    raise SystemExit(main())
