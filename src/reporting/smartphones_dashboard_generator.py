"""Gerador do Dashboard Interativo e Relatório Incremental de Smartphones 512 GB (Black Friday)."""

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

BUDGET_CEILING = 3000.0
FRESHNESS_WINDOW_HOURS = DEFAULT_FRESHNESS_HOURS

PROFILE_LABELS = {
    "geral": "Melhor Escolha Geral",
    "fotografia": "Fotografia",
    "longevidade": "Longevidade de Software",
    "gamer": "Jogos / Desempenho",
    "bateria": "Bateria Extrema",
    "compacto": "Compacto",
    "economia": "Economia (< R$ 2.500)",
}


def compute_benefit_score(specs: dict[str, Any]) -> dict[str, float]:
    """Calcula o Índice de Benefício (0–100) a partir das notas editoriais e da ficha técnica."""
    scores = specs.get("scores", {}) or {}
    perf = float(scores.get("performance", 5.0)) * 3.0
    camera = float(scores.get("camera", 5.0)) * 2.5
    display = float(scores.get("display", 5.0)) * 1.0

    battery_mah = float(specs.get("battery_mah") or 0)
    charge_w = float(specs.get("charge_w") or 0)
    battery = min(battery_mah / 7000.0, 1.0) * 10.0 + min(charge_w / 120.0, 1.0) * 5.0

    software = min(float(specs.get("updates_years") or 0) / 7.0, 1.0) * 10.0

    ip = str(specs.get("ip") or "").upper()
    if "IP68" in ip:
        ip_pts = 5.0
    elif "IP67" in ip or "IP65" in ip:
        ip_pts = 2.5
    elif "IP64" in ip:
        ip_pts = 1.5
    else:
        ip_pts = 0.0

    ram = int(specs.get("ram_gb") or 0)
    ram_pts = 2.5 if ram >= 12 else (1.25 if ram >= 8 else 0.0)
    storage = str(specs.get("storage_type") or "")
    if "4.0" in storage:
        ufs_pts = 2.5
    elif "3.1" in storage:
        ufs_pts = 1.5
    elif "2.2" in storage:
        ufs_pts = 0.5
    else:
        ufs_pts = 1.0

    build = ip_pts + ram_pts + ufs_pts
    breakdown = {
        "desempenho": round(perf, 1),
        "cameras": round(camera, 1),
        "bateria": round(battery, 1),
        "software": round(software, 1),
        "tela": round(display, 1),
        "construcao": round(build, 1),
    }
    breakdown["total"] = round(sum(breakdown.values()), 1)
    return breakdown


class SmartphonesDashboardGenerator(BaseCategoryDashboardGenerator):
    """Compila o painel HTML evolutivo e o relatório Markdown de smartphones 512 GB."""

    def __init__(
        self,
        repository: Repository | None = None,
        config_path: str | Path = "src/config/smartphones_512.yaml",
        cycles_log_path: str | Path = "data/smartphones_512_cycles.jsonl",
    ):
        super().__init__(
            repository=repository,
            config_path=config_path,
            cycles_log_path=cycles_log_path,
        )

    def generate(
        self,
        output_html_path: str | Path = "reports/celulares_512gb_black_friday.html",
        output_md_path: str | Path = "reports/celulares_512gb_summary.md",
        open_browser: bool = False,
    ) -> Path:
        """Gera o dashboard HTML interativo e o relatório Markdown incremental."""
        catalog = self.load_catalog_config()
        cycle_logs = self.load_cycle_logs()
        now_local = datetime.now(timezone.utc).astimezone(RECIFE_TZ)

        phones: list[dict[str, Any]] = []
        all_buckets: set[str] = set()
        per_phone_buckets: dict[str, dict[str, dict[str, float]]] = {}
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
            per_phone_buckets[pid] = bundle.mkt_bucket_min

            live_price = bundle.live_price
            effective_price = bundle.effective_price
            best = bundle.best_offer
            stat_profile = bundle.stat_profile

            benefit = compute_benefit_score(specs)
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
            elif live_price is not None:
                status_key, status_badge = "tracked", "✅ Monitorado"
            else:
                status_key, status_badge = "baseline", "⏳ Sem Cotação"

            phones.append({
                "id": pid,
                "name": item["nome"],
                "brand": specs.get("brand", ""),
                "category": specs.get("category", ""),
                "profiles": specs.get("profiles", []),
                "tag": specs.get("tag", ""),
                "estimated": bool(specs.get("estimated", False)),
                "soc": specs.get("soc", "—"),
                "ramGb": specs.get("ram_gb"),
                "ramType": specs.get("ram_type", "—"),
                "storageType": specs.get("storage_type", "—"),
                "display": specs.get("display", "—"),
                "camera": specs.get("camera", "—"),
                "selfie": specs.get("selfie", "—"),
                "batteryMah": specs.get("battery_mah"),
                "chargeW": specs.get("charge_w"),
                "wirelessW": specs.get("wireless_w"),
                "ip": specs.get("ip", "—"),
                "updatesYears": specs.get("updates_years"),
                "updatesNote": specs.get("updates_note", ""),
                "weightG": specs.get("weight_g"),
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
            per_phone_buckets,
            phones,
            baseline_label="Ref. Pesquisa",
            baseline_key="priceRegularRef",
            freshness_hours=FRESHNESS_WINDOW_HOURS,
        )

        ranked = sorted(phones, key=lambda p: p["cbIndex"], reverse=True)
        for pos, ph in enumerate(ranked, start=1):
            ph["cbRank"] = pos
        live = [p for p in phones if p["hasLiveQuote"]]
        cheapest = min(live or phones, key=lambda p: p["effectivePrice"]) if phones else None
        best_cb = ranked[0] if ranked else None
        flagships_under = [
            p
            for p in live
            if p["category"] == "Topo de Linha Depreciado"
            and p["effectivePrice"] <= BUDGET_CEILING
        ]
        best_flagship = (
            max(flagships_under, key=lambda p: p["benefit"]["total"]) if flagships_under else None
        )

        kpis = {
            "best_cb_name": best_cb["name"] if best_cb else "—",
            "best_cb_index": best_cb["cbIndex"] if best_cb else 0,
            "best_cb_price": best_cb["effectivePriceFmt"] if best_cb else "—",
            "cheapest_name": cheapest["name"] if cheapest else "—",
            "cheapest_price": cheapest["effectivePriceFmt"] if cheapest else "—",
            "best_flagship_name": (
                best_flagship["name"]
                if best_flagship
                else "Nenhum topo de linha ≤ R$ 3.000 agora"
            ),
            "best_flagship_price": best_flagship["effectivePriceFmt"] if best_flagship else "—",
            "deals_count": sum(1 for p in phones if p["isBelowTarget"]),
            "under_budget_count": sum(1 for p in live if p["effectivePrice"] <= BUDGET_CEILING),
            "live_tracked_count": len(live),
            "total_phones": len(phones),
            "total_cycles": max(len(cycle_logs), len(all_buckets)),
            "total_db_records": total_db_records,
            "days_to_bf": max(0, (BLACK_FRIDAY_2026.date() - now_local.date()).days),
            "last_updated": now_local.strftime("%d/%m/%Y às %H:%M (America/Recife)"),
        }

        template = self.env.get_template("smartphones_512_dashboard.html")
        html_content = template.render(
            kpis=kpis,
            phones=ranked,
            phones_json=self.safe_script_json(phones),
            timeline_labels_json=self.safe_script_json(timeline_labels),
            profiles_json=self.safe_script_json(PROFILE_LABELS),
            cycle_logs=cycle_logs[-10:][::-1],
            budget=BUDGET_CEILING,
        )
        md_content = self._build_phone_markdown(kpis, ranked, cycle_logs)

        return self.write_outputs(
            html_content=html_content,
            md_content=md_content,
            output_html_path=output_html_path,
            output_md_path=output_md_path,
            open_browser=open_browser,
            banner_label="📱 Painel de celulares 512 GB",
        )

    @staticmethod
    def _build_phone_markdown(
        kpis: dict[str, Any],
        ranked: list[dict[str, Any]],
        cycle_logs: list[dict[str, Any]],
    ) -> str:
        lines = [
            "# 📱 Relatório Incremental Black Friday 2026 — Smartphones 512 GB (faixa R$ 3.000)",
            "",
            f"- **Última atualização:** {kpis['last_updated']}",
            f"- **Contagem regressiva Black Friday (27/11/2026):** {kpis['days_to_bf']} dias",
            f"- **Rodadas acumuladas:** {kpis['total_cycles']} | **Cotações no SQLite:** {kpis['total_db_records']}",
            (
                f"- **Aparelhos com cotação ao vivo:** {kpis['live_tracked_count']}/{kpis['total_phones']} | "
                f"**Abaixo do Alvo:** {kpis['deals_count']} | **≤ R$ 3.000 agora:** {kpis['under_budget_count']}"
            ),
            (
                f"- **🏆 Melhor custo-benefício:** {kpis['best_cb_name']} — {kpis['best_cb_price']} "
                f"({kpis['best_cb_index']} pts/R$ 1.000)"
            ),
            f"- **💰 Menor preço 512 GB:** {kpis['cheapest_name']} — {kpis['cheapest_price']}",
            f"- **👑 Melhor topo de linha ≤ R$ 3.000:** {kpis['best_flagship_name']} {kpis['best_flagship_price']}",
            "",
            "## 🏆 Ranking Custo-Benefício e Oportunidade Black Friday",
            "",
            "| # | Aparelho | Preço Atual | Loja | Benefício | Deal Score | Oportunidade BF | Z-Score (MAD) | Pts/R$1k | Status |",
            "| :---: | :--- | :---: | :--- | :---: | :---: | :---: | :---: | :---: | :--- |",
        ]
        for ph in ranked:
            store = f"[{ph['bestStore']}]({ph['bestUrl']})" if ph["bestUrl"] else ph["bestStore"]
            price = (
                f"**{ph['effectivePriceFmt']}**"
                if ph["hasLiveQuote"]
                else f"_{ph['effectivePriceFmt']} (ref.)_"
            )
            est = " ⚠️" if ph["estimated"] else ""
            deal_s = f"{ph['dealScore']:.0f}/100" if ph.get("dealScore") is not None else "—"
            bf_opp = f"{ph['bfOpportunityScore']:.1f}" if ph.get("bfOpportunityScore") is not None else "—"
            z_val = f"{ph['robustZScore']:+.2f}" if ph.get("robustZScore") is not None else "0.00"
            lines.append(
                f"| {ph['cbRank']} | **{ph['name']}**{est} | {price} | {store} | {ph['benefit']['total']} | "
                f"`{deal_s}` | **`{bf_opp}`** | `{z_val}` | {ph['cbIndex']} | {ph['statusBadge']} |"
            )
        lines.extend([
            "",
            (
                "> ⚠️ = ficha técnica parcial na pesquisa (notas estimadas). Sem cotação ao vivo, usa-se o preço "
                "regular da pesquisa (conservador)."
            ),
            "",
            "## ⏱️ Histórico Recente de Execuções",
            "",
            "| Ciclo | Data / Hora (Recife) | Aparelhos | Fontes | Cotações Válidas | Oportunidades |",
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
