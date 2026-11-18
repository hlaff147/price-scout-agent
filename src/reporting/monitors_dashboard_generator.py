"""Gerador do Dashboard Interativo Unificado e Relatório Incremental de Monitores 27" (Black Friday)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.data.repository import Repository
from src.reporting.category_base import (
    BLACK_FRIDAY_2026,
    DEFAULT_FRESHNESS_HOURS,
    MARKETPLACE_LABELS,
    RECIFE_TZ,
    BaseCategoryDashboardGenerator,
    fmt_brl,
)
from src.reporting.category_base import (
    CATEGORY_PALETTE as MONITOR_PALETTE,
)

__all__ = [
    "MARKETPLACE_LABELS",
    "MONITOR_PALETTE",
    "RECIFE_TZ",
    "MonitorsDashboardGenerator",
    "fmt_brl",
]


class MonitorsDashboardGenerator(BaseCategoryDashboardGenerator):
    """Compila o painel HTML único evolutivo e o relatório Markdown incremental de monitores 27"."""

    def __init__(
        self,
        repository: Repository | None = None,
        config_path: str | Path = "src/config/monitors_27.yaml",
        cycles_log_path: str | Path = "data/monitors_27_cycles.jsonl",
    ):
        super().__init__(
            repository=repository,
            config_path=config_path,
            cycles_log_path=cycles_log_path,
        )

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
        all_buckets: set[str] = set()
        per_monitor_buckets: dict[str, dict[str, dict[str, float]]] = {}
        total_db_records = 0

        for idx, item in enumerate(catalog):
            pid = item["id"]
            specs = item.get("specs", {}) or {}
            color = MONITOR_PALETTE[idx % len(MONITOR_PALETTE)]

            price_min_ref = float(specs.get("price_min_ref", item["preco_alvo"]))
            price_max_ref = float(specs.get("price_max_ref", item["preco_maximo"]))
            preco_alvo = float(item["preco_alvo"])
            preco_maximo = float(item["preco_maximo"])

            bundle = self.collect_product_history(
                item,
                now_local=now_local,
                fallback_ref_price=price_min_ref,
                freshness_hours=DEFAULT_FRESHNESS_HOURS,
            )
            total_db_records += len(bundle.records_asc)
            all_buckets.update(bundle.mkt_bucket_min.keys())
            per_monitor_buckets[pid] = bundle.mkt_bucket_min

            live_price = bundle.live_price
            effective_price = bundle.effective_price
            best_offer = bundle.best_offer
            stat_profile = bundle.stat_profile

            diff_vs_ref_pct = (
                round(((live_price - price_min_ref) / price_min_ref) * 100.0, 1)
                if live_price is not None and price_min_ref > 0
                else None
            )
            is_below_target = bool(live_price is not None and live_price <= preco_alvo)
            is_all_time_low = bool(
                live_price is not None
                and bundle.hist_min is not None
                and len(bundle.records_asc) > 1
                and live_price <= bundle.hist_min
            )

            if is_below_target:
                status_badge, status_key = "🎯 Abaixo do Alvo", "deal"
            elif live_price is not None and diff_vs_ref_pct is not None and diff_vs_ref_pct <= -3.0:
                status_badge, status_key = "📉 Em Queda", "dropping"
            elif live_price is not None:
                status_badge, status_key = "✅ Monitorado", "tracked"
            else:
                status_badge, status_key = "⏳ Ref. Base", "baseline"

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
                "histMin": round(bundle.hist_min, 2) if bundle.hist_min is not None else None,
                "histMinFmt": fmt_brl(bundle.hist_min),
                "histAvg": round(bundle.hist_avg, 2) if bundle.hist_avg is not None else None,
                "histAvgFmt": fmt_brl(bundle.hist_avg),
                "diffVsRefPct": diff_vs_ref_pct,
                "isBelowTarget": is_below_target,
                "isAllTimeLow": is_all_time_low,
                "hasLiveQuote": live_price is not None,
                "bestStore": best_offer["marketplace"] if best_offer else "Referência Inicial",
                "bestUrl": best_offer["url"] if best_offer else "",
                "bestUpdated": best_offer["coletado_em"] if best_offer else "Base 2026",
                "storeOffers": bundle.store_offers,
                "storeSeries": bundle.store_series,
                "recordsCount": len(bundle.records_asc),
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

        timeline_labels = self.build_timeline_series(
            all_buckets,
            per_monitor_buckets,
            monitors_payload,
            baseline_label="Ref. Inicial",
            baseline_key="priceMinRef",
            freshness_hours=DEFAULT_FRESHNESS_HOURS,
        )

        qhd_gamer_models = [
            m for m in monitors_payload if m["res"] == "QHD" and m["refresh"] >= 144
        ]
        best_qhd_gamer = (
            min(qhd_gamer_models, key=lambda x: x["effectivePrice"]) if qhd_gamer_models else None
        )
        best_overall = (
            min(monitors_payload, key=lambda x: x["effectivePrice"]) if monitors_payload else None
        )

        kpis = {
            "best_qhd_gamer_price": (
                fmt_brl(best_qhd_gamer["effectivePrice"]) if best_qhd_gamer else "R$ 1.102,00"
            ),
            "best_qhd_gamer_name": (
                best_qhd_gamer["name"] if best_qhd_gamer else "ASUS ROG Strix XG27ACS"
            ),
            "best_overall_price": (
                fmt_brl(best_overall["effectivePrice"]) if best_overall else "R$ 836,00"
            ),
            "best_overall_name": (
                best_overall["name"] if best_overall else 'HQ Pro 27" HQ27AJ75G'
            ),
            "deals_count": sum(1 for m in monitors_payload if m["isBelowTarget"]),
            "live_tracked_count": sum(1 for m in monitors_payload if m["hasLiveQuote"]),
            "total_monitors": len(monitors_payload),
            "total_cycles": max(len(cycle_logs), len(all_buckets)),
            "total_db_records": total_db_records,
            "days_to_bf": max(0, (BLACK_FRIDAY_2026.date() - now_local.date()).days),
            "last_updated": now_local.strftime("%d/%m/%Y às %H:%M (America/Recife)"),
        }

        template = self.env.get_template("monitors_27_dashboard.html")
        html_content = template.render(
            kpis=kpis,
            monitors_json=self.safe_script_json(monitors_payload),
            timeline_labels_json=self.safe_script_json(timeline_labels),
            cycle_logs_json=self.safe_script_json(cycle_logs[-20:][::-1]),
            monitors=monitors_payload,
            cycle_logs=cycle_logs[-10:][::-1],
        )
        md_content = self._build_markdown_report(kpis, monitors_payload, cycle_logs)

        return self.write_outputs(
            html_content=html_content,
            md_content=md_content,
            output_html_path=output_html_path,
            output_md_path=output_md_path,
            open_browser=open_browser,
            banner_label="📊 Painel Black Friday (Monitores 27\")",
        )

    @staticmethod
    def _build_markdown_report(
        kpis: dict[str, Any],
        monitors: list[dict[str, Any]],
        cycle_logs: list[dict[str, Any]],
    ) -> str:
        lines = [
            '# 📊 Relatório Incremental Black Friday 2026 — Monitores 27" Ergonômicos',
            "",
            f"- **Última atualização:** {kpis['last_updated']}",
            f"- **Contagem regressiva Black Friday (27/11/2026):** {kpis['days_to_bf']} dias",
            f"- **Rodadas acumuladas:** {kpis['total_cycles']} | **Cotações no SQLite:** {kpis['total_db_records']}",
            (
                f"- **Monitores com cotação ao vivo:** {kpis['live_tracked_count']}/{kpis['total_monitors']} | "
                f"**Abaixo do Alvo:** {kpis['deals_count']}"
            ),
            f"- **Menor QHD Gamer (144Hz+) atual:** {kpis['best_qhd_gamer_price']} ({kpis['best_qhd_gamer_name']})",
            "",
            "## 🏆 Tabela Consolidada de Preços (Ordenada por Menor Valor Atual)",
            "",
            "| Monitor | Res / Hz | Preço Atual | Loja | Alvo BF | Mín. Histórica | Deal Score | Z-Score (MAD) | Status |",
            "| :--- | :---: | :---: | :--- | :---: | :---: | :---: | :---: | :--- |",
        ]

        for m in sorted(monitors, key=lambda x: x["effectivePrice"]):
            store_cell = f"[{m['bestStore']}]({m['bestUrl']})" if m["bestUrl"] else m["bestStore"]
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
                checked = log.get("items_checked", log.get("monitors_checked", 0))
                lines.append(
                    f"| #{log.get('run_number', '?')} | {log.get('timestamp_local', '—')} | "
                    f"{checked} | {log.get('sources_checked', 0)} | "
                    f"{log.get('quotes_collected', 0)} | {log.get('deals_found', 0)} |"
                )
        else:
            lines.append(f"| #0 | Base Inicial | {kpis['total_monitors']} | — | — | — |")

        lines.append("")
        return "\n".join(lines)
