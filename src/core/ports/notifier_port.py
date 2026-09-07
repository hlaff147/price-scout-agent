"""Port interface for alert and notification adapters."""

from abc import ABC, abstractmethod

from src.data.models import DealAnalysis, Product


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
