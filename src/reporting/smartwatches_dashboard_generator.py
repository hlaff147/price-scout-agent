"""Gerador do Dashboard Interativo e Relatório Incremental de Smartwatches (Black Friday R$ 800 a R$ 1.200).

Calcula o Índice de Benefício Vestível (0–100) focado em precisão desportiva, sensores de saúde,
bateria e ecossistema inteligente, além do Retorno por R$ 1.000 gastos (Custo-Benefício).
"""

from __future__ import annotations

import json
import webbrowser
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from src.data.models import PriceRecord
from src.data.repository import Repository
from src.reporting.monitors_dashboard_generator import (
    MARKETPLACE_LABELS,
    MONITOR_PALETTE,
    RECIFE_TZ,
    MonitorsDashboardGenerator,
    fmt_brl,
)

BLACK_FRIDAY_2026 = datetime(2026, 11, 27, 0, 0, tzinfo=RECIFE_TZ)
BUDGET_CEILING = 1200.0
BUDGET_FLOOR = 800.0
FRESHNESS_WINDOW_HOURS = 96

SMARTWATCH_PROFILES = {
    "corrida": "Corrida & Performance (Maratona / Asfalto)",
    "hibrido_lifestyle": "Híbrido Esporte & Dia a Dia (iOS / Android)",
    "smart_wearos": "Wear OS & Mini-Smartphone (Apps / Google Pay)",
    "bateria_extrema": "Bateria Extrema (14 a 21 dias)",
    "custo_beneficio_piso": "Piso do Orçamento (~R$ 800)",
    "pagamentos_nfc": "Pagamentos por Aproximação Universais",
}


def compute_smartwatch_benefit_score(specs: dict[str, Any]) -> dict[str, float]:
    """Calcula o Índice de Benefício Vestível (0–100).

    Pesos:
      - Precisão GPS & Corrida: 30 pts (peso 3.0 no score 0-10)
      - Sensores de Saúde & ECG/HRV: 20 pts (peso 2.0 no score 0-10)
      - Autonomia & Bateria: 20 pts (peso 2.0 no score 0-10)
      - Construção, Ergonomia & Proteção: 15 pts (peso 1.5 no score 0-10)
      - Ecossistema, Conectividade & NFC/Strava: 15 pts (peso 1.5 no score 0-10)
    """
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


class SmartwatchesDashboardGenerator(MonitorsDashboardGenerator):
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
            sources = self.repository.get_sources_for_product(pid)
            source_map = {s.id: s for s in sources if s.id is not None}

            history: list[PriceRecord] = self.repository.get_price_history(pid, days=120)
            history_asc = sorted(history, key=lambda r: r.coletado_em)
            total_db_records += len(history_asc)

            preco_alvo = float(item["preco_alvo"])
            preco_maximo = float(item["preco_maximo"])
            # Filtro contra ofertas implausíveis ou itens com preços abusivos
            scalper_ceiling = preco_maximo * 1.65

            latest_by_mkt: dict[str, dict[str, Any]] = {}
            mkt_bucket_min: dict[str, dict[str, float]] = defaultdict(dict)
            for rec in history_asc:
                if rec.preco > scalper_ceiling:
                    continue
                src = source_map.get(rec.source_id)
                mkt_key = src.marketplace if src else "desconhecido"
                local_dt = (
                    rec.coletado_em.astimezone(RECIFE_TZ)
                    if rec.coletado_em.tzinfo
                    else rec.coletado_em.replace(tzinfo=timezone.utc).astimezone(RECIFE_TZ)
                )
                bucket = local_dt.strftime("%Y-%m-%d %H:00")
                all_buckets.add(bucket)
                prev = mkt_bucket_min[bucket].get(mkt_key)
                if prev is None or rec.preco < prev:
                    mkt_bucket_min[bucket][mkt_key] = rec.preco
                latest_by_mkt[mkt_key] = {
                    "marketplace": MARKETPLACE_LABELS.get(mkt_key, mkt_key.upper()),
                    "preco": round(rec.preco, 2),
                    "preco_fmt": fmt_brl(rec.preco),
                    "url": rec.url_encontrada or (src.url_produto if src else ""),
                    "titulo": rec.titulo_coletado or item["nome"],
                    "coletado_em": local_dt.strftime("%d/%m %H:%M"),
                    "seen_at": local_dt,
                }
            per_watch_buckets[pid] = dict(mkt_bucket_min)

            # Ofertas válidas dentro da janela de frescor
            fresh_offers = [
                o for o in latest_by_mkt.values()
                if (now_local - o["seen_at"]).total_seconds() <= FRESHNESS_WINDOW_HOURS * 3600
            ]
            store_offers = sorted(
                ({k: v for k, v in o.items() if k != "seen_at"} for o in fresh_offers),
                key=lambda x: x["preco"],
            )
            best = store_offers[0] if store_offers else None

            floor_ref = float(specs.get("price_floor_ref") or preco_alvo)
            regular_ref = float(specs.get("price_regular_ref") or preco_maximo)
            hist_min = self.repository.get_historical_min_price(pid)

            live_price = best["preco"] if best else None
            effective_price = live_price if live_price is not None else regular_ref

            benefit = compute_smartwatch_benefit_score(specs)
            cb_index = round(benefit["total"] / (effective_price / 1000.0), 1) if effective_price else 0.0

            is_below_target = bool(live_price is not None and live_price <= preco_alvo)
            is_under_budget = bool(effective_price <= BUDGET_CEILING)
            is_all_time_low = bool(
                live_price is not None and hist_min is not None and len(history_asc) > 1 and live_price <= hist_min
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
                "histMin": round(hist_min, 2) if hist_min is not None else None,
                "histMinFmt": fmt_brl(hist_min),
                "hasLiveQuote": live_price is not None,
                "isBelowTarget": is_below_target,
                "isUnderBudget": is_under_budget,
                "isAllTimeLow": is_all_time_low,
                "statusKey": status_key,
                "statusBadge": status_badge,
                "bestStore": best["marketplace"] if best else "Ref. da pesquisa",
                "bestUrl": best["url"] if best else "",
                "bestUpdated": best["coletado_em"] if best else "—",
                "storeOffers": store_offers,
                "recordsCount": len(history_asc),
                "benefit": benefit,
                "cbIndex": cb_index,
                "color": MONITOR_PALETTE[idx % len(MONITOR_PALETTE)],
            })

        # Linha do tempo
        sorted_buckets = sorted(all_buckets)
        bucket_dts = [datetime.strptime(b, "%Y-%m-%d %H:00").replace(tzinfo=RECIFE_TZ) for b in sorted_buckets]
        timeline_labels = ["Ref. Pesquisa"] + [dt.strftime("%d/%m %Hh") for dt in bucket_dts]
        for w in watches:
            buckets = per_watch_buckets.get(w["id"], {})
            values: list[float | None] = [w["priceRegularRef"]]
            active: dict[str, tuple[datetime, float]] = {}
            last_known: float | None = None
            for b, b_dt in zip(sorted_buckets, bucket_dts, strict=True):
                for mkt_key, price in buckets.get(b, {}).items():
                    active[mkt_key] = (b_dt, price)
                fresh = [
                    p for seen, p in active.values()
                    if (b_dt - seen).total_seconds() <= FRESHNESS_WINDOW_HOURS * 3600
                ]
                if fresh:
                    last_known = round(min(fresh), 2)
                values.append(last_known)
            w["timelineValues"] = values

        # Rankings e KPIs
        ranked = sorted(watches, key=lambda w: w["cbIndex"], reverse=True)
        for pos, w in enumerate(ranked, start=1):
            w["cbRank"] = pos

        live = [w for w in watches if w["hasLiveQuote"]]
        best_cb = ranked[0] if ranked else None
        cheapest = min(live or watches, key=lambda w: w["effectivePrice"]) if watches else None
        runner2 = next((w for w in watches if w["id"] == "huawei-gt-runner-2"), None)
        wearos_models = [w for w in (live or watches) if "smart_wearos" in w["profiles"]]
        best_wearos = min(wearos_models, key=lambda w: w["effectivePrice"]) if wearos_models else None

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
            "under_budget_count": sum(1 for w in (live or watches) if w["effectivePrice"] <= BUDGET_CEILING),
            "live_tracked_count": len(live),
            "total_watches": len(watches),
            "total_cycles": max(len(cycle_logs), len(sorted_buckets)),
            "total_db_records": total_db_records,
            "days_to_bf": max(0, (BLACK_FRIDAY_2026.date() - now_local.date()).days),
            "last_updated": now_local.strftime("%d/%m/%Y às %H:%M (America/Recife)"),
        }

        template = self.env.get_template("smartwatches_dashboard.html")
        html = template.render(
            kpis=kpis,
            watches=ranked,
            watches_json=json.dumps(watches, ensure_ascii=False),
            timeline_labels_json=json.dumps(timeline_labels, ensure_ascii=False),
            profiles_json=json.dumps(SMARTWATCH_PROFILES, ensure_ascii=False),
            cycle_logs=cycle_logs[-10:][::-1],
            budget_max=BUDGET_CEILING,
            budget_min=BUDGET_FLOOR,
        )
        out_html = Path(output_html_path)
        out_html.parent.mkdir(parents=True, exist_ok=True)
        out_html.write_text(html, encoding="utf-8")

        out_md = Path(output_md_path)
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text(self._build_watch_markdown(kpis, ranked, cycle_logs), encoding="utf-8")

        logger.success(f"⌚ Painel de smartwatches atualizado: {out_html}")
        logger.info(f"📝 Relatório resumo atualizado: {out_md}")
        if open_browser:
            webbrowser.open(f"file://{out_html.resolve()}")
        return out_html

    @staticmethod
    def _build_watch_markdown(
        kpis: dict[str, Any],
        ranked: list[dict[str, Any]],
        cycle_logs: list[dict[str, Any]],
    ) -> str:
        """Relatório executivo em Markdown ordenado por custo-benefício vestível."""
        lines = [
            "# ⌚ Relatório Incremental Black Friday 2026 — Smartwatches (R$ 800 a R$ 1.200)",
            "",
            f"- **Última atualização:** {kpis['last_updated']}",
            f"- **Contagem regressiva Black Friday (27/11/2026):** {kpis['days_to_bf']} dias",
            f"- **Rodadas acumuladas:** {kpis['total_cycles']} | **Cotações no SQLite:** {kpis['total_db_records']}",
            f"- **Relógios com cotação ao vivo:** {kpis['live_tracked_count']}/{kpis['total_watches']} | "
            f"**Abaixo do Alvo:** {kpis['deals_count']} | **Na faixa de R$ 800 a R$ 1.200:** {kpis['under_budget_count']}",
            f"- **🏃 HUAWEI WATCH GT Runner 2 (Foco):** {kpis['runner2_price']} (Alvo: {kpis['runner2_target']} | Benefício: {kpis['runner2_benefit']}/100)",
            f"- **🏆 Melhor custo-benefício geral:** {kpis['best_cb_name']} — {kpis['best_cb_price']} ({kpis['best_cb_index']} pts/R$ 1.000)",
            f"- **🤖 Melhor Wear OS (Smart/Google Pay):** {kpis['best_wearos_name']} — {kpis['best_wearos_price']}",
            f"- **💰 Menor preço no piso:** {kpis['cheapest_name']} — {kpis['cheapest_price']}",
            "",
            "## 🏆 Ranking Custo-Benefício Vestível (Benefício 0–100 ÷ Preço)",
            "",
            "| # | Smartwatch | Categoria | Preço Atual | Loja | Alvo BF | Piso Pesquisa | Benefício | Pts/R$1k | Status |",
            "| :---: | :--- | :--- | :---: | :--- | :---: | :---: | :---: | :---: | :--- |",
        ]
        for w in ranked:
            store = f"[{w['bestStore']}]({w['bestUrl']})" if w["bestUrl"] else w["bestStore"]
            price = f"**{w['effectivePriceFmt']}**" if w["hasLiveQuote"] else f"_{w['effectivePriceFmt']} (ref.)_"
            highlight = " 🏃" if "gt-runner-2" in w["id"] else ""
            lines.append(
                f"| {w['cbRank']} | **{w['name']}**{highlight} | {w['category']} | {price} | {store} | "
                f"{w['priceTargetFmt']} | {w['priceFloorRefFmt']} | {w['benefit']['total']} | "
                f"{w['cbIndex']} | {w['statusBadge']} |"
            )
        lines.extend([
            "",
            "## ⏱️ Histórico Recente de Execuções",
            "",
            "| Ciclo | Data / Hora (Recife) | Relógios | Fontes | Cotações Válidas | Oportunidades |",
            "| :---: | :---: | :---: | :---: | :---: | :---: |",
        ])
        for log in cycle_logs[-15:][::-1]:
            lines.append(
                f"| #{log.get('run_number', '?')} | {log.get('timestamp_local', '—')} | "
                f"{log.get('monitors_checked', 0)} | {log.get('sources_checked', 0)} | "
                f"{log.get('quotes_collected', 0)} | {log.get('deals_found', 0)} |"
            )
        if not cycle_logs:
            lines.append("| #0 | Base Inicial (pesquisa) | — | — | — | — |")
        lines.append("")
        return "\n".join(lines)
