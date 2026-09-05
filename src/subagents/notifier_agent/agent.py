"""Notifier subagent for Telegram dispatch and console fallback."""

import httpx
from loguru import logger

from src.config.settings import settings
from src.data.models import Alert, DealAnalysis, Product
from src.data.repository import Repository
from src.skills.format_alert.formatter import FormatAlertSkill
from src.subagents.base import BaseSubagent


class NotifierSubagent(BaseSubagent):
    """Subagente responsável por formatar e disparar notificações de ofertas."""

    name = "notifier_agent"
    role = "Alert & Notification Dispatcher"

    def __init__(self, repository: Repository | None = None):
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
        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
        html_text = self.formatter.format_telegram_message(deal, product)

        payload = {
            "chat_id": settings.TELEGRAM_CHAT_ID,
            "text": html_text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    logger.success(f"Alerta enviado com sucesso via Telegram para '{product.nome}'!")
                    return True
                else:
                    logger.error(f"Erro ao enviar Telegram (status {resp.status_code}): {resp.text}")
                    return False
        except Exception as exc:
            logger.error(f"Exceção ao disparar notificação no Telegram: {exc}")
            return False
