"""Execution runner for PromoRadar monitoring cycles."""

import asyncio
from typing import Any

from loguru import logger

from src.config.settings import settings
from src.orchestrator.orchestrator import Orchestrator


async def run_monitoring_cycle(
    product_id: str | None = None,
    dry_run: bool | None = None,
    config_path: str = "src/config/products.yaml",
) -> dict[str, Any]:
    """Ponto de entrada para execução de um ciclo de monitoramento."""
    is_dry_run = dry_run if dry_run is not None else settings.DRY_RUN
    logger.info(f"Iniciando PromoRadar Runner (dry_run={is_dry_run})...")

    orchestrator = Orchestrator()
    summary = await orchestrator.run_all_products(
        specific_product_id=product_id,
        dry_run=is_dry_run,
        config_path=config_path,
    )
    logger.info("Ciclo de monitoramento finalizado com sucesso.")
    return summary


def main():
    """Wrapper síncrono para CLI."""
    asyncio.run(run_monitoring_cycle())


if __name__ == "__main__":
    main()
