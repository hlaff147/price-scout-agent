#!/usr/bin/env python3
"""Script CLI para execução manual ou cron de um ciclo do PromoRadar."""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Garante a execução dentro do .venv caso o usuário execute com o python3 global do sistema
venv_python = Path(__file__).resolve().parent.parent / ".venv" / "bin" / "python"
if venv_python.exists() and sys.executable != str(venv_python):
    os.execv(str(venv_python), [str(venv_python)] + sys.argv)

from loguru import logger

from src.config.settings import settings
from src.orchestrator.runner import run_monitoring_cycle


def parse_args():
    parser = argparse.ArgumentParser(
        description="PromoRadar - Execução de ciclo de monitoramento de ofertas."
    )
    parser.add_argument(
        "--product",
        "-p",
        type=str,
        default=None,
        help="ID do produto específico a ser monitorado (ex: 'huawei-freebuds-pro-5').",
    )
    parser.add_argument(
        "--dry-run",
        "-d",
        action="store_true",
        help="Simula o ciclo sem disparar notificações reais no Telegram.",
    )
    parser.add_argument(
        "--config",
        "-c",
        type=str,
        default="src/config/products.yaml",
        help="Caminho para o arquivo YAML de produtos.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Habilita logs detalhados de nível DEBUG.",
    )
    return parser.parse_args()


async def async_main():
    args = parse_args()

    # Configuração de logging
    logger.remove()
    log_level = "DEBUG" if args.verbose else settings.LOG_LEVEL
    logger.add(sys.stderr, level=log_level)

    dry_run = args.dry_run or settings.DRY_RUN

    logger.info("🛰️ PromoRadar: Iniciando ciclo sob demanda...")
    summary = await run_monitoring_cycle(
        product_id=args.product,
        dry_run=dry_run,
        config_path=args.config,
    )

    total_deals = sum(c.get("deals_found", 0) for c in summary.get("cycles", []))
    total_sources = sum(c.get("sources_checked", 0) for c in summary.get("cycles", []))
    total_prices = sum(c.get("prices_collected", 0) for c in summary.get("cycles", []))

    print("\n" + "=" * 60)
    print("📊 RESUMO DO CICLO PROMORADAR")
    print("=" * 60)
    print(f"• Produtos processados: {summary.get('total_products', 0)}")
    print(f"• Fontes consultadas:   {total_sources}")
    print(f"• Preços coletados:     {total_prices}")
    print(f"• Ofertas vantajosas:   {total_deals}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(async_main())
