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

from src.agents.adk_runner import AdkMonitoringRunner
from src.config.settings import settings
from src.orchestrator.runner import run_monitoring_cycle
from src.reporting.report_generator import ReportGenerator


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
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Desabilita a geração do relatório HTML após o ciclo.",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Gera o relatório HTML mas não abre automaticamente no navegador.",
    )
    parser.add_argument(
        "--legacy",
        action="store_true",
        help="Utiliza o orquestrador procedural legado em vez do Google ADK.",
    )
    return parser.parse_args()


async def async_main():
    args = parse_args()

    # Configuração de logging
    logger.remove()
    log_level = "DEBUG" if args.verbose else settings.LOG_LEVEL
    logger.add(sys.stderr, level=log_level)

    dry_run = args.dry_run or settings.DRY_RUN

    if args.legacy:
        logger.info("🛰️ PromoRadar: Iniciando ciclo sob demanda (Modo Legado)...")
        summary = await run_monitoring_cycle(
            product_id=args.product,
            dry_run=dry_run,
            config_path=args.config,
        )
        report_path_str = None
        if not args.no_report:
            try:
                generator = ReportGenerator()
                report_path = generator.generate(
                    summary=summary,
                    open_browser=not args.no_open,
                )
                if report_path:
                    report_path_str = str(report_path.resolve())
            except Exception as exc:  # noqa: BLE001
                logger.error(f"Erro ao gerar relatório HTML: {exc}")
    else:
        logger.info("🤖 PromoRadar: Iniciando ciclo sob demanda com Google ADK...")
        runner = AdkMonitoringRunner()
        summary = await runner.run_cycle(
            product_id=args.product,
            dry_run=dry_run,
            generate_report=not args.no_report,
            open_browser=not args.no_open,
            config_path=args.config,
        )
        report_path_str = next(
            (c.get("report_path") for c in summary.get("cycles", []) if c.get("report_path")),
            None,
        )

    total_deals = sum(c.get("deals_found", 0) for c in summary.get("cycles", []))
    total_sources = sum(c.get("sources_checked", 0) for c in summary.get("cycles", []))
    total_prices = sum(c.get("prices_collected", 0) for c in summary.get("cycles", []))
    total_no_results = sum(c.get("no_results", 0) for c in summary.get("cycles", []))
    total_errors = sum(c.get("errors", 0) for c in summary.get("cycles", []))

    mode_label = "LEGADO" if args.legacy else "GOOGLE ADK"
    print("\n" + "=" * 60)
    print(f"📊 RESUMO DO CICLO PROMORADAR [{mode_label}]")
    print("=" * 60)
    print(f"• Produtos processados: {summary.get('total_products', 0)}")
    print(f"• Fontes consultadas:   {total_sources}")
    print(f"• Preços coletados:     {total_prices}")
    print(f"• Ofertas vantajosas:   {total_deals}")
    print(f"• Sem resultado:        {total_no_results}")
    print(f"• Erros de coleta:      {total_errors}")
    print("=" * 60)

    if report_path_str:
        print(f"\n📄 Relatório HTML: {report_path_str}")

    print()


if __name__ == "__main__":
    asyncio.run(async_main())
