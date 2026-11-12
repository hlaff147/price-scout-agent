#!/usr/bin/env python3
"""CLI e Motor de Rastreamento Black Friday para Smartphones 512 GB (Faixa R$ 3.000)."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Garante execução no .venv do projeto e no diretório raiz correto
venv_python = PROJECT_ROOT / ".venv" / "bin" / "python"
if venv_python.exists() and Path(sys.executable).resolve() != venv_python.resolve():
    os.execv(str(venv_python), [str(venv_python)] + sys.argv)

os.chdir(PROJECT_ROOT)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import yaml
from loguru import logger

from src.agents.adk_runner import AdkMonitoringRunner
from src.config.settings import settings
from src.data.database import default_db
from src.data.models import ScrapedData, Source
from src.data.repository import Repository
from src.orchestrator.orchestrator import Orchestrator
from src.reporting.smartphones_dashboard_generator import SmartphonesDashboardGenerator
from src.subagents.notifier_agent.agent import NotifierSubagent
from src.subagents.price_analyst_agent.agent import PriceAnalystSubagent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rastreador Incremental Black Friday — Smartphones 512 GB (Custo × Benefício)"
    )
    parser.add_argument(
        "--config",
        type=str,
        default="src/config/smartphones_512.yaml",
        help="Caminho para o YAML dos smartphones 512 GB.",
    )
    parser.add_argument(
        "--product",
        "-p",
        type=str,
        default=None,
        help="Filtrar por um ID de smartphone específico (ex: 'moto-edge-50-ultra-512').",
    )
    parser.add_argument(
        "--dry-run",
        "-d",
        action="store_true",
        help="Executa sem disparar mensagens externas no Telegram.",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Não abre automaticamente o navegador após atualizar o HTML.",
    )
    parser.add_argument(
        "--dashboard-only",
        action="store_true",
        help="Apenas sincroniza o catálogo e recompila o painel HTML/Markdown a partir do SQLite.",
    )
    parser.add_argument(
        "--record-price",
        nargs=4,
        metavar=("PRODUCT_ID", "MARKETPLACE", "PRICE", "URL"),
        help="Registra manualmente/via busca web uma cotação verificada no SQLite e atualiza o painel.",
    )
    parser.add_argument(
        "--title",
        type=str,
        default=None,
        help="Título opcional do anúncio ao usar --record-price.",
    )
    parser.add_argument(
        "--record-cycle",
        action="store_true",
        help="Ao usar --dashboard-only, registra também um marco de ciclo no log incremental.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Habilita logs DEBUG.",
    )
    return parser.parse_args()


def load_phone_ids(config_path: str) -> list[str]:
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return [p["id"] for p in data.get("products", []) if p.get("ativo", True)]


async def record_verified_quote(
    repo: Repository,
    config_path: str,
    product_id: str,
    marketplace: str,
    price: float,
    url: str,
    title: str | None = None,
    dry_run: bool = True,
) -> None:
    """Persiste uma cotação verificada (ex: obtida via busca web) no SQLite passando pelo Analista."""
    orch = Orchestrator(repository=repo)
    orch.load_products_from_yaml(config_path)

    product = repo.get_product(product_id)
    if not product:
        raise ValueError(f"Smartphone '{product_id}' não encontrado em {config_path}.")

    mkt = marketplace.lower().strip()
    source = Source(
        product_id=product.id,
        marketplace=mkt,
        url_produto=url,
        metodo_coleta="web_verified",
        ativo=True,
    )
    source = repo.upsert_source(source)

    scraped = ScrapedData(
        marketplace=mkt,
        success=True,
        titulo=title or product.nome,
        preco=float(price),
        moeda="BRL",
        disponivel=True,
        url=url,
    )

    analyst = PriceAnalystSubagent(repository=repo)
    analyses = await analyst.run(product, [(source, scraped)])

    notifier = NotifierSubagent(repository=repo)
    for deal in analyses:
        if deal.is_deal:
            await notifier.run(deal, product, dry_run=dry_run)


async def async_main() -> None:
    args = parse_args()
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if args.verbose else settings.LOG_LEVEL)

    repo = Repository(default_db)
    dashboard_gen = SmartphonesDashboardGenerator(
        repository=repo,
        config_path=args.config,
    )

    # Modo 1: Registrar cotação individual verificada
    if args.record_price:
        pid, mkt, raw_price, url = args.record_price
        await record_verified_quote(
            repo=repo,
            config_path=args.config,
            product_id=pid,
            marketplace=mkt,
            price=float(raw_price),
            url=url,
            title=args.title,
            dry_run=args.dry_run or settings.DRY_RUN,
        )
        html_path = dashboard_gen.generate(open_browser=not args.no_open)
        print(f"✅ Cotação registrada para '{pid}' ({mkt}: R$ {float(raw_price):.2f}) -> {html_path.resolve()}")
        return

    # Modo 2: Apenas recompilar o painel a partir do SQLite
    if args.dashboard_only:
        orch = Orchestrator(repository=repo)
        products = orch.load_products_from_yaml(args.config)
        if args.record_cycle:
            dashboard_gen.record_cycle_log({
                "cycles": [
                    {
                        "product_id": p.id,
                        "sources_checked": len(p.sources),
                        "prices_collected": 1 if repo.get_price_history(p.id, days=1) else 0,
                        "deals_found": (
                            1
                            if (hm := repo.get_historical_min_price(p.id)) is not None and hm <= p.preco_alvo
                            else 0
                        ),
                    }
                    for p in products
                ]
            })
        html_path = dashboard_gen.generate(open_browser=not args.no_open)
        print(f"📱 Painel de celulares recompilado com sucesso: {html_path.resolve()}")
        return

    # Modo 3: Ciclo completo Google ADK para todos os smartphones 512 GB
    phone_ids = load_phone_ids(args.config)
    runner = AdkMonitoringRunner(repository=repo)
    summary = await runner.run_cycle(
        product_id=args.product,
        product_ids=phone_ids,
        dry_run=args.dry_run or settings.DRY_RUN,
        generate_report=False,
        open_browser=False,
        config_path=args.config,
    )

    cycle_entry = dashboard_gen.record_cycle_log(summary)
    html_path = dashboard_gen.generate(open_browser=not args.no_open)

    cycles = summary.get("cycles", [])
    missing_ids = [
        c["product_id"]
        for c in cycles
        if c.get("prices_collected", 0) == 0 and "product_id" in c
    ]

    print("\n" + "=" * 70)
    print(f"📱 RADAR BLACK FRIDAY — SMARTPHONES 512 GB (CICLO #{cycle_entry['run_number']})")
    print("=" * 70)
    print(f"• Aparelhos verificados: {cycle_entry['monitors_checked']}")
    print(f"• Fontes consultadas:    {cycle_entry['sources_checked']}")
    print(f"• Cotações coletadas:    {cycle_entry['quotes_collected']}")
    print(f"• Ofertas no alvo BF:    {cycle_entry['deals_found']}")
    if missing_ids:
        print(f"• Sem cotação HTTP direta ({len(missing_ids)}): {', '.join(missing_ids)}")
    print(f"• Painel HTML Unificado: {html_path.resolve()}")
    print(f"• Resumo Markdown:       {(PROJECT_ROOT / 'reports' / 'celulares_512gb_summary.md').resolve()}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(async_main())
