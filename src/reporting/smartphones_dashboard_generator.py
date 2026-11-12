"""Gerador do Dashboard Interativo e Relatório Incremental de Smartphones 512 GB (Black Friday).

Reaproveita o log incremental de ciclos do gerador de monitores e acrescenta o
Índice de Benefício (0–100) e o Custo-Benefício (pontos por R$ 1.000) de cada aparelho.
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
BUDGET_CEILING = 3000.0
FRESHNESS_WINDOW_HOURS = 96

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
    """Calcula o Índice de Benefício (0–100) a partir das notas editoriais e da ficha técnica.

    Pesos: Desempenho 30 | Câmeras 25 | Bateria+Recarga 15 | Software 10 | Tela 10 | Construção/Memória 10.
    """
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


class SmartphonesDashboardGenerator(MonitorsDashboardGenerator):
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
            sources = self.repository.get_sources_for_product(pid)
            source_map = {s.id: s for s in sources if s.id is not None}

            history: list[PriceRecord] = self.repository.get_price_history(pid, days=120)
            history_asc = sorted(history, key=lambda r: r.coletado_em)
            total_db_records += len(history_asc)

            preco_alvo = float(item["preco_alvo"])
            preco_maximo = float(item["preco_maximo"])
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
            per_phone_buckets[pid] = dict(mkt_bucket_min)

            # Só considera ofertas "vivas" (vistas na janela de frescor) para o preço atual
            fresh_offers = [
                o for o in latest_by_mkt.values()
                if (now_local - o["seen_at"]).total_seconds() <= FRESHNESS_WINDOW_HOURS * 3600
            ]
            store_offers = sorted(
                ({k: v for k, v in o.items() if k != "seen_at"} for o in fresh_offers),
                key=lambda x: x["preco"],
            )
            best = store_offers[0] if store_offers else None

            preco_alvo = float(item["preco_alvo"])
            preco_maximo = float(item["preco_maximo"])
            floor_ref = float(specs.get("price_floor_ref") or preco_alvo)
            regular_ref = float(specs.get("price_regular_ref") or preco_maximo)
            hist_min = self.repository.get_historical_min_price(pid)

            live_price = best["preco"] if best else None
            # Sem cotação viva, usa o preço regular da pesquisa (conservador) para o custo-benefício
            effective_price = live_price if live_price is not None else regular_ref

            benefit = compute_benefit_score(specs)
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

        # Linha do tempo: "Ref. Pesquisa" (preço regular) + uma coluna por janela horária coletada
        sorted_buckets = sorted(all_buckets)
        bucket_dts = [datetime.strptime(b, "%Y-%m-%d %H:00").replace(tzinfo=RECIFE_TZ) for b in sorted_buckets]
        timeline_labels = ["Ref. Pesquisa"] + [dt.strftime("%d/%m %Hh") for dt in bucket_dts]
        for ph in phones:
            buckets = per_phone_buckets.get(ph["id"], {})
            values: list[float | None] = [ph["priceRegularRef"]]
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
            ph["timelineValues"] = values

        # Rankings e KPIs
        ranked = sorted(phones, key=lambda p: p["cbIndex"], reverse=True)
        for pos, ph in enumerate(ranked, start=1):
            ph["cbRank"] = pos
        live = [p for p in phones if p["hasLiveQuote"]]
        cheapest = min(live or phones, key=lambda p: p["effectivePrice"]) if phones else None
        best_cb = ranked[0] if ranked else None
        flagships_under = [
            p for p in live
            if p["category"] == "Topo de Linha Depreciado" and p["effectivePrice"] <= BUDGET_CEILING
        ]
        best_flagship = max(flagships_under, key=lambda p: p["benefit"]["total"]) if flagships_under else None

        kpis = {
            "best_cb_name": best_cb["name"] if best_cb else "—",
            "best_cb_index": best_cb["cbIndex"] if best_cb else 0,
            "best_cb_price": best_cb["effectivePriceFmt"] if best_cb else "—",
            "cheapest_name": cheapest["name"] if cheapest else "—",
            "cheapest_price": cheapest["effectivePriceFmt"] if cheapest else "—",
            "best_flagship_name": best_flagship["name"] if best_flagship else "Nenhum topo de linha ≤ R$ 3.000 agora",
            "best_flagship_price": best_flagship["effectivePriceFmt"] if best_flagship else "—",
            "deals_count": sum(1 for p in phones if p["isBelowTarget"]),
            "under_budget_count": sum(1 for p in live if p["effectivePrice"] <= BUDGET_CEILING),
            "live_tracked_count": len(live),
            "total_phones": len(phones),
            "total_cycles": max(len(cycle_logs), len(sorted_buckets)),
            "total_db_records": total_db_records,
            "days_to_bf": max(0, (BLACK_FRIDAY_2026.date() - now_local.date()).days),
            "last_updated": now_local.strftime("%d/%m/%Y às %H:%M (America/Recife)"),
        }

        template = self.env.get_template("smartphones_512_dashboard.html")
        html = template.render(
            kpis=kpis,
            phones=ranked,
            phones_json=json.dumps(phones, ensure_ascii=False),
            timeline_labels_json=json.dumps(timeline_labels, ensure_ascii=False),
            profiles_json=json.dumps(PROFILE_LABELS, ensure_ascii=False),
            cycle_logs=cycle_logs[-10:][::-1],
            budget=BUDGET_CEILING,
        )
        out_html = Path(output_html_path)
        out_html.parent.mkdir(parents=True, exist_ok=True)
        out_html.write_text(html, encoding="utf-8")

        out_md = Path(output_md_path)
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text(self._build_phone_markdown(kpis, ranked, cycle_logs), encoding="utf-8")

        logger.success(f"📱 Painel de celulares 512 GB atualizado: {out_html}")
        logger.info(f"📝 Relatório resumo atualizado: {out_md}")
        if open_browser:
            webbrowser.open(f"file://{out_html.resolve()}")
        return out_html

    @staticmethod
    def _build_phone_markdown(
        kpis: dict[str, Any],
        ranked: list[dict[str, Any]],
        cycle_logs: list[dict[str, Any]],
    ) -> str:
        """Relatório executivo em Markdown ordenado por custo-benefício."""
        lines = [
            "# 📱 Relatório Incremental Black Friday 2026 — Smartphones 512 GB (faixa R$ 3.000)",
            "",
            f"- **Última atualização:** {kpis['last_updated']}",
            f"- **Contagem regressiva Black Friday (27/11/2026):** {kpis['days_to_bf']} dias",
            f"- **Rodadas acumuladas:** {kpis['total_cycles']} | **Cotações no SQLite:** {kpis['total_db_records']}",
            f"- **Aparelhos com cotação ao vivo:** {kpis['live_tracked_count']}/{kpis['total_phones']} | "
            f"**Abaixo do Alvo:** {kpis['deals_count']} | **≤ R$ 3.000 agora:** {kpis['under_budget_count']}",
            f"- **🏆 Melhor custo-benefício:** {kpis['best_cb_name']} — {kpis['best_cb_price']} "
            f"({kpis['best_cb_index']} pts/R$ 1.000)",
            f"- **💰 Menor preço 512 GB:** {kpis['cheapest_name']} — {kpis['cheapest_price']}",
            f"- **👑 Melhor topo de linha ≤ R$ 3.000:** {kpis['best_flagship_name']} {kpis['best_flagship_price']}",
            "",
            "## 🏆 Ranking Custo-Benefício (Índice de Benefício ÷ preço)",
            "",
            "| # | Aparelho | Categoria | Preço Atual | Loja | Alvo BF | Piso Pesquisa | Benefício | Pts/R$1k | Status |",
            "| :---: | :--- | :--- | :---: | :--- | :---: | :---: | :---: | :---: | :--- |",
        ]
        for ph in ranked:
            store = f"[{ph['bestStore']}]({ph['bestUrl']})" if ph["bestUrl"] else ph["bestStore"]
            price = f"**{ph['effectivePriceFmt']}**" if ph["hasLiveQuote"] else f"_{ph['effectivePriceFmt']} (ref.)_"
            est = " ⚠️" if ph["estimated"] else ""
            lines.append(
                f"| {ph['cbRank']} | **{ph['name']}**{est} | {ph['category']} | {price} | {store} | "
                f"{ph['priceTargetFmt']} | {ph['priceFloorRefFmt']} | {ph['benefit']['total']} | "
                f"{ph['cbIndex']} | {ph['statusBadge']} |"
            )
        lines.extend([
            "",
            "> ⚠️ = ficha técnica parcial na pesquisa (notas estimadas). Sem cotação ao vivo, usa-se o preço "
            "regular da pesquisa (conservador).",
            "",
            "## ⏱️ Histórico Recente de Execuções",
            "",
            "| Ciclo | Data / Hora (Recife) | Aparelhos | Fontes | Cotações Válidas | Oportunidades |",
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
