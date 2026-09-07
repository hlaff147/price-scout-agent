"""HTML report generator for PromoRadar monitoring cycles."""

import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader
from loguru import logger

from src.data.database import default_db
from src.data.models import DealAnalysis, Product
from src.data.repository import Repository


# Cores por marketplace para os gráficos
MARKETPLACE_COLORS = {
    "amazon": {"bg": "rgba(255, 153, 0, 0.7)", "border": "rgb(255, 153, 0)"},
    "mercadolivre": {"bg": "rgba(255, 230, 0, 0.7)", "border": "rgb(255, 230, 0)"},
    "shopee": {"bg": "rgba(238, 77, 45, 0.7)", "border": "rgb(238, 77, 45)"},
    "google_shopping": {"bg": "rgba(66, 133, 244, 0.7)", "border": "rgb(66, 133, 244)"},
    "kabum": {"bg": "rgba(255, 85, 0, 0.7)", "border": "rgb(255, 85, 0)"},
    "aliexpress": {"bg": "rgba(230, 36, 18, 0.7)", "border": "rgb(230, 36, 18)"},
}

DEFAULT_COLOR = {"bg": "rgba(153, 153, 153, 0.7)", "border": "rgb(153, 153, 153)"}


class ReportGenerator:
    """Gera relatórios HTML interativos com gráficos de preço após cada ciclo."""

    def __init__(self, repository: Repository | None = None):
        self.repository = repository or Repository(default_db)
        template_dir = Path(__file__).parent / "templates"
        self.env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=True,
        )

    def generate(
        self,
        summary: dict[str, Any],
        open_browser: bool = True,
    ) -> Path | None:
        """Gera relatórios HTML para cada produto processado no ciclo.

        Returns:
            Path do último relatório gerado, ou None se nenhum foi gerado.
        """
        cycles = summary.get("cycles", [])
        if not cycles:
            logger.warning("Nenhum ciclo para gerar relatório.")
            return None

        last_path = None
        for cycle in cycles:
            product_id = cycle.get("product_id")
            if not product_id:
                continue

            product = self.repository.get_product(product_id)
            if not product:
                logger.warning(f"Produto '{product_id}' não encontrado no banco.")
                continue

            report_path = self._generate_for_product(product, cycle)
            if report_path:
                last_path = report_path
                logger.success(f"📄 Relatório gerado: {report_path}")
                if open_browser:
                    webbrowser.open(f"file://{report_path.resolve()}")

        return last_path

    def _generate_for_product(
        self,
        product: Product,
        cycle: dict[str, Any],
    ) -> Path | None:
        """Gera o relatório HTML para um produto específico."""
        now = datetime.now(timezone.utc)
        timestamp_str = now.strftime("%Y-%m-%d_%H-%M")

        # Dados do ciclo atual
        analyses: list[DealAnalysis] = cycle.get("analyses", [])
        sources_checked = cycle.get("sources_checked", 0)
        prices_collected = cycle.get("prices_collected", 0)
        deals_found = cycle.get("deals_found", 0)
        no_results = cycle.get("no_results", 0)
        errors = cycle.get("errors", 0)

        # Todas as fontes do produto (ativas e inativas)
        all_sources = self.repository.get_sources_for_product(product.id)

        # Preços atuais por marketplace (do ciclo atual)
        current_prices = []
        for analysis in analyses:
            color = MARKETPLACE_COLORS.get(analysis.marketplace, DEFAULT_COLOR)
            current_prices.append({
                "marketplace": analysis.marketplace.upper(),
                "marketplace_key": analysis.marketplace,
                "preco": analysis.preco_atual,
                "preco_fmt": f"R$ {analysis.preco_atual:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                "preco_original": analysis.preco_original_anunciado,
                "preco_original_fmt": (
                    f"R$ {analysis.preco_original_anunciado:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                    if analysis.preco_original_anunciado
                    else "—"
                ),
                "desconto_real": analysis.desconto_real_percent,
                "desconto_real_fmt": f"{analysis.desconto_real_percent:.1f}%" if analysis.desconto_real_percent else "—",
                "is_deal": analysis.is_deal,
                "is_fake_discount": analysis.is_fake_discount,
                "is_all_time_low": analysis.is_all_time_low,
                "motivo": analysis.motivo_alerta or "",
                "justificativa": analysis.justificativa,
                "url": analysis.url,
                "cupom": analysis.cupom,
                "color_bg": color["bg"],
                "color_border": color["border"],
            })

        # Ordenar por preço (menor primeiro)
        current_prices.sort(key=lambda x: x["preco"])

        # Dados para gráfico de barras (comparação de preços atuais)
        bar_labels = [p["marketplace"] for p in current_prices]
        bar_values = [p["preco"] for p in current_prices]
        bar_colors_bg = [p["color_bg"] for p in current_prices]
        bar_colors_border = [p["color_border"] for p in current_prices]

        # Dados para gráfico de linha (histórico de preços por marketplace)
        history_datasets = []
        active_sources = [s for s in all_sources if s.ativo and s.id]
        for source in active_sources:
            history = self.repository.get_price_history_by_source(source.id, days=90)
            if not history:
                continue
            color = MARKETPLACE_COLORS.get(source.marketplace, DEFAULT_COLOR)
            dataset = {
                "label": source.marketplace.upper(),
                "data": [
                    {
                        "x": rec.coletado_em.strftime("%Y-%m-%dT%H:%M:%S"),
                        "y": rec.preco,
                    }
                    for rec in history
                ],
                "borderColor": color["border"],
                "backgroundColor": color["bg"],
            }
            history_datasets.append(dataset)

        # Estatísticas históricas
        min_price = self.repository.get_historical_min_price(product.id)
        avg_price = self.repository.get_historical_average_price(product.id, days=60)

        # Alertas recentes
        recent_alerts = self.repository.get_recent_alerts(product.id, limit=5)
        alerts_data = [
            {
                "motivo": a.motivo,
                "detalhes": a.detalhes or "—",
                "enviado_em": a.enviado_em.strftime("%d/%m/%Y %H:%M"),
                "canal": a.canal,
            }
            for a in recent_alerts
        ]

        # Status das fontes
        sources_status = []
        for src in all_sources:
            sources_status.append({
                "marketplace": src.marketplace.upper(),
                "url": src.url_produto,
                "metodo": src.metodo_coleta,
                "ativo": src.ativo,
                "motivo_desativacao": src.motivo_desativacao or "—",
            })

        # Deals (oportunidades)
        deals = [p for p in current_prices if p["is_deal"]]

        # Renderizar template
        template = self.env.get_template("cycle_report.html")
        html = template.render(
            product_name=product.nome,
            product_id=product.id,
            preco_alvo=product.preco_alvo,
            preco_alvo_fmt=f"R$ {product.preco_alvo:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            preco_maximo=product.preco_maximo,
            preco_maximo_fmt=f"R$ {product.preco_maximo:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            cycle_timestamp=now.strftime("%d/%m/%Y %H:%M:%S UTC"),
            sources_checked=sources_checked,
            prices_collected=prices_collected,
            deals_found=deals_found,
            no_results=no_results,
            errors=errors,
            current_prices=current_prices,
            bar_labels=bar_labels,
            bar_values=bar_values,
            bar_colors_bg=bar_colors_bg,
            bar_colors_border=bar_colors_border,
            history_datasets=history_datasets,
            min_price=min_price,
            min_price_fmt=(
                f"R$ {min_price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                if min_price else "—"
            ),
            avg_price=avg_price,
            avg_price_fmt=(
                f"R$ {avg_price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                if avg_price else "—"
            ),
            alerts=alerts_data,
            sources_status=sources_status,
            deals=deals,
        )

        # Salvar em reports/
        reports_dir = Path("reports")
        reports_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{product.id}_{timestamp_str}.html"
        report_path = reports_dir / filename

        report_path.write_text(html, encoding="utf-8")
        return report_path
