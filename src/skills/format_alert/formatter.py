"""Alert message formatting skill with strict HTML entity escaping for Telegram."""

from __future__ import annotations

from src.core.domain import escape_telegram_html
from src.core.models import Coupon, DealAnalysis, Product
from src.skills.base import BaseSkill


def _fmt_brl(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


class FormatAlertSkill(BaseSkill):
    """Formata mensagens ricas e sanitizadas para notificação de ofertas."""

    name = "format_alert"
    description = "Formata mensagens em HTML seguro/Texto para Telegram e console."

    def execute(self, deal: DealAnalysis, product: Product) -> str:
        return self.format_telegram_message(deal, product)

    @staticmethod
    def format_telegram_message(deal: DealAnalysis, product: Product) -> str:
        """Gera mensagem formatada em HTML escapado para o Telegram Bot."""
        if deal.is_all_time_low:
            badge = "🚨 <b>MENOR PREÇO HISTÓRICO DETECTADO!</b>"
        elif deal.is_below_target:
            badge = "🎯 <b>PREÇO ABAIXO DO ALVO DEFINIDO!</b>"
        else:
            badge = "⚡ <b>OPORTUNIDADE DE COMPRA DETECTADA!</b>"

        market_display = escape_telegram_html(deal.marketplace.upper())
        prod_name = escape_telegram_html(product.nome)
        preco_fmt = _fmt_brl(deal.preco_atual)

        lines = [
            badge,
            "",
            f"📦 <b>Produto:</b> {prod_name}",
            f"🛒 <b>Loja:</b> {market_display}",
            f"💰 <b>Preço Atual:</b> <code>{preco_fmt}</code>",
        ]

        if deal.preco_efetivo and deal.preco_efetivo < deal.preco_atual:
            lines.append(f"💵 <b>Preço Efetivo c/ Cupom:</b> <code>{_fmt_brl(deal.preco_efetivo)}</code>")

        if deal.preco_minimo_historico and deal.preco_minimo_historico > 0:
            lines.append(f"📉 <b>Mínima Anterior:</b> {_fmt_brl(deal.preco_minimo_historico)}")

        if deal.desconto_real_percent and deal.desconto_real_percent > 0:
            lines.append(f"🏷️ <b>Desconto Real:</b> {deal.desconto_real_percent:.1f}% (vs. histórico)")

        if deal.cupom:
            lines.append(f"🎟️ <b>Cupom Disponível:</b> <code>{escape_telegram_html(deal.cupom)}</code>")

        if deal.is_fake_discount:
            lines.append(
                "⚠️ <i>Atenção: A loja anuncia um desconto inflado sobre o preço 'de', "
                "mas o desconto real foi apurado contra o histórico.</i>"
            )

        safe_justificativa = escape_telegram_html(deal.justificativa)
        safe_url = escape_telegram_html(deal.url)

        lines.extend([
            "",
            f"💡 <i>{safe_justificativa}</i>",
            "",
            f'🔗 <a href="{safe_url}">Ver Oferta na Loja</a>',
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
        """Gera mensagem formatada em HTML escapado especializada para cupons no Telegram Bot."""
        market_display = escape_telegram_html(coupon.marketplace.upper())
        safe_code = escape_telegram_html(coupon.codigo)

        if coupon.desconto_percentual:
            desc_text = f"<b>{coupon.desconto_percentual:.0f}% OFF</b>"
        elif coupon.desconto_fixo:
            desc_text = f"<b>R$ {coupon.desconto_fixo:.2f} OFF</b>"
        elif coupon.descricao:
            desc_text = f"<b>{escape_telegram_html(coupon.descricao)}</b>"
        else:
            desc_text = "Desconto promocional"

        lines = [
            "🎟️ <b>NOVO CUPOM DE DESCONTO DETECTADO!</b>",
            "",
            f"🛒 <b>Loja:</b> {market_display}",
            f"🏷️ <b>Cupom:</b> <code>{safe_code}</code>",
            f"💰 <b>Vantagem:</b> {desc_text}",
        ]

        if product:
            lines.append(f"📦 <b>Produto:</b> {escape_telegram_html(product.nome)}")
        if final_price:
            lines.append(f"💵 <b>Preço c/ Cupom:</b> <code>{_fmt_brl(final_price)}</code>")

        if url:
            safe_url = escape_telegram_html(url)
            lines.extend(["", f'🔗 <a href="{safe_url}">Aproveitar Cupom na Loja</a>'])

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
