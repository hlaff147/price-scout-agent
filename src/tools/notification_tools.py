"""ADK Tools for alert formatting and dispatch with credential redaction and HTML fallback."""

from __future__ import annotations

import re

import httpx
from loguru import logger

from src.config.settings import settings
from src.core.domain import redact_secrets

HTML_TAG_STRIP_RE = re.compile(r"<[^>]+>")


async def send_telegram_notification(
    text: str,
    parse_mode: str = "HTML",
    disable_preview: bool = False,
) -> dict:
    """Envia mensagem para o chat do Telegram configurado sem expor segredos em logs."""
    if not settings.has_telegram_configured:
        logger.warning("Telegram não configurado no .env. Notificação suprimida.")
        return {"sent": False, "reason": "not_configured"}

    token = settings.TELEGRAM_BOT_TOKEN or ""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload: dict[str, object] = {
        "chat_id": settings.TELEGRAM_CHAT_ID,
        "text": text,
        "disable_web_page_preview": disable_preview,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                logger.success("Alerta disparado com sucesso via Telegram.")
                return {"sent": True, "status_code": 200}

            # Degradação graciosa: se falhar por entidade HTML, reenvia em texto puro
            if resp.status_code == 400 and parse_mode:
                logger.warning(
                    "Telegram rejeitou formatação HTML (HTTP 400). Reenviando em texto puro seguro..."
                )
                plain_payload = {
                    "chat_id": settings.TELEGRAM_CHAT_ID,
                    "text": HTML_TAG_STRIP_RE.sub("", text),
                    "disable_web_page_preview": disable_preview,
                }
                retry_resp = await client.post(url, json=plain_payload)
                if retry_resp.status_code == 200:
                    logger.success("Alerta disparado via Telegram (modo fallback texto puro).")
                    return {"sent": True, "status_code": 200, "fallback": "plain_text"}

            safe_err = redact_secrets(resp.text, token)
            logger.error(f"Erro ao enviar Telegram (status {resp.status_code}): {safe_err}")
            return {"sent": False, "status_code": resp.status_code, "error": safe_err}
    except Exception as exc:  # noqa: BLE001
        safe_exc = redact_secrets(str(exc), token)
        logger.error(f"Exceção ao disparar Telegram: {safe_exc}")
        return {"sent": False, "error": safe_exc}
