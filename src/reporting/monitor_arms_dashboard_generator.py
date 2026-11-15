"""Gerador do Dashboard Interativo e Relatório Incremental de Suportes Articulados para Monitores (1 e 2 Telas, Mesa 5 cm Sem Furos).

Calcula o Índice de Benefício Ergonômico (0–100) focado em durabilidade do mecanismo,
compatibilidade confirmada com borda de 5 cm (50 mm), ergonomia, capacidade de carga e garantia,
além do Retorno por R$ 100 gastos (Custo-Benefício).
"""

from __future__ import annotations

import json
import webbrowser
from collections import defaultdict
from datetime import datetime
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
FRESHNESS_WINDOW_HOURS = 96

ARM_PROFILES = {
    "1_monitor": "1 Monitor (Braço Individual)",
    "2_monitores": "2 Monitores (Braço Duplo)",
    "mesa_5cm_confirmada": "Compatível 5 cm Confirmado (≥ 70 mm)",
    "custo_beneficio": "Melhor Custo-Benefício Geral",
    "telas_pesadas": "Telas Pesadas (até 12 kg / braço)",
    "economico": "Setup Econômico",
}


def compute_arm_benefit_score(specs: dict[str, Any]) -> dict[str, float]:
    """Calcula o Índice de Benefício Ergonômico (0–100).

    Pesos:
      - Mecanismo & Durabilidade: 30 pts (peso 3.0)
      - Compatibilidade Morsa 5 cm: 25 pts (peso 2.5)
      - Ergonomia & Alcance: 20 pts (peso 2.0)
      - Capacidade de Carga & Telas: 15 pts (peso 1.5)
      - Garantia & Acabamento: 10 pts (peso 1.0)
    """
    scores = specs.get("scores", {}) or {}
    mechanism = float(scores.get("mechanism_durability", 7.0)) * 3.0
    clamp_5cm = float(scores.get("clamp_5cm", 7.0)) * 2.5
    ergonomics = float(scores.get("ergonomics_reach", 7.0)) * 2.0
    load_cap = float(scores.get("load_capacity", 7.0)) * 1.5
    warranty = float(scores.get("warranty_build", 7.0)) * 1.0

    breakdown = {
        "mechanism_durability": round(mechanism, 1),
        "clamp_5cm": round(clamp_5cm, 1),
        "ergonomics_reach": round(ergonomics, 1),
        "load_capacity": round(load_cap, 1),
        "warranty_build": round(warranty, 1),
    }
    total = round(sum(breakdown.values()), 1)
    breakdown["total"] = total
    return breakdown


class MonitorArmsDashboardGenerator:
    """Gera painel Chart.js e resumo Markdown para os 10 suportes de monitor (1 e 2 telas)."""

    def __init__(self, repository: Repository, config_path: str | Path = "src/config/monitor_arms.yaml"):
        self.repo = repository
        self.config_path = Path(config_path)
        self.cycles_log_path = Path("data/monitor_arms_cycles.jsonl")
        self.template_path = Path("src/reporting/templates/monitor_arms_dashboard.html")
        self._base_helper = MonitorsDashboardGenerator(repository, config_path)

    def _load_catalog(self) -> list[dict[str, Any]]:
        import yaml

        if not self.config_path.exists():
            return []
        data = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        return data.get("products", [])

    def _load_cycles_log(self) -> list[dict[str, Any]]:
        if not self.cycles_log_path.exists():
            return []
        cycles = []
        for line in self.cycles_log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                cycles.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return cycles

    def append_cycle_log(
        self,
        arms_checked: int,
        sources_checked: int,
        quotes_collected: int,
        deals_found: int,
    ) -> int:
        self.cycles_log_path.parent.mkdir(parents=True, exist_ok=True)
        existing = self._load_cycles_log()
        run_number = len(existing) + 1
        now_recife = datetime.now(RECIFE_TZ)
        entry = {
            "run_number": run_number,
            "timestamp_utc": now_recife.astimezone().isoformat(),
            "timestamp_local": now_recife.strftime("%d/%m/%Y %H:%M"),
            "arms_checked": arms_checked,
            "sources_checked": sources_checked,
            "quotes_collected": quotes_collected,
            "deals_found": deals_found,
        }
        with self.cycles_log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return run_number

    def _build_dataset(self) -> dict[str, Any]:
        catalog = self._load_catalog()
        cycles = self._load_cycles_log()
        now_recife = datetime.now(RECIFE_TZ)
        days_to_bf = max(0, (BLACK_FRIDAY_2026 - now_recife).days)

        all_sources = []
        for p in catalog:
            all_sources.extend(self.repo.get_sources_for_product(p["id"]))
        source_by_id = {s.id: s for s in all_sources}
        sources_by_product: dict[str, list[int]] = defaultdict(list)
        for s in all_sources:
            if s.id is not None:
                sources_by_product[s.product_id].append(s.id)

        all_records: list[PriceRecord] = []
        for p in catalog:
            pid = p["id"]
            sids = sources_by_product.get(pid, [])
            if sids:
                all_records.extend(self.repo.get_price_history(pid, days=120))

        all_records.sort(key=lambda r: self._base_helper._to_recife(r.coletado_em))

        bucket_keys: list[str] = []
        bucket_seen: set[str] = set()
        for r in all_records:
            dt_recife = self._base_helper._to_recife(r.coletado_em)
            bkey = self._base_helper._bucket_key(dt_recife)
            if bkey not in bucket_seen:
                bucket_seen.add(bkey)
                bucket_keys.append(bkey)

        timeline_labels = [
            f"{b[8:10]}/{b[5:7]} {b[11:13]}h" if len(b) >= 13 else b
            for b in bucket_keys
        ]

        cards: list[dict[str, Any]] = []
        series_datasets: list[dict[str, Any]] = []
        total_quotes_count = len(all_records)
        live_count = 0
        below_target_count = 0
        confirmed_5cm_count = 0

        for idx, prod in enumerate(catalog):
            pid = prod["id"]
            nome = prod["nome"]
            specs = prod.get("specs", {}) or {}
            target = float(prod.get("preco_alvo", 0))
            max_price = float(prod.get("preco_maximo", 0))
            color = MONITOR_PALETTE[idx % len(MONITOR_PALETTE)]

            benefit = compute_arm_benefit_score(specs)
            prod_records = [
                r for r in all_records
                if source_by_id.get(r.source_id) and source_by_id[r.source_id].product_id == pid
            ]
            prod_records.sort(key=lambda r: self._base_helper._to_recife(r.coletado_em))

            records_by_bucket: dict[str, list[PriceRecord]] = defaultdict(list)
            for r in prod_records:
                bkey = self._base_helper._bucket_key(self._base_helper._to_recife(r.coletado_em))
                records_by_bucket[bkey].append(r)

            min_by_bucket: dict[str, PriceRecord] = {}
            for bkey, recs in records_by_bucket.items():
                min_by_bucket[bkey] = min(recs, key=lambda r: r.preco)

            last_price: float | None = None
            data_points: list[float | None] = []
            for bkey in bucket_keys:
                if bkey in min_by_bucket:
                    last_price = round(min_by_bucket[bkey].preco, 2)
                data_points.append(last_price)

            latest_by_mkt: dict[str, PriceRecord] = {}
            for r in prod_records:
                src = source_by_id.get(r.source_id)
                if src:
                    latest_by_mkt[src.marketplace] = r

            active_mkt_quotes = [
                r for r in latest_by_mkt.values()
                if (now_recife - self._base_helper._to_recife(r.coletado_em)).total_seconds() <= FRESHNESS_WINDOW_HOURS * 3600
            ]
            if not active_mkt_quotes and latest_by_mkt:
                active_mkt_quotes = list(latest_by_mkt.values())

            best_quote = min(active_mkt_quotes, key=lambda r: r.preco) if active_mkt_quotes else None
            has_live = best_quote is not None
            if has_live:
                live_count += 1

            ref_price = float(specs.get("price_regular_ref", max_price or target or 200))
            current_price = round(best_quote.preco, 2) if best_quote else round(ref_price, 2)
            current_mkt = source_by_id[best_quote.source_id].marketplace if best_quote and best_quote.source_id in source_by_id else "referencia"
            current_mkt_label = MARKETPLACE_LABELS.get(current_mkt, "Ref. da pesquisa")
            current_url = (best_quote.url_encontrada if best_quote and best_quote.url_encontrada else "") or (
                prod.get("sources", [{}])[0].get("url_produto", "#")
            )
            last_updated_str = (
                self._base_helper._to_recife(best_quote.coletado_em).strftime("%d/%m %H:%M")
                if best_quote else "Ref. pesquisa"
            )

            all_prices = [r.preco for r in prod_records]
            hist_min = round(min(all_prices), 2) if all_prices else round(float(specs.get("price_floor_ref", current_price)), 2)

            if target > 0:
                ratio = (target - current_price) / target
                deal_score = int(max(10, min(98, round(55 + ratio * 100))))
            else:
                deal_score = 50
            z_score = 0.0

            pts_per_100 = round(benefit["total"] / (current_price / 100.0), 1) if current_price > 0 else 0.0
            bf_opportunity = round(0.55 * benefit["total"] + 0.45 * deal_score, 1)

            below_target = has_live and target > 0 and current_price <= target
            if below_target:
                below_target_count += 1

            clamp_max_mm = int(specs.get("clamp_max_mm") or 0)
            if clamp_max_mm >= 50:
                confirmed_5cm_count += 1

            if has_live:
                series_datasets.append({
                    "id": pid,
                    "label": nome,
                    "data": data_points,
                    "borderColor": color,
                    "backgroundColor": color + "22",
                    "borderWidth": 2.5,
                    "tension": 0.25,
                    "pointRadius": 4,
                    "pointHoverRadius": 6,
                    "spanGaps": True,
                })

            cards.append({
                "id": pid,
                "nome": nome,
                "brand": specs.get("brand", ""),
                "monitors_count": int(specs.get("monitors_count", 1)),
                "category": specs.get("category", ""),
                "profiles": specs.get("profiles", []),
                "mechanism": specs.get("mechanism", ""),
                "screen_range": specs.get("screen_range", ""),
                "weight_min_kg": specs.get("weight_min_kg", 2.0),
                "weight_max_kg": specs.get("weight_max_kg", 9.0),
                "clamp_range_mm": specs.get("clamp_range_mm", ""),
                "clamp_max_mm": clamp_max_mm,
                "clearance_5cm_mm": specs.get("clearance_5cm_mm"),
                "clamp_5cm_status": specs.get("clamp_5cm_status", ""),
                "vesa": specs.get("vesa", ""),
                "warranty": specs.get("warranty", ""),
                "tag": specs.get("tag", ""),
                "pros": specs.get("pros", []),
                "cons": specs.get("cons", []),
                "color": color,
                "has_live": has_live,
                "current_price": current_price,
                "target_price": target,
                "hist_min": hist_min,
                "marketplace": current_mkt_label,
                "url": current_url,
                "last_updated": last_updated_str,
                "below_target": below_target,
                "deal_score": deal_score,
                "z_score": z_score,
                "benefit_score": benefit["total"],
                "benefit_breakdown": benefit,
                "pts_per_100": pts_per_100,
                "bf_opportunity": bf_opportunity,
            })

        cards_by_cb = sorted(cards, key=lambda c: (-c["pts_per_100"], c["current_price"]))
        cards_by_price = sorted(cards, key=lambda c: c["current_price"])

        best_1mon = next((c for c in cards_by_cb if c["monitors_count"] == 1), None)
        best_2mon = next((c for c in cards_by_cb if c["monitors_count"] == 2), None)
        cheapest = cards_by_price[0] if cards_by_price else None

        return {
            "generated_at": now_recife.strftime("%d/%m/%Y às %H:%M"),
            "days_to_bf": days_to_bf,
            "total_arms": len(catalog),
            "live_count": live_count,
            "below_target_count": below_target_count,
            "confirmed_5cm_count": confirmed_5cm_count,
            "total_quotes": total_quotes_count,
            "cycles_count": len(cycles),
            "timeline_labels": timeline_labels,
            "series_datasets": series_datasets,
            "cards": cards_by_cb,
            "cards_by_price": cards_by_price,
            "cycles": list(reversed(cycles[-10:])),
            "profiles": ARM_PROFILES,
            "highlights": {
                "best_1mon": best_1mon,
                "best_2mon": best_2mon,
                "cheapest": cheapest,
            },
        }

    def generate(
        self,
        html_path: str | Path = "reports/suportes_monitor_black_friday.html",
        md_path: str | Path = "reports/monitor_arms_summary.md",
        open_browser: bool = False,
    ) -> dict[str, Path]:
        dataset = self._build_dataset()

        html_out = Path(html_path)
        html_out.parent.mkdir(parents=True, exist_ok=True)
        if self.template_path.exists():
            tpl = self.template_path.read_text(encoding="utf-8")
            payload_json = json.dumps(dataset, ensure_ascii=False)
            html_content = tpl.replace("__MONITOR_ARMS_DATA_JSON__", payload_json)
            html_out.write_text(html_content, encoding="utf-8")
            logger.success(f"🦾 Painel de suportes de monitor atualizado: {html_out}")

        md_out = Path(md_path)
        md_out.parent.mkdir(parents=True, exist_ok=True)
        md_out.write_text(self._render_markdown(dataset), encoding="utf-8")
        logger.info(f"📝 Relatório resumo atualizado: {md_out}")

        if open_browser and html_out.exists():
            webbrowser.open(html_out.resolve().as_uri())

        return {"html": html_out, "markdown": md_out}

    def _render_markdown(self, dataset: dict[str, Any]) -> str:
        hl = dataset["highlights"]
        lines = [
            "# 🦾 Relatório Incremental Black Friday 2026 — Suportes Articulados para Monitores (Mesa 5 cm Sem Furos)",
            "",
            f"- **Última atualização:** {dataset['generated_at']} (America/Recife)",
            f"- **Contagem regressiva Black Friday (27/11/2026):** {dataset['days_to_bf']} dias",
            f"- **Rodadas acumuladas:** {dataset['cycles_count']} | **Cotações no SQLite:** {dataset['total_quotes']}",
            f"- **Suportes com cotação ao vivo:** {dataset['live_count']}/{dataset['total_arms']} | **Abaixo do Alvo:** {dataset['below_target_count']} | **Morsa 5 cm confirmada:** {dataset['confirmed_5cm_count']}/{dataset['total_arms']}",
        ]
        if hl.get("best_1mon"):
            b1 = hl["best_1mon"]
            lines.append(f"- **🏆 Melhor Custo-Benefício (1 Monitor):** {b1['nome']} — {fmt_brl(b1['current_price'])} ({b1['pts_per_100']} pts/R$ 100)")
        if hl.get("best_2mon"):
            b2 = hl["best_2mon"]
            lines.append(f"- **🖥️ Melhor Custo-Benefício (2 Monitores):** {b2['nome']} — {fmt_brl(b2['current_price'])} ({b2['pts_per_100']} pts/R$ 100)")
        if hl.get("cheapest"):
            ch = hl["cheapest"]
            lines.append(f"- **💰 Menor preço atual:** {ch['nome']} — {fmt_brl(ch['current_price'])}")

        lines.extend([
            "",
            "## 🏆 Ranking Custo-Benefício Ergonômico e Compatibilidade (Mesa 5 cm)",
            "",
            "| # | Suporte | Telas | Mecanismo | Morsa / Folga 5 cm | Preço Atual | Loja | Benefício | Pts/R$100 | Status |",
            "| :---: | :--- | :---: | :--- | :--- | :---: | :--- | :---: | :---: | :--- |",
        ])

        for i, c in enumerate(dataset["cards"], start=1):
            price_str = f"**{fmt_brl(c['current_price'])}**" if c["has_live"] else f"_{fmt_brl(c['current_price'])} (ref.)_"
            loja_str = f"[{c['marketplace']}]({c['url']})" if c["url"] and c["url"] != "#" else c["marketplace"]
            status_str = "🎯 Abaixo do Alvo" if c["below_target"] else ("✅ Monitorado" if c["has_live"] else "⏳ Ref. Pesquisa")
            folga = f"{c['clamp_range_mm']}" + (f" (+{c['clearance_5cm_mm']}mm)" if c["clearance_5cm_mm"] is not None else "")
            lines.append(
                f"| {i} | **{c['nome']}** | {c['monitors_count']}x | {c['mechanism']} | {folga} | {price_str} | {loja_str} | {c['benefit_score']} | {c['pts_per_100']} | {status_str} |"
            )

        if dataset["cycles"]:
            lines.extend([
                "",
                "## ⏱️ Histórico Recente de Execuções",
                "",
                "| Ciclo | Data / Hora (Recife) | Suportes | Fontes | Cotações Válidas | Oportunidades |",
                "| :---: | :---: | :---: | :---: | :---: | :---: |",
            ])
            for cyc in dataset["cycles"]:
                lines.append(
                    f"| #{cyc.get('run_number')} | {cyc.get('timestamp_local')} | {cyc.get('arms_checked')} | {cyc.get('sources_checked')} | {cyc.get('quotes_collected')} | {cyc.get('deals_found')} |"
                )

        return "\n".join(lines)
