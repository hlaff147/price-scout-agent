"""Alert message formatting skill."""

from src.data.models import Coupon, DealAnalysis, Product
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

    @staticmethod
    def format_coupon_message(
        coupon: Coupon,
        product: Product | None = None,
        final_price: float | None = None,
        url: str | None = None,
    ) -> str:
        """Gera mensagem formatada em HTML especializada para cupons no Telegram Bot."""
        market_display = coupon.marketplace.upper()

        if coupon.desconto_percentual:
            desc_text = f"<b>{coupon.desconto_percentual:.0f}% OFF</b>"
        elif coupon.desconto_fixo:
            desc_text = f"<b>R$ {coupon.desconto_fixo:.2f} OFF</b>"
        elif coupon.descricao:
            desc_text = f"<b>{coupon.descricao}</b>"
        else:
            desc_text = "Desconto promocional"

        lines = [
            "🎟️ <b>NOVO CUPOM DE DESCONTO DETECTADO!</b>",
            "",
            f"🛒 <b>Loja:</b> {market_display}",
            f"🏷️ <b>Cupom:</b> <code>{coupon.codigo}</code>",
            f"💰 <b>Vantagem:</b> {desc_text}",
        ]

        if product:
            lines.append(f"📦 <b>Produto:</b> {product.nome}")
        if final_price:
            preco_fmt = f"R$ {final_price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            lines.append(f"💵 <b>Preço c/ Cupom:</b> <code>{preco_fmt}</code>")

        if url:
            lines.extend(["", f"🔗 <a href='{url}'>Aproveitar Cupom na Loja</a>"])

        return "\n".join(lines)

    @staticmethod
    def format_coupon_console_message(
        coupon: Coupon,
        product: Product | None = None,
        final_price: float | None = None,
        url: str | None = None,
    ) -> str:
        """Gera mensagem legível de cupom para logs de console."""
        sep = "=" * 60
        prod_str = f" para '{product.nome}'" if product else ""
        price_str = f" | Preço c/ Cupom: R$ {final_price:.2f}" if final_price else ""
        return (
            f"\n{sep}\n"
            f"[PROMORADAR CUPOM] Novo cupom em {coupon.marketplace.upper()}{prod_str}\n"
            f"Código: {coupon.codigo} | Descrição: {coupon.descricao or 'N/A'}{price_str}\n"
            f"Link: {url or 'N/A'}\n"
            f"{sep}"
        )

