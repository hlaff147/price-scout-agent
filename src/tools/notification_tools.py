"""ADK Tools for alert formatting and dispatch."""

import httpx
from loguru import logger

from src.config.settings import settings


async def send_telegram_notification(
    text: str,
    parse_mode: str = "HTML",
    disable_preview: bool = False,
) -> dict:
    """Envia uma mensagem formatada para o chat do Telegram configurado.

    Args:
        text: Mensagem a ser enviada (HTML ou texto puro).
        parse_mode: Modo de parsing do Telegram ('HTML' ou 'MarkdownV2').
        disable_preview: Se True, desabilita pré-visualização de links.

    Returns:
        Dicionário com status de envio e resposta da API do Telegram.
    """
    if not settings.has_telegram_configured:
        logger.warning("Telegram não configurado no .env. Notificação suprimida.")
        return {"sent": False, "reason": "not_configured"}

    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": settings.TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": disable_preview,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                logger.success("Alerta disparado com sucesso via Telegram.")
                return {"sent": True, "status_code": 200}
            else:
                logger.error(f"Erro ao enviar Telegram (status {resp.status_code}): {resp.text}")
                return {"sent": False, "status_code": resp.status_code, "error": resp.text}
    except Exception as exc:
        logger.error(f"Exceção ao disparar Telegram: {exc}")
        return {"sent": False, "error": str(exc)}
