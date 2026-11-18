"""Gerador do Dashboard Interativo e Relatório Incremental de Smartwatches (Black Friday R$ 800 a R$ 1.200)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.data.repository import Repository
from src.reporting.category_base import (
    BLACK_FRIDAY_2026,
    CATEGORY_PALETTE,
    DEFAULT_FRESHNESS_HOURS,
    RECIFE_TZ,
    BaseCategoryDashboardGenerator,
    fmt_brl,
)

BUDGET_CEILING = 1200.0
BUDGET_FLOOR = 800.0
FRESHNESS_WINDOW_HOURS = DEFAULT_FRESHNESS_HOURS

SMARTWATCH_PROFILES = {
    "corrida": "Corrida & Performance (Maratona / Asfalto)",
    "hibrido_lifestyle": "Híbrido Esporte & Dia a Dia (iOS / Android)",
    "smart_wearos": "Wear OS & Mini-Smartphone (Apps / Google Pay)",
    "bateria_extrema": "Bateria Extrema (14 a 21 dias)",
    "custo_beneficio_piso": "Piso do Orçamento (~R$ 800)",
    "pagamentos_nfc": "Pagamentos por Aproximação Universais",
}


def compute_smartwatch_benefit_score(specs: dict[str, Any]) -> dict[str, float]:
    """Calcula o Índice de Benefício Vestível (0–100)."""
    scores = specs.get("scores", {}) or {}
    gps_running = float(scores.get("gps_running", 7.0)) * 3.0
    health_sensors = float(scores.get("health_sensors", 7.0)) * 2.0
    battery = float(scores.get("battery", 7.0)) * 2.0
    build_ergonomics = float(scores.get("build_ergonomics", 7.0)) * 1.5
    ecosystem_smart = float(scores.get("ecosystem_smart", 7.0)) * 1.5

    breakdown = {
        "gps_corrida": round(gps_running, 1),
        "sensores_saude": round(health_sensors, 1),
        "bateria_autonomia": round(battery, 1),
        "construcao_ergonomia": round(build_ergonomics, 1),
        "ecossistema_smart": round(ecosystem_smart, 1),
    }
    breakdown["total"] = round(sum(breakdown.values()), 1)
    return breakdown


class SmartwatchesDashboardGenerator(BaseCategoryDashboardGenerator):
    """Compila o painel HTML evolutivo e o relatório Markdown de smartwatches (R$ 800 a R$ 1.200)."""

    def __init__(
        self,
        repository: Repository | None = None,
        config_path: str | Path = "src/config/smartwatches_800_1200.yaml",
        cycles_log_path: str | Path = "data/smartwatches_cycles.jsonl",
    ):
        super().__init__(
            repository=repository,
            config_path=config_path,
            cycles_log_path=cycles_log_path,
        )

    def generate(
        self,
        output_html_path: str | Path = "reports/smartwatches_black_friday.html",
        output_md_path: str | Path = "reports/smartwatches_summary.md",
        open_browser: bool = False,
    ) -> Path:
        """Gera o dashboard HTML interativo e o relatório Markdown incremental."""
        catalog = self.load_catalog_config()
        cycle_logs = self.load_cycle_logs()
        now_local = datetime.now(timezone.utc).astimezone(RECIFE_TZ)

        watches: list[dict[str, Any]] = []
        all_buckets: set[str] = set()
        per_watch_buckets: dict[str, dict[str, dict[str, float]]] = {}
        total_db_records = 0

        for idx, item in enumerate(catalog):
            pid = item["id"]
            specs = item.get("specs", {}) or {}
            preco_alvo = float(item["preco_alvo"])
            preco_maximo = float(item["preco_maximo"])
            floor_ref = float(specs.get("price_floor_ref") or preco_alvo)
            regular_ref = float(specs.get("price_regular_ref") or preco_maximo)

            bundle = self.collect_product_history(
                item,
                now_local=now_local,
                fallback_ref_price=regular_ref,
                freshness_hours=FRESHNESS_WINDOW_HOURS,
            )
            total_db_records += len(bundle.records_asc)
            all_buckets.update(bundle.mkt_bucket_min.keys())
            per_watch_buckets[pid] = bundle.mkt_bucket_min

            live_price = bundle.live_price
            effective_price = bundle.effective_price
            best = bundle.best_offer
            stat_profile = bundle.stat_profile

            benefit = compute_smartwatch_benefit_score(specs)
            cb_index = (
                round(benefit["total"] / (effective_price / 1000.0), 1)
                if effective_price
                else 0.0
            )
            bf_opp_score = round(
                (0.55 * benefit["total"]) + (0.45 * stat_profile.deal_confidence_score), 1
            )

            is_below_target = bool(live_price is not None and live_price <= preco_alvo)
            is_under_budget = bool(effective_price <= BUDGET_CEILING)
            is_all_time_low = bool(
                live_price is not None
                and bundle.hist_min is not None
                and len(bundle.records_asc) > 1
                and live_price <= bundle.hist_min
            )

            if is_below_target:
                status_key, status_badge = "deal", "🎯 Abaixo do Alvo"
            elif live_price is not None and live_price <= floor_ref:
                status_key, status_badge = "floor", "📉 No Piso Histórico"
            elif live_price is not None and is_under_budget:
                status_key, status_badge = "budget", "✅ No Orçamento"
            elif live_price is not None:
                status_key, status_badge = "tracked", "🔍 Monitorado"
            else:
                status_key, status_badge = "baseline", "⏳ Sem Cotação"

            watches.append({
                "id": pid,
                "name": item["nome"],
                "brand": specs.get("brand", ""),
                "category": specs.get("category", ""),
                "rankPosition": specs.get("rank_position", idx + 1),
                "profiles": specs.get("profiles", []),
                "tag": specs.get("tag", ""),
                "display": specs.get("display", "—"),
                "materials": specs.get("materials", "—"),
                "weightG": specs.get("weight_g"),
                "gnss": specs.get("gnss", "—"),
                "sensors": specs.get("sensors", "—"),
                "batteryDays": specs.get("battery_days"),
                "batteryRealDays": specs.get("battery_real_days"),
                "gpsHours": specs.get("gps_hours"),
                "chargeType": specs.get("charge_type", "—"),
                "waterResistance": specs.get("water_resistance", "—"),
                "osApps": specs.get("os_apps", "—"),
                "strava": specs.get("strava", "—"),
                "nfc": specs.get("nfc", "—"),
                "pros": specs.get("pros", []),
                "cons": specs.get("cons", []),
                "priceLaunch": specs.get("price_launch"),
                "priceRegularRef": regular_ref,
                "priceFloorRef": floor_ref,
                "priceTarget": preco_alvo,
                "priceMax": preco_maximo,
                "livePrice": live_price,
                "effectivePrice": round(effective_price, 2),
                "effectivePriceFmt": fmt_brl(effective_price),
                "priceTargetFmt": fmt_brl(preco_alvo),
                "priceFloorRefFmt": fmt_brl(floor_ref),
                "priceRegularRefFmt": fmt_brl(regular_ref),
                "histMin": round(bundle.hist_min, 2) if bundle.hist_min is not None else None,
                "histMinFmt": fmt_brl(bundle.hist_min),
                "hasLiveQuote": live_price is not None,
                "isBelowTarget": is_below_target,
                "isUnderBudget": is_under_budget,
                "isAllTimeLow": is_all_time_low,
                "statusKey": status_key,
                "statusBadge": status_badge,
                "bestStore": best["marketplace"] if best else "Ref. da pesquisa",
                "bestUrl": best["url"] if best else "",
                "bestUpdated": best["coletado_em"] if best else "—",
                "storeOffers": bundle.store_offers,
                "recordsCount": len(bundle.records_asc),
                "benefit": benefit,
                "cbIndex": cb_index,
                "dealScore": stat_profile.deal_confidence_score,
                "robustZScore": stat_profile.robust_z_score,
                "percentileRank": stat_profile.percentile_rank,
                "bfOpportunityScore": bf_opp_score,
                "priceRegime": stat_profile.regime_preco,
                "color": CATEGORY_PALETTE[idx % len(CATEGORY_PALETTE)],
            })

        timeline_labels = self.build_timeline_series(
            all_buckets,
            per_watch_buckets,
            watches,
            baseline_label="Ref. Pesquisa",
            baseline_key="priceRegularRef",
            freshness_hours=FRESHNESS_WINDOW_HOURS,
        )

        ranked = sorted(watches, key=lambda w: w["cbIndex"], reverse=True)
        for pos, w in enumerate(ranked, start=1):
            w["cbRank"] = pos

        live = [w for w in watches if w["hasLiveQuote"]]
        best_cb = ranked[0] if ranked else None
        cheapest = min(live or watches, key=lambda w: w["effectivePrice"]) if watches else None
        runner2 = next((w for w in watches if w["id"] == "huawei-gt-runner-2"), None)
        wearos_models = [w for w in (live or watches) if "smart_wearos" in w["profiles"]]
        best_wearos = (
            min(wearos_models, key=lambda w: w["effectivePrice"]) if wearos_models else None
        )

        kpis = {
            "best_cb_name": best_cb["name"] if best_cb else "—",
            "best_cb_index": best_cb["cbIndex"] if best_cb else 0,
            "best_cb_price": best_cb["effectivePriceFmt"] if best_cb else "—",
            "runner2_price": runner2["effectivePriceFmt"] if runner2 else "—",
            "runner2_status": runner2["statusBadge"] if runner2 else "—",
            "runner2_target": runner2["priceTargetFmt"] if runner2 else "—",
            "runner2_benefit": runner2["benefit"]["total"] if runner2 else 0,
            "best_wearos_name": best_wearos["name"] if best_wearos else "—",
            "best_wearos_price": best_wearos["effectivePriceFmt"] if best_wearos else "—",
            "cheapest_name": cheapest["name"] if cheapest else "—",
            "cheapest_price": cheapest["effectivePriceFmt"] if cheapest else "—",
            "deals_count": sum(1 for w in watches if w["isBelowTarget"]),
            "under_budget_count": sum(
                1 for w in (live or watches) if w["effectivePrice"] <= BUDGET_CEILING
            ),
            "live_tracked_count": len(live),
            "total_watches": len(watches),
            "total_cycles": max(len(cycle_logs), len(all_buckets)),
            "total_db_records": total_db_records,
            "days_to_bf": max(0, (BLACK_FRIDAY_2026.date() - now_local.date()).days),
            "last_updated": now_local.strftime("%d/%m/%Y às %H:%M (America/Recife)"),
        }

        template = self.env.get_template("smartwatches_dashboard.html")
        html_content = template.render(
            kpis=kpis,
            watches=ranked,
            watches_json=self.safe_script_json(watches),
            timeline_labels_json=self.safe_script_json(timeline_labels),
            profiles_json=self.safe_script_json(SMARTWATCH_PROFILES),
            cycle_logs=cycle_logs[-10:][::-1],
            budget_max=BUDGET_CEILING,
            budget_min=BUDGET_FLOOR,
        )
        md_content = self._build_watch_markdown(kpis, ranked, cycle_logs)

        return self.write_outputs(
            html_content=html_content,
            md_content=md_content,
            output_html_path=output_html_path,
            output_md_path=output_md_path,
            open_browser=open_browser,
            banner_label="⌚ Painel de smartwatches",
        )

    @staticmethod
    def _build_watch_markdown(
        kpis: dict[str, Any],
        ranked: list[dict[str, Any]],
        cycle_logs: list[dict[str, Any]],
    ) -> str:
        lines = [
            "# ⌚ Relatório Incremental Black Friday 2026 — Smartwatches (R$ 800 a R$ 1.200)",
            "",
            f"- **Última atualização:** {kpis['last_updated']}",
            f"- **Contagem regressiva Black Friday (27/11/2026):** {kpis['days_to_bf']} dias",
            f"- **Rodadas acumuladas:** {kpis['total_cycles']} | **Cotações no SQLite:** {kpis['total_db_records']}",
            (
                f"- **Relógios com cotação ao vivo:** {kpis['live_tracked_count']}/{kpis['total_watches']} | "
                f"**Abaixo do Alvo:** {kpis['deals_count']} | **Na faixa de R$ 800 a R$ 1.200:** {kpis['under_budget_count']}"
            ),
            (
                f"- **🏃 HUAWEI WATCH GT Runner 2 (Foco):** {kpis['runner2_price']} "
                f"(Alvo: {kpis['runner2_target']} | Benefício: {kpis['runner2_benefit']}/100)"
            ),
            (
                f"- **🏆 Melhor custo-benefício geral:** {kpis['best_cb_name']} — {kpis['best_cb_price']} "
                f"({kpis['best_cb_index']} pts/R$ 1.000)"
            ),
            f"- **🤖 Melhor Wear OS (Smart/Google Pay):** {kpis['best_wearos_name']} — {kpis['best_wearos_price']}",
            f"- **💰 Menor preço no piso:** {kpis['cheapest_name']} — {kpis['cheapest_price']}",
            "",
            "## 🏆 Ranking Custo-Benefício Vestível e Oportunidade Black Friday",
            "",
            "| # | Smartwatch | Preço Atual | Loja | Benefício | Deal Score | Oportunidade BF | Z-Score (MAD) | Pts/R$1k | Status |",
            "| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |",
        ]
        for w in ranked:
            store = f"[{w['bestStore']}]({w['bestUrl']})" if w["bestUrl"] else w["bestStore"]
            price = (
                f"**{w['effectivePriceFmt']}**"
                if w["hasLiveQuote"]
                else f"_{w['effectivePriceFmt']} (ref.)_"
            )
            highlight = " 🏃" if "gt-runner-2" in w["id"] else ""
            deal_s = f"{w['dealScore']:.0f}/100" if w.get("dealScore") is not None else "—"
            bf_opp = f"{w['bfOpportunityScore']:.1f}" if w.get("bfOpportunityScore") is not None else "—"
            z_val = f"{w['robustZScore']:+.2f}" if w.get("robustZScore") is not None else "0.00"
            lines.append(
                f"| {w['cbRank']} | **{w['name']}**{highlight} | {price} | {store} | {w['benefit']['total']} | "
                f"`{deal_s}` | **`{bf_opp}`** | `{z_val}` | {w['cbIndex']} | {w['statusBadge']} |"
            )
        lines.extend([
            "",
            "## ⏱️ Histórico Recente de Execuções",
            "",
            "| Ciclo | Data / Hora (Recife) | Relógios | Fontes | Cotações Válidas | Oportunidades |",
            "| :---: | :---: | :---: | :---: | :---: | :---: |",
        ])
        for log in cycle_logs[-15:][::-1]:
            checked = log.get("items_checked", log.get("monitors_checked", 0))
            lines.append(
                f"| #{log.get('run_number', '?')} | {log.get('timestamp_local', '—')} | "
                f"{checked} | {log.get('sources_checked', 0)} | "
                f"{log.get('quotes_collected', 0)} | {log.get('deals_found', 0)} |"
            )
        if not cycle_logs:
            lines.append("| #0 | Base Inicial (pesquisa) | — | — | — | — |")
        lines.append("")
        return "\n".join(lines)
