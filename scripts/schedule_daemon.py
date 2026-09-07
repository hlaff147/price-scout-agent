#!/usr/bin/env python3
"""Daemon de monitoramento contínuo agendado com APScheduler."""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Garante a execução dentro do .venv caso o usuário execute com o python3 global do sistema
venv_python = Path(__file__).resolve().parent.parent / ".venv" / "bin" / "python"
if venv_python.exists() and sys.executable != str(venv_python):
    os.execv(str(venv_python), [str(venv_python)] + sys.argv)

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

from src.agents.adk_runner import AdkMonitoringRunner
from src.config.settings import settings
from src.orchestrator.runner import run_monitoring_cycle


def parse_args():
    parser = argparse.ArgumentParser(
        description="PromoRadar - Daemon de monitoramento agendado."
    )
    parser.add_argument(
        "--interval-hours",
        "-i",
        type=int,
        default=settings.CHECK_INTERVAL_HOURS,
        help=f"Intervalo em horas entre ciclos (padrão: {settings.CHECK_INTERVAL_HOURS}h).",
    )
    parser.add_argument(
        "--dry-run",
        "-d",
        action="store_true",
        help="Executa em modo simulação sem disparar mensagens reais.",
    )
    parser.add_argument(
        "--legacy",
        action="store_true",
        help="Executa com o orquestrador procedural legado em vez do Google ADK.",
    )
    return parser.parse_args()


async def scheduled_task(dry_run: bool, legacy: bool = False):
    logger.info("⏰ APScheduler: Disparando ciclo periódico de monitoramento...")
    try:
        if legacy:
            logger.info("Utilizando motor legado para o ciclo periódico...")
            await run_monitoring_cycle(dry_run=dry_run)
        else:
            logger.info("Utilizando Google ADK para o ciclo periódico...")
            runner = AdkMonitoringRunner()
            await runner.run_cycle(dry_run=dry_run, generate_report=False)
    except Exception as exc:
        logger.error(f"Erro durante o ciclo agendado: {exc}")


async def main():
    args = parse_args()
    logger.remove()
    logger.add(sys.stderr, level=settings.LOG_LEVEL)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        scheduled_task,
        "interval",
        hours=args.interval_hours,
        args=[args.dry_run, args.legacy],
        id="promoradar_monitor_job",
    )

    logger.info(
        f"🛰️ PromoRadar Daemon iniciado. Monitoramento agendado a cada {args.interval_hours} hora(s)."
    )

    # Executar uma primeira checagem imediata ao iniciar o daemon
    logger.info("Executando ciclo inicial imediatamente...")
    await scheduled_task(args.dry_run, args.legacy)

    scheduler.start()

    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Encerrando daemon PromoRadar...")
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
