"""Gerador do Dashboard Interativo Unificado e Relatório Incremental de Monitores 27" (Black Friday)."""

from __future__ import annotations

import json
import webbrowser
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml
from jinja2 import Environment, FileSystemLoader
from loguru import logger

from src.data.database import default_db
from src.data.models import PriceRecord
from src.data.repository import Repository
from src.skills.price_statistics.analyzer import PriceStatisticsSkill

RECIFE_TZ = ZoneInfo("America/Recife")

# Paleta distinta para curvas de evolução temporal de cada monitor
MONITOR_PALETTE = [
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
    "terabyte": "Terabyteshop",
    "pichau": "Pichau",
    "magalu": "Magalu",
    "dell": "Dell Oficial",
    "web_search": "Busca Web Verificada",
}


def fmt_brl(value: float | None) -> str:
    """Formata um float em moeda brasileira R$ 1.234,56."""
    if value is None:
        return "—"
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


class MonitorsDashboardGenerator:
    """Compila o painel HTML único evolutivo e o relatório Markdown incremental de monitores 27"."""

    def __init__(
        self,
        repository: Repository | None = None,
        config_path: str | Path = "src/config/monitors_27.yaml",
        cycles_log_path: str | Path = "data/monitors_27_cycles.jsonl",
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

    def load_catalog_config(self) -> list[dict[str, Any]]:
        """Carrega os 13 monitores e suas especificações ergonômicas do YAML."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuração não encontrada: {self.config_path}")
        with open(self.config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        return raw.get("products", [])

    def record_cycle_log(self, summary: dict[str, Any]) -> dict[str, Any]:
        """Acrescenta uma entrada incremental no log JSONL de ciclos executados."""
        self.cycles_log_path.parent.mkdir(parents=True, exist_ok=True)
        now_utc = datetime.now(timezone.utc)
        now_local = now_utc.astimezone(RECIFE_TZ)

        cycles = summary.get("cycles", [])
        quotes_collected = sum(c.get("prices_collected", 0) for c in cycles)
        deals_found = sum(c.get("deals_found", 0) for c in cycles)
        sources_checked = sum(c.get("sources_checked", 0) for c in cycles)

        existing_runs = self.load_cycle_logs()
        run_number = len(existing_runs) + 1

        entry = {
            "run_number": run_number,
            "timestamp_utc": now_utc.isoformat(),
            "timestamp_local": now_local.strftime("%d/%m/%Y %H:%M"),
            "monitors_checked": len(cycles),
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

    def generate(
        self,
        output_html_path: str | Path = "reports/monitores_27_black_friday.html",
        output_md_path: str | Path = "reports/monitors_27_history_summary.md",
        open_browser: bool = False,
    ) -> Path:
        """Gera o dashboard HTML interativo unificado e o relatório Markdown incremental."""
        catalog = self.load_catalog_config()
        cycle_logs = self.load_cycle_logs()
        now_local = datetime.now(timezone.utc).astimezone(RECIFE_TZ)

        monitors_payload: list[dict[str, Any]] = []
        all_bucket_labels_set: set[str] = set()
        per_monitor_mkt_bucket_prices: dict[str, dict[str, dict[str, float]]] = {}
        total_db_records = 0

        for idx, item in enumerate(catalog):
            pid = item["id"]
            specs = item.get("specs", {})
            color = MONITOR_PALETTE[idx % len(MONITOR_PALETTE)]

            sources = self.repository.get_sources_for_product(pid)
            source_map = {s.id: s for s in sources if s.id is not None}

            history: list[PriceRecord] = self.repository.get_price_history(pid, days=120)
            # Ordenar cronologicamente (antigo -> recente)
            history_asc = sorted(history, key=lambda r: r.coletado_em)
            total_db_records += len(history_asc)

            # Última cotação válida por marketplace e melhor preço por loja/janela
            latest_by_mkt: dict[str, dict[str, Any]] = {}
            mkt_bucket_min: dict[str, dict[str, float]] = defaultdict(dict)
            store_series: dict[str, list[dict[str, Any]]] = defaultdict(list)

            for rec in history_asc:
                src = source_map.get(rec.source_id)
                mkt_key = src.marketplace if src else "desconhecido"
                mkt_label = MARKETPLACE_LABELS.get(mkt_key, mkt_key.upper())
                local_dt = (
                    rec.coletado_em.astimezone(RECIFE_TZ)
                    if rec.coletado_em.tzinfo
                    else rec.coletado_em.replace(tzinfo=timezone.utc).astimezone(RECIFE_TZ)
                )
                # Agrupar por janela horária da rodada
                bucket_key = local_dt.strftime("%Y-%m-%d %H:00")
                all_bucket_labels_set.add(bucket_key)
                prev_mkt_bucket = mkt_bucket_min[bucket_key].get(mkt_key)
                if prev_mkt_bucket is None or rec.preco < prev_mkt_bucket:
                    mkt_bucket_min[bucket_key][mkt_key] = rec.preco

                latest_by_mkt[mkt_key] = {
                    "marketplace_key": mkt_key,
                    "marketplace": mkt_label,
                    "preco": round(rec.preco, 2),
                    "preco_fmt": fmt_brl(rec.preco),
                    "preco_original": round(rec.preco_original, 2) if rec.preco_original else None,
                    "preco_original_fmt": fmt_brl(rec.preco_original),
                    "url": rec.url_encontrada or (src.url_produto if src else ""),
                    "titulo": rec.titulo_coletado or item["nome"],
                    "cupom": rec.cupom,
                    "coletado_em": local_dt.strftime("%d/%m %H:%M"),
                }
                store_series[mkt_label].append({
                    "t": local_dt.strftime("%d/%m %H:%M"),
                    "y": round(rec.preco, 2),
                })

            per_monitor_mkt_bucket_prices[pid] = dict(mkt_bucket_min)

            store_offers = sorted(latest_by_mkt.values(), key=lambda x: x["preco"])
            best_offer = store_offers[0] if store_offers else None

            price_min_ref = float(specs.get("price_min_ref", item["preco_alvo"]))
            price_max_ref = float(specs.get("price_max_ref", item["preco_maximo"]))
            preco_alvo = float(item["preco_alvo"])
            preco_maximo = float(item["preco_maximo"])

            hist_min = self.repository.get_historical_min_price(pid)
            hist_avg = self.repository.get_historical_average_price(pid, days=60)
            hist_prices = [r.preco for r in history_asc if r.preco is not None and r.preco > 0]
            hist_dates = [r.coletado_em for r in history_asc if r.preco is not None and r.preco > 0]

            live_price = best_offer["preco"] if best_offer else None
            effective_price = live_price if live_price is not None else price_min_ref

            stat_profile = self.statistics_skill.execute(
                historical_prices=hist_prices,
                current_price=effective_price,
                historical_dates=hist_dates,
                target_price=preco_alvo,
                user_max_price=preco_maximo,
            )

            diff_vs_ref_pct = (
                round(((live_price - price_min_ref) / price_min_ref) * 100.0, 1)
                if live_price is not None and price_min_ref > 0
                else None
            )
            is_below_target = bool(live_price is not None and live_price <= preco_alvo)
            is_all_time_low = bool(
                live_price is not None
                and hist_min is not None
                and len(history_asc) > 1
                and live_price <= hist_min
            )

            if is_below_target:
                status_badge = "🎯 Abaixo do Alvo"
                status_key = "deal"
            elif live_price is not None and diff_vs_ref_pct is not None and diff_vs_ref_pct <= -3.0:
                status_badge = "📉 Em Queda"
                status_key = "dropping"
            elif live_price is not None:
                status_badge = "✅ Monitorado"
                status_key = "tracked"
            else:
                status_badge = "⏳ Ref. Base"
                status_key = "baseline"

            monitors_payload.append({
                "id": pid,
                "name": item["nome"],
                "statusBadge": status_badge,
                "statusKey": status_key,
                "res": specs.get("res", "QHD"),
                "panel": specs.get("panel", "IPS"),
                "refresh": int(specs.get("refresh", 180)),
                "response": specs.get("response", "1 ms"),
                "has": specs.get("has", "Ajuste de Altura"),
                "ports": specs.get("ports", "HDMI, DisplayPort"),
                "priceMinRef": price_min_ref,
                "priceMaxRef": price_max_ref,
                "priceTarget": preco_alvo,
                "priceMaxAllowed": preco_maximo,
                "livePrice": live_price,
                "effectivePrice": round(effective_price, 2),
                "effectivePriceFmt": fmt_brl(effective_price),
                "livePriceFmt": fmt_brl(live_price),
                "priceTargetFmt": fmt_brl(preco_alvo),
                "histMin": round(hist_min, 2) if hist_min is not None else None,
                "histMinFmt": fmt_brl(hist_min),
                "histAvg": round(hist_avg, 2) if hist_avg is not None else None,
                "histAvgFmt": fmt_brl(hist_avg),
                "diffVsRefPct": diff_vs_ref_pct,
                "isBelowTarget": is_below_target,
                "isAllTimeLow": is_all_time_low,
                "hasLiveQuote": live_price is not None,
                "bestStore": best_offer["marketplace"] if best_offer else "Referência Inicial",
                "bestUrl": best_offer["url"] if best_offer else "",
                "bestUpdated": best_offer["coletado_em"] if best_offer else "Base 2026",
                "storeOffers": store_offers,
                "storeSeries": dict(store_series),
                "recordsCount": len(history_asc),
                "tag": specs.get("tag", ""),
                "useCase": specs.get("use_case", "Gamer"),
                "ppi": int(specs.get("ppi", 109)),
                "desc": specs.get("desc", ""),
                "color": color,
                "dealScore": stat_profile.deal_confidence_score,
                "robustZScore": stat_profile.robust_z_score,
                "percentileRank": stat_profile.percentile_rank,
                "cvPercent": stat_profile.cv_percent,
                "trendSlope": stat_profile.trend_slope_brl_per_day,
                "priceRegime": stat_profile.regime_preco,
            })

        # Construir eixo X incremental da linha do tempo:
        # Ponto 0 = "Ref. Inicial" seguido de cada janela horária coletada no SQLite
        sorted_buckets = sorted(all_bucket_labels_set)
        bucket_dts = [
            datetime.strptime(b, "%Y-%m-%d %H:00").replace(tzinfo=RECIFE_TZ)
            for b in sorted_buckets
        ]
        timeline_labels = ["Ref. Inicial"] + [dt.strftime("%d/%m %Hh") for dt in bucket_dts]

        for m in monitors_payload:
            pid = m["id"]
            mkt_b_prices = per_monitor_mkt_bucket_prices.get(pid, {})
            series_values: list[float | None] = [m["priceMinRef"]]
            active_by_mkt: dict[str, tuple[datetime, float]] = {}
            last_known: float | None = None
            for b, b_dt in zip(sorted_buckets, bucket_dts, strict=True):
                for mkt_key, mkt_price in mkt_b_prices.get(b, {}).items():
                    active_by_mkt[mkt_key] = (b_dt, mkt_price)
                fresh_prices = [
                    p
                    for seen_dt, p in active_by_mkt.values()
                    if (b_dt - seen_dt).total_seconds() <= 96 * 3600
                ]
                if fresh_prices:
                    last_known = round(min(fresh_prices), 2)
                series_values.append(last_known)
            m["timelineValues"] = series_values

        # KPIs agregados dinâmicos
        qhd_models = [m for m in monitors_payload if m["res"] == "QHD"]
        qhd_gamer_models = [m for m in qhd_models if m["refresh"] >= 144]
        best_qhd_gamer = min(qhd_gamer_models, key=lambda x: x["effectivePrice"]) if qhd_gamer_models else None
        best_overall = min(monitors_payload, key=lambda x: x["effectivePrice"]) if monitors_payload else None
        deals_count = sum(1 for m in monitors_payload if m["isBelowTarget"])
        live_tracked_count = sum(1 for m in monitors_payload if m["hasLiveQuote"])

        # Contagem regressiva Black Friday 2026 (4ª sexta-feira de novembro = 27/11/2026)
        bf_date = datetime(2026, 11, 27, 0, 0, tzinfo=RECIFE_TZ)
        days_to_bf = max(0, (bf_date.date() - now_local.date()).days)

        kpis = {
            "best_qhd_gamer_price": fmt_brl(best_qhd_gamer["effectivePrice"]) if best_qhd_gamer else "R$ 1.102,00",
            "best_qhd_gamer_name": best_qhd_gamer["name"] if best_qhd_gamer else "ASUS ROG Strix XG27ACS",
            "best_overall_price": fmt_brl(best_overall["effectivePrice"]) if best_overall else "R$ 836,00",
            "best_overall_name": best_overall["name"] if best_overall else "HQ Pro 27\" HQ27AJ75G",
            "deals_count": deals_count,
            "live_tracked_count": live_tracked_count,
            "total_monitors": len(monitors_payload),
            "total_cycles": max(len(cycle_logs), len(sorted_buckets)),
            "total_db_records": total_db_records,
            "days_to_bf": days_to_bf,
            "last_updated": now_local.strftime("%d/%m/%Y às %H:%M (America/Recife)"),
        }

        # Renderizar HTML
        template = self.env.get_template("monitors_27_dashboard.html")
        html_content = template.render(
            kpis=kpis,
            monitors_json=json.dumps(monitors_payload, ensure_ascii=False),
            timeline_labels_json=json.dumps(timeline_labels, ensure_ascii=False),
            cycle_logs_json=json.dumps(cycle_logs[-20:][::-1], ensure_ascii=False),
            monitors=monitors_payload,
            cycle_logs=cycle_logs[-10:][::-1],
        )

        out_html = Path(output_html_path)
        out_html.parent.mkdir(parents=True, exist_ok=True)
        out_html.write_text(html_content, encoding="utf-8")

        # Gerar também o relatório Markdown incremental
        out_md = Path(output_md_path)
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text(
            self._build_markdown_report(kpis, monitors_payload, cycle_logs),
            encoding="utf-8",
        )

        logger.success(f"📊 Painel Black Friday atualizado: {out_html}")
        logger.info(f"📝 Relatório resumo atualizado: {out_md}")

        if open_browser:
            webbrowser.open(f"file://{out_html.resolve()}")

        return out_html

    def _build_markdown_report(
        self,
        kpis: dict[str, Any],
        monitors: list[dict[str, Any]],
        cycle_logs: list[dict[str, Any]],
    ) -> str:
        """Gera um relatório executivo em Markdown atualizado a cada rodada de 6h."""
        lines = [
            "# 📊 Relatório Incremental Black Friday 2026 — Monitores 27\" Ergonômicos",
            "",
            f"- **Última atualização:** {kpis['last_updated']}",
            f"- **Contagem regressiva Black Friday (27/11/2026):** {kpis['days_to_bf']} dias",
            f"- **Rodadas acumuladas:** {kpis['total_cycles']} | **Cotações no SQLite:** {kpis['total_db_records']}",
            f"- **Monitores com cotação ao vivo:** {kpis['live_tracked_count']}/{kpis['total_monitors']} | **Abaixo do Alvo:** {kpis['deals_count']}",
            f"- **Menor QHD Gamer (144Hz+) atual:** {kpis['best_qhd_gamer_price']} ({kpis['best_qhd_gamer_name']})",
            "",
            "## 🏆 Tabela Consolidada de Preços (Ordenada por Menor Valor Atual)",
            "",
            "| Monitor | Res / Hz | Preço Atual | Loja | Alvo BF | Mín. Histórica | Deal Score | Z-Score (MAD) | Status |",
            "| :--- | :---: | :---: | :--- | :---: | :---: | :---: | :---: | :--- |",
        ]

        sorted_mons = sorted(monitors, key=lambda x: x["effectivePrice"])
        for m in sorted_mons:
            store_cell = (
                f"[{m['bestStore']}]({m['bestUrl']})"
                if m["bestUrl"]
                else m["bestStore"]
            )
            status_icon = (
                "🎯 ABAIXO DO ALVO"
                if m["isBelowTarget"]
                else ("✅ Ao Vivo" if m["hasLiveQuote"] else "⏳ Ref. Base")
            )
            z_fmt = f"{m['robustZScore']:+.2f}" if m.get("robustZScore") is not None else "0.00"
            score_fmt = f"{m['dealScore']:.0f}/100" if m.get("dealScore") is not None else "—"
            lines.append(
                f"| **{m['name']}** | {m['res']} {m['refresh']}Hz | **{m['effectivePriceFmt']}** | "
                f"{store_cell} | {m['priceTargetFmt']} | {m['histMinFmt']} | `{score_fmt}` | `{z_fmt}` | {status_icon} |"
            )

        lines.extend([
            "",
            "## ⏱️ Histórico Recente de Execuções (Ciclos de 6h)",
            "",
            "| Ciclo | Data / Hora (Recife) | Monitores | Fontes | Cotações Válidas | Oportunidades |",
            "| :---: | :---: | :---: | :---: | :---: | :---: |",
        ])

        if cycle_logs:
            for log in cycle_logs[-15:][::-1]:
                lines.append(
                    f"| #{log.get('run_number', '?')} | {log.get('timestamp_local', '—')} | "
                    f"{log.get('monitors_checked', 0)} | {log.get('sources_checked', 0)} | "
                    f"{log.get('quotes_collected', 0)} | {log.get('deals_found', 0)} |"
                )
        else:
            lines.append("| #0 | Base Inicial | 13 | — | — | — |")

        lines.append("")
        return "\n".join(lines)
