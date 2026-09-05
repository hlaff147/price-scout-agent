"""Alert message formatting skill."""

from src.data.models import DealAnalysis, Product
from src.skills.base import BaseSkill


class FormatAlertSkill(BaseSkill):
    """Formata mensagens ricas para notificação de ofertas."""

    name = "format_alert"
    description = "Formata mensagens em HTML/Markdown para Telegram."

    def execute(self, deal: DealAnalysis, product: Product) -> str:
        return self.format_telegram_message(deal, product)

    @staticmethod
    def format_telegram_message(deal: DealAnalysis, product: Product) -> str:
        """Gera mensagem formatada em HTML para o Telegram Bot."""
        # Badge de cabeçalho
        if deal.is_all_time_low:
            badge = "🚨 <b>MENOR PREÇO HISTÓRICO DETECTADO!</b>"
        elif deal.is_below_target:
            badge = "🎯 <b>PREÇO ABAIXO DO ALVO DEFINIDO!</b>"
        else:
            badge = "⚡ <b>OPORTUNIDADE DE COMPRA DETECTADA!</b>"

        market_display = deal.marketplace.upper()
        preco_fmt = f"R$ {deal.preco_atual:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

        lines = [
            badge,
            "",
            f"📦 <b>Produto:</b> {product.nome}",
            f"🛒 <b>Loja:</b> {market_display}",
            f"💰 <b>Preço Atual:</b> <code>{preco_fmt}</code>",
        ]

        if deal.preco_minimo_historico and deal.preco_minimo_historico > 0:
            min_fmt = f"R$ {deal.preco_minimo_historico:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            lines.append(f"📉 <b>Mínima Anterior:</b> {min_fmt}")

        if deal.desconto_real_percent and deal.desconto_real_percent > 0:
            lines.append(f"🏷️ <b>Desconto Real:</b> {deal.desconto_real_percent:.1f}% (vs. histórico)")

        if deal.cupom:
            lines.append(f"🎟️ <b>Cupom Disponível:</b> <code>{deal.cupom}</code>")

        if deal.is_fake_discount:
            lines.append("⚠️ <i>Atenção: A loja anuncia um desconto inflado sobre o preço 'de', mas o desconto real foi apurado contra o histórico.</i>")

        lines.extend([
            "",
            f"💡 <i>{deal.justificativa}</i>",
            "",
            f"🔗 <a href='{deal.url}'>Ver Oferta na Loja</a>",
        ])

        return "\n".join(lines)

    @staticmethod
    def format_console_message(deal: DealAnalysis, product: Product) -> str:
        """Gera mensagem legível para terminal/logs."""
        sep = "=" * 60
        return (
            f"\n{sep}\n"
            f"[PROMORADAR ALERTA] {product.nome} em {deal.marketplace.upper()}\n"
            f"Preço: R$ {deal.preco_atual:.2f} | Motivo: {deal.motivo_alerta}\n"
            f"Justificativa: {deal.justificativa}\n"
            f"Link: {deal.url}\n"
            f"{sep}"
        )
