"""Base engine for incremental Black Friday category dashboards (HTML Chart.js + Markdown)."""

from __future__ import annotations

import json
import webbrowser
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml
from jinja2 import Environment, FileSystemLoader
from loguru import logger

from src.core.domain import safe_json_for_html_script, validate_external_http_url
from src.core.models import PriceRecord
from src.data.database import default_db
from src.data.repository import Repository
from src.skills.price_statistics.analyzer import (
    PriceStatisticalProfile,
    PriceStatisticsSkill,
)

RECIFE_TZ = ZoneInfo("America/Recife")
BLACK_FRIDAY_2026 = datetime(2026, 11, 27, 0, 0, tzinfo=RECIFE_TZ)
DEFAULT_FRESHNESS_HOURS = 96
DEFAULT_SCALPER_MULTIPLIER = 1.65

CATEGORY_PALETTE = [
    "#0d9488",  # teal-600
    "#2563eb",  # blue-600
    "#d97706",  # amber-600
    "#7c3aed",  # violet-600
    "#dc2626",  # red-600
    "#059669",  # emerald-600
    "#db2777",  # pink-600
    "#4f46e5",  # indigo-600
    "#ea580c",  # orange-600
    "#0891b2",  # cyan-600
    "#65a30d",  # lime-600
    "#9333ea",  # purple-600
    "#be123c",  # rose-700
    "#0284c7",  # sky-600
    "#16a34a",  # green-600
]

MARKETPLACE_LABELS = {
    "amazon": "Amazon",
    "kabum": "KaBuM!",
    "mercadolivre": "Mercado Livre",
    "google_shopping": "Google Shopping",
    "shopee": "Shopee",
    "aliexpress": "AliExpress",
    "terabyte": "Terabyteshop",
    "pichau": "Pichau",
    "magalu": "Magalu",
    "dell": "Dell Oficial",
    "web_search": "Busca Web Verificada",
    "web_verified": "Busca Web Verificada",
}


def fmt_brl(value: float | None) -> str:
    """Formata um float em moeda brasileira R$ 1.234,56."""
    if value is None:
        return "—"
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def safe_external_href(url: str | None) -> str:
    """Garante que links renderizados em HTML/Markdown usem apenas http/https válidos."""
    if not url:
        return ""
    try:
        return validate_external_http_url(url, allow_private=True)
    except ValueError:
        return ""


@dataclass
class ProductHistoryBundle:
    """Resultado consolidado da agregação histórica de um produto do catálogo."""

    records_asc: list[PriceRecord]
    store_offers: list[dict[str, Any]]
    best_offer: dict[str, Any] | None
    mkt_bucket_min: dict[str, dict[str, float]]
    store_series: dict[str, list[dict[str, Any]]]
    live_price: float | None
    effective_price: float
    hist_min: float | None
    hist_avg: float | None
    stat_profile: PriceStatisticalProfile


class BaseCategoryDashboardGenerator:
    """Classe base coesa para todos os geradores de painel evolutivo por categoria."""

    def __init__(
        self,
        repository: Repository | None = None,
        config_path: str | Path = "src/config/products.yaml",
        cycles_log_path: str | Path = "data/cycles.jsonl",
    ):
        self.repository = repository or Repository(default_db)
        self.statistics_skill = PriceStatisticsSkill()
        self.config_path = Path(config_path)
        self.cycles_log_path = Path(cycles_log_path)
        template_dir = Path(__file__).parent / "templates"
        self.env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=True,
        )

    @staticmethod
    def to_recife(dt: datetime) -> datetime:
        """Converte qualquer datetime (naive ou aware) para o fuso `America/Recife`."""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc).astimezone(RECIFE_TZ)
        return dt.astimezone(RECIFE_TZ)

    # Aliases retrocompatíveis
    def _to_recife(self, dt: datetime) -> datetime:
        return self.to_recife(dt)

    @staticmethod
    def bucket_key(dt_recife: datetime) -> str:
        """Gera a chave de janela horária no fuso local."""
        return dt_recife.strftime("%Y-%m-%d %H:00")

    def _bucket_key(self, dt_recife: datetime) -> str:
        return self.bucket_key(dt_recife)

    def load_catalog_config(self) -> list[dict[str, Any]]:
        """Carrega os itens e especificações do arquivo YAML da categoria."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuração não encontrada: {self.config_path}")
        with open(self.config_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        return raw.get("products", [])

    def record_cycle_log(self, summary: dict[str, Any]) -> dict[str, Any]:
        """Acrescenta uma entrada incremental padronizada no log JSONL de ciclos."""
        self.cycles_log_path.parent.mkdir(parents=True, exist_ok=True)
        now_utc = datetime.now(timezone.utc)
        now_local = now_utc.astimezone(RECIFE_TZ)

        cycles = summary.get("cycles", [])
        quotes_collected = sum(c.get("prices_collected", 0) for c in cycles)
        deals_found = sum(c.get("deals_found", 0) for c in cycles)
        sources_checked = sum(c.get("sources_checked", 0) for c in cycles)
        items_checked = len(cycles)

        existing_runs = self.load_cycle_logs()
        run_number = len(existing_runs) + 1

        entry = {
            "run_number": run_number,
            "timestamp_utc": now_utc.isoformat(),
            "timestamp_local": now_local.strftime("%d/%m/%Y %H:%M"),
            "items_checked": items_checked,
            "monitors_checked": items_checked,  # alias retrocompatível com JSONLs antigos
            "arms_checked": items_checked,  # alias retrocompatível com suportes
            "sources_checked": sources_checked,
            "quotes_collected": quotes_collected,
            "deals_found": deals_found,
        }
        with open(self.cycles_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def load_cycle_logs(self) -> list[dict[str, Any]]:
        """Lê o histórico de ciclos executados no JSONL."""
        if not self.cycles_log_path.exists():
            return []
        entries: list[dict[str, Any]] = []
        for line in self.cycles_log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return entries

    def collect_product_history(
        self,
        item: dict[str, Any],
        *,
        now_local: datetime,
        fallback_ref_price: float,
        days: int = 120,
        freshness_hours: int = DEFAULT_FRESHNESS_HOURS,
        scalper_multiplier: float = DEFAULT_SCALPER_MULTIPLIER,
    ) -> ProductHistoryBundle:
        """Agrega cotações do SQLite, aplica teto anti-scalper/frescor e calcula perfil estatístico."""
        pid = item["id"]
        preco_alvo = float(item["preco_alvo"])
        preco_maximo = float(item["preco_maximo"])
        scalper_ceiling = preco_maximo * scalper_multiplier if preco_maximo > 0 else float("inf")

        sources = self.repository.get_sources_for_product(pid)
        source_map = {s.id: s for s in sources if s.id is not None}

        history = self.repository.get_price_history(pid, days=days)
        history_asc = sorted(history, key=lambda r: self.to_recife(r.coletado_em))

        latest_by_mkt: dict[str, dict[str, Any]] = {}
        mkt_bucket_min: dict[str, dict[str, float]] = defaultdict(dict)
        store_series: dict[str, list[dict[str, Any]]] = defaultdict(list)

        for rec in history_asc:
            if rec.preco is None or rec.preco <= 0 or rec.preco > scalper_ceiling:
                continue
            src = source_map.get(rec.source_id)
            mkt_key = src.marketplace if src else "desconhecido"
            mkt_label = MARKETPLACE_LABELS.get(mkt_key, mkt_key.upper())
            local_dt = self.to_recife(rec.coletado_em)
            bkey = self.bucket_key(local_dt)

            prev_val = mkt_bucket_min[bkey].get(mkt_key)
            if prev_val is None or rec.preco < prev_val:
                mkt_bucket_min[bkey][mkt_key] = rec.preco

            safe_url = safe_external_href(rec.url_encontrada or (src.url_produto if src else ""))
            latest_by_mkt[mkt_key] = {
                "marketplace_key": mkt_key,
                "marketplace": mkt_label,
                "preco": round(rec.preco, 2),
                "preco_fmt": fmt_brl(rec.preco),
                "preco_original": round(rec.preco_original, 2) if rec.preco_original else None,
                "preco_original_fmt": fmt_brl(rec.preco_original),
                "url": safe_url,
                "titulo": rec.titulo_coletado or item["nome"],
                "cupom": rec.cupom,
                "coletado_em": local_dt.strftime("%d/%m %H:%M"),
                "seen_at": local_dt,
            }
            store_series[mkt_label].append({
                "t": local_dt.strftime("%d/%m %H:%M"),
                "y": round(rec.preco, 2),
            })

        fresh_offers = [
            o
            for o in latest_by_mkt.values()
            if (now_local - o["seen_at"]).total_seconds() <= freshness_hours * 3600
        ]
        store_offers = sorted(
            ({k: v for k, v in o.items() if k != "seen_at"} for o in fresh_offers),
            key=lambda x: x["preco"],
        )
        best_offer = store_offers[0] if store_offers else None

        hist_min = self.repository.get_historical_min_price(pid)
        hist_avg = self.repository.get_historical_average_price(pid, days=60)
        valid_recs = [
            r for r in history_asc if r.preco is not None and 0 < r.preco <= scalper_ceiling
        ]
        hist_prices = [r.preco for r in valid_recs]
        hist_dates = [r.coletado_em for r in valid_recs]

        live_price = best_offer["preco"] if best_offer else None
        effective_price = live_price if live_price is not None else fallback_ref_price

        stat_profile = self.statistics_skill.execute(
            historical_prices=hist_prices,
            current_price=effective_price,
            historical_dates=hist_dates,
            target_price=preco_alvo,
            user_max_price=preco_maximo,
        )

        return ProductHistoryBundle(
            records_asc=valid_recs,
            store_offers=store_offers,
            best_offer=best_offer,
            mkt_bucket_min=dict(mkt_bucket_min),
            store_series=dict(store_series),
            live_price=live_price,
            effective_price=effective_price,
            hist_min=hist_min,
            hist_avg=hist_avg,
            stat_profile=stat_profile,
        )

    @staticmethod
    def build_timeline_series(
        all_buckets: set[str],
        per_item_buckets: dict[str, dict[str, dict[str, float]]],
        items_payload: list[dict[str, Any]],
        *,
        baseline_label: str,
        baseline_key: str,
        freshness_hours: int = DEFAULT_FRESHNESS_HOURS,
    ) -> list[str]:
        """Popula `timelineValues` em cada item e retorna os rótulos do eixo X."""
        sorted_buckets = sorted(all_buckets)
        bucket_dts = [
            datetime.strptime(b, "%Y-%m-%d %H:00").replace(tzinfo=RECIFE_TZ)
            for b in sorted_buckets
        ]
        timeline_labels = [baseline_label] + [dt.strftime("%d/%m %Hh") for dt in bucket_dts]

        for entry in items_payload:
            pid = entry["id"]
            buckets = per_item_buckets.get(pid, {})
            values: list[float | None] = [entry[baseline_key]]
            active: dict[str, tuple[datetime, float]] = {}
            last_known: float | None = None
            for b, b_dt in zip(sorted_buckets, bucket_dts, strict=True):
                for mkt_key, price in buckets.get(b, {}).items():
                    active[mkt_key] = (b_dt, price)
                fresh = [
                    p
                    for seen, p in active.values()
                    if (b_dt - seen).total_seconds() <= freshness_hours * 3600
                ]
                if fresh:
                    last_known = round(min(fresh), 2)
                values.append(last_known)
            entry["timelineValues"] = values

        return timeline_labels

    @staticmethod
    def safe_script_json(payload: object) -> str:
        """Serializa objeto JSON escapando sequências perigosas para incorporação em `<script>`."""
        return safe_json_for_html_script(payload)

    @staticmethod
    def write_outputs(
        *,
        html_content: str,
        md_content: str,
        output_html_path: str | Path,
        output_md_path: str | Path,
        open_browser: bool,
        banner_label: str,
    ) -> Path:
        """Persiste arquivos HTML e Markdown de forma padronizada e abre navegador opcionalmente."""
        out_html = Path(output_html_path)
        out_html.parent.mkdir(parents=True, exist_ok=True)
        out_html.write_text(html_content, encoding="utf-8")

        out_md = Path(output_md_path)
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text(md_content, encoding="utf-8")

        logger.success(f"{banner_label} atualizado: {out_html}")
        logger.info(f"📝 Relatório resumo atualizado: {out_md}")

        if open_browser and out_html.exists():
            webbrowser.open(out_html.resolve().as_uri())

        return out_html
