"""Gerador do Dashboard Interativo e Relatório Incremental de Suportes Articulados para Monitores (1 e 2 Telas, Mesa 5 cm Sem Furos)."""

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
    safe_external_href,
)

FRESHNESS_WINDOW_HOURS = DEFAULT_FRESHNESS_HOURS

ARM_PROFILES = {
    "1_monitor": "1 Monitor (Braço Individual)",
    "2_monitores": "2 Monitores (Braço Duplo)",
    "mesa_5cm_confirmada": "Compatível 5 cm Confirmado (≥ 70 mm)",
    "custo_beneficio": "Melhor Custo-Benefício Geral",
    "telas_pesadas": "Telas Pesadas (até 12 kg / braço)",
    "economico": "Setup Econômico",
}


def compute_arm_benefit_score(specs: dict[str, Any]) -> dict[str, float]:
    """Calcula o Índice de Benefício Ergonômico (0–100)."""
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
    breakdown["total"] = round(sum(breakdown.values()), 1)
    return breakdown


class MonitorArmsDashboardGenerator(BaseCategoryDashboardGenerator):
    """Gera painel Chart.js seguro e resumo Markdown para os 10 suportes de monitor (1 e 2 telas)."""

    def __init__(
        self,
        repository: Repository | None = None,
        config_path: str | Path = "src/config/monitor_arms.yaml",
        cycles_log_path: str | Path = "data/monitor_arms_cycles.jsonl",
    ):
        super().__init__(
            repository=repository,
            config_path=config_path,
            cycles_log_path=cycles_log_path,
        )

    def _build_dataset(self) -> dict[str, Any]:
        catalog = self.load_catalog_config()
        cycles = self.load_cycle_logs()
        now_local = datetime.now(timezone.utc).astimezone(RECIFE_TZ)
        days_to_bf = max(0, (BLACK_FRIDAY_2026.date() - now_local.date()).days)

        cards: list[dict[str, Any]] = []
        all_buckets: set[str] = set()
        per_arm_buckets: dict[str, dict[str, dict[str, float]]] = {}
        total_quotes_count = 0
        live_count = 0
        below_target_count = 0
        confirmed_5cm_count = 0

        for idx, prod in enumerate(catalog):
            pid = prod["id"]
            nome = prod["nome"]
            specs = prod.get("specs", {}) or {}
            target = float(prod.get("preco_alvo", 0))
            max_price = float(prod.get("preco_maximo", 0))
            ref_price = float(specs.get("price_regular_ref", max_price or target or 200))
            floor_ref = float(specs.get("price_floor_ref", ref_price))
            color = CATEGORY_PALETTE[idx % len(CATEGORY_PALETTE)]

            bundle = self.collect_product_history(
                prod,
                now_local=now_local,
                fallback_ref_price=ref_price,
                freshness_hours=FRESHNESS_WINDOW_HOURS,
            )
            total_quotes_count += len(bundle.records_asc)
            all_buckets.update(bundle.mkt_bucket_min.keys())
            per_arm_buckets[pid] = bundle.mkt_bucket_min

            has_live = bundle.live_price is not None
            if has_live:
                live_count += 1

            current_price = round(bundle.effective_price, 2)
            best = bundle.best_offer
            default_src_url = safe_external_href(
                (prod.get("sources") or [{}])[0].get("url_produto", "")
            )
            current_url = (best["url"] if best and best["url"] else default_src_url) or "#"
            current_mkt_label = best["marketplace"] if best else "Ref. da pesquisa"
            last_updated_str = best["coletado_em"] if best else "Ref. pesquisa"

            hist_min = (
                round(bundle.hist_min, 2) if bundle.hist_min is not None else round(floor_ref, 2)
            )
            stat = bundle.stat_profile
            benefit = compute_arm_benefit_score(specs)

            pts_per_100 = (
                round(benefit["total"] / (current_price / 100.0), 1)
                if current_price > 0
                else 0.0
            )
            bf_opportunity = round(
                0.55 * benefit["total"] + 0.45 * stat.deal_confidence_score, 1
            )

            below_target = bool(has_live and target > 0 and current_price <= target)
            if below_target:
                below_target_count += 1

            clamp_max_mm = int(specs.get("clamp_max_mm") or 0)
            if clamp_max_mm >= 50:
                confirmed_5cm_count += 1

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
                "priceRegularRef": round(ref_price, 2),
                "has_live": has_live,
                "current_price": current_price,
                "target_price": target,
                "hist_min": hist_min,
                "marketplace": current_mkt_label,
                "url": current_url,
                "last_updated": last_updated_str,
                "below_target": below_target,
                "deal_score": stat.deal_confidence_score,
                "z_score": stat.robust_z_score,
                "percentile_rank": stat.percentile_rank,
                "price_regime": stat.regime_preco,
                "benefit_score": benefit["total"],
                "benefit_breakdown": benefit,
                "pts_per_100": pts_per_100,
                "bf_opportunity": bf_opportunity,
                "store_offers": bundle.store_offers,
            })

        timeline_labels = self.build_timeline_series(
            all_buckets,
            per_arm_buckets,
            cards,
            baseline_label="Ref. Pesquisa",
            baseline_key="priceRegularRef",
            freshness_hours=FRESHNESS_WINDOW_HOURS,
        )

        series_datasets = [
            {
                "id": c["id"],
                "label": c["nome"],
                "data": c["timelineValues"],
                "borderColor": c["color"],
                "backgroundColor": c["color"] + "22",
                "borderWidth": 2.5,
                "tension": 0.25,
                "pointRadius": 4,
                "pointHoverRadius": 6,
                "spanGaps": True,
            }
            for c in cards
            if c["has_live"]
        ]

        cards_by_cb = sorted(cards, key=lambda c: (-c["pts_per_100"], c["current_price"]))
        cards_by_price = sorted(cards, key=lambda c: c["current_price"])

        best_1mon = next((c for c in cards_by_cb if c["monitors_count"] == 1), None)
        best_2mon = next((c for c in cards_by_cb if c["monitors_count"] == 2), None)
        cheapest = cards_by_price[0] if cards_by_price else None

        return {
            "generated_at": now_local.strftime("%d/%m/%Y às %H:%M"),
            "days_to_bf": days_to_bf,
            "total_arms": len(catalog),
            "live_count": live_count,
            "below_target_count": below_target_count,
            "confirmed_5cm_count": confirmed_5cm_count,
            "total_quotes": total_quotes_count,
            "cycles_count": max(len(cycles), len(all_buckets)),
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
        output_html_path: str | Path = "reports/suportes_monitor_black_friday.html",
        output_md_path: str | Path = "reports/monitor_arms_summary.md",
        open_browser: bool = False,
        *,
        html_path: str | Path | None = None,
        md_path: str | Path | None = None,
    ) -> Path:
        """Gera o dashboard HTML interativo seguro e o resumo Markdown dos suportes."""
        resolved_html = html_path or output_html_path
        resolved_md = md_path or output_md_path
        dataset = self._build_dataset()

        template = self.env.get_template("monitor_arms_dashboard.html")
        html_content = template.render(
            data_json=self.safe_script_json(dataset),
        )
        md_content = self._render_markdown(dataset)

        return self.write_outputs(
            html_content=html_content,
            md_content=md_content,
            output_html_path=resolved_html,
            output_md_path=resolved_md,
            open_browser=open_browser,
            banner_label="🦾 Painel de suportes de monitor",
        )

    @staticmethod
    def _render_markdown(dataset: dict[str, Any]) -> str:
        hl = dataset["highlights"]
        lines = [
            "# 🦾 Relatório Incremental Black Friday 2026 — Suportes Articulados para Monitores (Mesa 5 cm Sem Furos)",
            "",
            f"- **Última atualização:** {dataset['generated_at']} (America/Recife)",
            f"- **Contagem regressiva Black Friday (27/11/2026):** {dataset['days_to_bf']} dias",
            f"- **Rodadas acumuladas:** {dataset['cycles_count']} | **Cotações no SQLite:** {dataset['total_quotes']}",
            (
                f"- **Suportes com cotação ao vivo:** {dataset['live_count']}/{dataset['total_arms']} | "
                f"**Abaixo do Alvo:** {dataset['below_target_count']} | "
                f"**Morsa 5 cm confirmada:** {dataset['confirmed_5cm_count']}/{dataset['total_arms']}"
            ),
        ]
        if hl.get("best_1mon"):
            b1 = hl["best_1mon"]
            lines.append(
                f"- **🏆 Melhor Custo-Benefício (1 Monitor):** {b1['nome']} — "
                f"{fmt_brl(b1['current_price'])} ({b1['pts_per_100']} pts/R$ 100)"
            )
        if hl.get("best_2mon"):
            b2 = hl["best_2mon"]
            lines.append(
                f"- **🖥️ Melhor Custo-Benefício (2 Monitores):** {b2['nome']} — "
                f"{fmt_brl(b2['current_price'])} ({b2['pts_per_100']} pts/R$ 100)"
            )
        if hl.get("cheapest"):
            ch = hl["cheapest"]
            lines.append(f"- **💰 Menor preço atual:** {ch['nome']} — {fmt_brl(ch['current_price'])}")

        lines.extend([
            "",
            "## 🏆 Ranking Custo-Benefício Ergonômico e Compatibilidade (Mesa 5 cm)",
            "",
            "| # | Suporte | Telas | Mecanismo | Morsa / Folga 5 cm | Preço Atual | Loja | Benefício | Deal Score | Z-Score (MAD) | Pts/R$100 | Status |",
            "| :---: | :--- | :---: | :--- | :--- | :---: | :--- | :---: | :---: | :---: | :---: | :--- |",
        ])

        for i, c in enumerate(dataset["cards"], start=1):
            price_str = (
                f"**{fmt_brl(c['current_price'])}**"
                if c["has_live"]
                else f"_{fmt_brl(c['current_price'])} (ref.)_"
            )
            loja_str = (
                f"[{c['marketplace']}]({c['url']})"
                if c["url"] and c["url"] != "#"
                else c["marketplace"]
            )
            status_str = (
                "🎯 Abaixo do Alvo"
                if c["below_target"]
                else ("✅ Monitorado" if c["has_live"] else "⏳ Ref. Pesquisa")
            )
            folga = f"{c['clamp_range_mm']}" + (
                f" (+{c['clearance_5cm_mm']}mm)" if c["clearance_5cm_mm"] is not None else ""
            )
            deal_s = f"{c['deal_score']:.0f}/100" if c.get("deal_score") is not None else "—"
            z_val = f"{c['z_score']:+.2f}" if c.get("z_score") is not None else "0.00"
            lines.append(
                f"| {i} | **{c['nome']}** | {c['monitors_count']}x | {c['mechanism']} | {folga} | "
                f"{price_str} | {loja_str} | {c['benefit_score']} | `{deal_s}` | `{z_val}` | "
                f"{c['pts_per_100']} | {status_str} |"
            )

        lines.extend([
            "",
            "## ⏱️ Histórico Recente de Execuções",
            "",
            "| Ciclo | Data / Hora (Recife) | Suportes | Fontes | Cotações Válidas | Oportunidades |",
            "| :---: | :---: | :---: | :---: | :---: | :---: |",
        ])
        if dataset["cycles"]:
            for cyc in dataset["cycles"]:
                checked = cyc.get("items_checked", cyc.get("arms_checked", cyc.get("monitors_checked", 0)))
                lines.append(
                    f"| #{cyc.get('run_number', '?')} | {cyc.get('timestamp_local', '—')} | "
                    f"{checked} | {cyc.get('sources_checked', 0)} | "
                    f"{cyc.get('quotes_collected', 0)} | {cyc.get('deals_found', 0)} |"
                )
        else:
            lines.append(f"| #0 | Base Inicial (pesquisa) | {dataset['total_arms']} | — | — | — |")

        lines.append("")
        return "\n".join(lines)
