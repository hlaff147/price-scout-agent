from loguru import logger

from src.config.settings import settings
from src.core.ports.notifier_port import INotifier
from src.core.ports.repository_port import IRepository
from src.data.models import Alert, DealAnalysis, Product
from src.data.repository import Repository
from src.skills.format_alert.formatter import FormatAlertSkill
from src.subagents.base import BaseSubagent
from src.tools.notification_tools import send_telegram_notification


class NotifierSubagent(BaseSubagent, INotifier):
    """Subagente responsável por formatar e disparar notificações de ofertas."""

    name = "notifier_agent"
    role = "Alert & Notification Dispatcher"

    def __init__(self, repository: IRepository | None = None):
        self.repository = repository or Repository()
        self.formatter = FormatAlertSkill()

    async def run(
        self,
        deal: DealAnalysis,
        product: Product,
        dry_run: bool = False,
    ) -> bool:
        """Envia alerta de oportunidade pelo canal configurado."""
        if not deal.is_deal:
            return False

        # Verificar política anti-spam (ex: não repetir alerta para o mesmo produto em menos de 6h)
        if not dry_run and self.repository.has_recent_alert(product.id, hours=6):
            logger.info(
                f"Alerta suprimido para '{product.nome}' devido à proteção anti-spam (alerta recente já enviado)."
            )
            return False

        console_msg = self.formatter.format_console_message(deal, product)
        logger.info(console_msg)

        sent_successfully = False
        canal = "console"

        # Tentar disparo via Telegram se configurado e não for dry_run
        if not dry_run and settings.has_telegram_configured:
            sent_successfully = await self._send_telegram(deal, product)
            if sent_successfully:
                canal = "telegram"
        else:
            if dry_run:
                logger.info("[DRY RUN] Simulação de alerta concluída com sucesso.")
            else:
                logger.warning(
                    "Telegram não configurado (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID ausentes). Alerta exibido apenas no console."
                )
            sent_successfully = True

        # Registrar alerta no banco
        if sent_successfully and not dry_run:
            alert = Alert(
                product_id=product.id,
                price_record_id=deal.source_id,
                motivo=deal.motivo_alerta or "desconto_identificado",
                detalhes=deal.justificativa,
                canal=canal,
            )
            self.repository.save_alert(alert)

        return sent_successfully

    async def _send_telegram(self, deal: DealAnalysis, product: Product) -> bool:
        """Dispara mensagem formatada via Telegram Bot API."""
        html_text = self.formatter.format_telegram_message(deal, product)
        res = await send_telegram_notification(text=html_text, parse_mode="HTML")
        if res.get("sent"):
            logger.success(f"Alerta enviado com sucesso via Telegram para '{product.nome}'!")
            return True
        return False
