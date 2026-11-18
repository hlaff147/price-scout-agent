"""Unified CLI and tracking engine for all Black Friday vertical categories."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml
from loguru import logger

from src.agents.adk_runner import AdkMonitoringRunner
from src.config.settings import settings
from src.core.domain import validate_external_http_url
from src.core.models import ScrapedData, Source
from src.data.database import default_db
from src.data.repository import Repository
from src.orchestrator.orchestrator import Orchestrator
from src.reporting.category_base import BaseCategoryDashboardGenerator
from src.subagents.notifier_agent.agent import NotifierSubagent
from src.subagents.price_analyst_agent.agent import PriceAnalystSubagent
from src.tools.browser_pool import browser_pool
from src.tools.http_client import http_client


@dataclass(frozen=True)
class CategoryTrackerSpec:
    """Configuração declarativa de uma vertical de rastreamento Black Friday."""

    category_key: str
    cli_description: str
    banner_title: str
    banner_icon: str
    item_noun_singular: str
    item_noun_plural: str
    default_config_path: str
    output_html_path: str
    output_md_path: str
    dashboard_cls: type[BaseCategoryDashboardGenerator]
    example_product_id: str


def build_category_arg_parser(spec: CategoryTrackerSpec) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=spec.cli_description)
    parser.add_argument(
        "--config",
        type=str,
        default=spec.default_config_path,
        help=f"Caminho para o YAML de {spec.item_noun_plural.lower()}.",
    )
    parser.add_argument(
        "--product",
        "-p",
        type=str,
        default=None,
        help=f"Filtrar por um ID específico (ex: '{spec.example_product_id}').",
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
        help="Registra uma cotação verificada no SQLite passando pelo Analista e atualiza o painel.",
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
    return parser


def load_active_catalog_ids(config_path: str | Path) -> list[str]:
    with open(config_path, encoding="utf-8") as f:
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
    """Persiste uma cotação verificada no SQLite passando pelo `PriceAnalystSubagent` e `NotifierSubagent`."""
    validated_url = validate_external_http_url(url, allow_private=settings.ALLOW_PRIVATE_URLS)
    if price <= 0:
        raise ValueError(f"Preço deve ser positivo (recebido: {price}).")

    orch = Orchestrator(repository=repo)
    orch.load_products_from_yaml(config_path)

    product = repo.get_product(product_id)
    if not product:
        raise ValueError(f"Produto '{product_id}' não encontrado em {config_path}.")

    mkt = marketplace.lower().strip()
    source = repo.upsert_source(
        Source(
            product_id=product.id,
            marketplace=mkt,
            url_produto=validated_url,
            metodo_coleta="web_verified",
            ativo=True,
        )
    )

    scraped = ScrapedData(
        marketplace=mkt,
        success=True,
        titulo=title or product.nome,
        preco=float(price),
        moeda="BRL",
        disponivel=True,
        url=validated_url,
    )

    analyst = PriceAnalystSubagent(repository=repo)
    analyses = await analyst.run(product, [(source, scraped)])

    notifier = NotifierSubagent(repository=repo)
    for deal in analyses:
        if deal.is_deal:
            await notifier.run(deal, product, dry_run=dry_run)


async def run_category_tracker(
    spec: CategoryTrackerSpec,
    argv: Sequence[str] | None = None,
    *,
    repository: Repository | None = None,
) -> int:
    """Executa qualquer vertical nos modos `--record-price`, `--dashboard-only` ou ciclo completo ADK."""
    parser = build_category_arg_parser(spec)
    args = parser.parse_args(argv)

    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if args.verbose else settings.LOG_LEVEL)

    repo = repository or Repository(default_db)
    dashboard_gen = spec.dashboard_cls(
        repository=repo,
        config_path=args.config,
    )
    is_dry_run = bool(args.dry_run or settings.DRY_RUN)

    try:
        # Modo 1: Registrar cotação individual verificada
        if args.record_price:
            pid, mkt, raw_price, url = args.record_price
            price_val = float(raw_price.replace(",", "."))
            await record_verified_quote(
                repo=repo,
                config_path=args.config,
                product_id=pid,
                marketplace=mkt,
                price=price_val,
                url=url,
                title=args.title,
                dry_run=is_dry_run,
            )
            html_path = dashboard_gen.generate(
                output_html_path=spec.output_html_path,
                output_md_path=spec.output_md_path,
                open_browser=not args.no_open,
            )
            print(
                f"✅ Cotação registrada para '{pid}' ({mkt}: R$ {price_val:.2f}) -> {html_path.resolve()}"
            )
            return 0

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
                                if (hm := repo.get_historical_min_price(p.id)) is not None
                                and hm <= p.preco_alvo
                                else 0
                            ),
                        }
                        for p in products
                    ]
                })
            html_path = dashboard_gen.generate(
                output_html_path=spec.output_html_path,
                output_md_path=spec.output_md_path,
                open_browser=not args.no_open,
            )
            print(f"{spec.banner_icon} Painel recompilado com sucesso: {html_path.resolve()}")
            return 0

        # Modo 3: Ciclo completo Google ADK para todos os itens ativos da categoria
        catalog_ids = load_active_catalog_ids(args.config)
        runner = AdkMonitoringRunner(repository=repo)
        async with http_client:
            summary = await runner.run_cycle(
                product_id=args.product,
                product_ids=catalog_ids,
                dry_run=is_dry_run,
                generate_report=False,
                open_browser=False,
                config_path=args.config,
            )

        cycle_entry = dashboard_gen.record_cycle_log(summary)
        html_path = dashboard_gen.generate(
            output_html_path=spec.output_html_path,
            output_md_path=spec.output_md_path,
            open_browser=not args.no_open,
        )

        cycles = summary.get("cycles", [])
        missing_ids = [
            c["product_id"]
            for c in cycles
            if c.get("prices_collected", 0) == 0 and "product_id" in c
        ]

        md_resolved = Path(spec.output_md_path).resolve()
        print("\n" + "=" * 70)
        print(
            f"{spec.banner_icon} RADAR BLACK FRIDAY — {spec.banner_title} (CICLO #{cycle_entry['run_number']})"
        )
        print("=" * 70)
        print(f"• {spec.item_noun_plural:<22} {cycle_entry['items_checked']}")
        print(f"• Fontes consultadas:    {cycle_entry['sources_checked']}")
        print(f"• Cotações coletadas:    {cycle_entry['quotes_collected']}")
        print(f"• Ofertas no alvo BF:    {cycle_entry['deals_found']}")
        if missing_ids:
            print(f"• Sem cotação HTTP direta ({len(missing_ids)}): {', '.join(missing_ids)}")
        print(f"• Painel HTML Unificado: {html_path.resolve()}")
        print(f"• Resumo Markdown:       {md_resolved}")
        print("=" * 70 + "\n")
        return 0
    finally:
        await http_client.close()
        await browser_pool.close()
