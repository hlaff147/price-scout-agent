#!/usr/bin/env python3
"""CLI e Motor de Rastreamento Black Friday para Suportes Articulados (1 e 2 Monitores, Mesa 5 cm Sem Furos)."""

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
from src.reporting.monitor_arms_dashboard_generator import MonitorArmsDashboardGenerator
from src.subagents.notifier_agent.agent import NotifierSubagent
from src.subagents.price_analyst_agent.agent import PriceAnalystSubagent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rastreador Incremental Black Friday — Suportes Articulados para Monitores (Mesa 5 cm)"
    )
    parser.add_argument(
        "--config",
        type=str,
        default="src/config/monitor_arms.yaml",
        help="Caminho para o YAML dos suportes de monitor.",
    )
    parser.add_argument(
        "--product",
        "-p",
        type=str,
        default=None,
        help="Filtrar por um ID de suporte específico (ex: 'elg-f80n').",
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
    return parser.parse_args()


def sync_catalog(repo: Repository, config_path: Path) -> list[dict]:
    if not config_path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {config_path}")

    orch = Orchestrator(repository=repo)
    orch.load_products_from_yaml(str(config_path))
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return data.get("products", [])


def record_manual_price(
    repo: Repository,
    product_id: str,
    marketplace: str,
    price: float,
    url: str,
    title: str | None = None,
) -> None:
    prod = repo.get_product(product_id)
    if not prod:
        raise ValueError(f"Suporte '{product_id}' não encontrado no catálogo SQLite.")

    sources = repo.get_sources_for_product(product_id)
    target_src = next((s for s in sources if s.marketplace.lower() == marketplace.lower()), None)
    if not target_src:
        src_id = repo.upsert_source(
            Source(
                product_id=product_id,
                marketplace=marketplace.lower(),
                url_produto=url,
                metodo_coleta="web_search",
                ativo=True,
            )
        )
        target_src = Source(
            id=src_id,
            product_id=product_id,
            marketplace=marketplace.lower(),
            url_produto=url,
            metodo_coleta="web_search",
        )

    scraped = ScrapedData(
        source_id=target_src.id,
        marketplace=target_src.marketplace,
        sucesso=True,
        preco=float(price),
        titulo_coletado=title or prod.nome,
        url_encontrada=url,
        disponivel=True,
    )
    repo.save_price_record(scraped)

    analyst = PriceAnalystSubagent(repo)
    opps = analyst.run(product_id, [scraped])
    if opps:
        notifier = NotifierSubagent(repo)
        notifier.run(opps)

    logger.success(
        f"💾 Preço registrado: {prod.nome} em [{marketplace.upper()}] = R$ {price:.2f} ({url})"
    )


async def run_tracking(args: argparse.Namespace) -> int:
    default_db.init_db()
    repo = Repository(default_db)
    config_path = Path(args.config)

    products_cfg = sync_catalog(repo, config_path)
    generator = MonitorArmsDashboardGenerator(repo, config_path)

    if args.record_price:
        pid, mkt, price_str, url = args.record_price
        record_manual_price(repo, pid, mkt, float(price_str), url, title=args.title)
        generator.generate(open_browser=not args.no_open)
        return 0

    if args.dashboard_only:
        paths = generator.generate(open_browser=not args.no_open)
        print(f"Painel atualizado: {paths['html']}")
        print(f"Resumo atualizado: {paths['markdown']}")
        return 0

    if args.product:
        target_ids = [args.product]
    else:
        target_ids = [p["id"] for p in products_cfg if p.get("ativo", True)]

    if settings.use_adk:
        runner = AdkMonitoringRunner(repo, generate_report=False)
        results = await runner.run_cycle(product_ids=target_ids, dry_run=args.dry_run)
    else:
        orch = Orchestrator(repo, dry_run=args.dry_run, generate_report=False)
        results = await orch.run_cycle(product_ids=target_ids)

    arms_checked = len(results)
    sources_checked = sum(r.get("sources_checked", 0) for r in results)
    quotes_collected = sum(r.get("prices_found", 0) for r in results)
    deals_found = sum(r.get("opportunities", 0) for r in results)

    run_number = generator.append_cycle_log(
        arms_checked=arms_checked,
        sources_checked=sources_checked,
        quotes_collected=quotes_collected,
        deals_found=deals_found,
    )
    paths = generator.generate(open_browser=not args.no_open)

    missing_live = [r["product_id"] for r in results if r.get("prices_found", 0) == 0]
    print("\n" + "=" * 70)
    print(f"🦾 RADAR BLACK FRIDAY — SUPORTES DE MONITOR (CICLO #{run_number})")
    print("=" * 70)
    print(f"• Suportes verificados:  {arms_checked}")
    print(f"• Fontes consultadas:    {sources_checked}")
    print(f"• Cotações coletadas:    {quotes_collected}")
    print(f"• Ofertas no alvo BF:    {deals_found}")
    if missing_live:
        print(f"• Sem cotação HTTP direta ({len(missing_live)}): {', '.join(missing_live)}")
    print(f"• Painel HTML Unificado: {paths['html'].resolve()}")
    print(f"• Resumo Markdown:       {paths['markdown'].resolve()}")
    print("=" * 70 + "\n")
    return 0


def main() -> int:
    args = parse_args()
    return asyncio.run(run_tracking(args))


if __name__ == "__main__":
    raise SystemExit(main())
