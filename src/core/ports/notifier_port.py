"""Port interface for alert and notification adapters."""

from abc import ABC, abstractmethod

from src.data.models import Coupon, DealAnalysis, Product


class INotifier(ABC):
    """Porta para adapters de notificação (Telegram, Discord, Console, Webhook, etc.)."""

    @abstractmethod
    async def run(
        self,
        deal: DealAnalysis,
        product: Product,
        dry_run: bool = False,
    ) -> bool:
        """Dispara um alerta sobre uma oportunidade detectada.

        Args:
            deal: Oportunidade identificada.
            product: Produto associado.
            dry_run: Se True, apenas simula sem envio para canais externos.

        Returns:
            True se o alerta foi emitido com sucesso, False caso contrário.
        """

    @abstractmethod
    async def notify_coupon(
        self,
        coupon: Coupon,
        product: Product | None = None,
        final_price: float | None = None,
        url: str | None = None,
        dry_run: bool = False,
    ) -> bool:
        """Dispara um alerta especializado sobre um cupom ou código promocional detectado.

        Args:
            coupon: Cupom detectado.
            product: Produto associado (opcional).
            final_price: Preço final com desconto do cupom (opcional).
            url: Link da oferta ou loja (opcional).
            dry_run: Se True, apenas simula.

        Returns:
            True se emitido com sucesso, False caso contrário.
        """

