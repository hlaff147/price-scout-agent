"""Telegram Bot Driving Adapter interacting with PromoRadar core ports."""

import asyncio
import html
from typing import Any

import httpx
from loguru import logger

from src.agents.adk_runner import AdkMonitoringRunner
from src.config.settings import settings
from src.core.ports.product_management_port import IProductManagementPort
from src.core.ports.repository_port import IRepository
from src.data.database import default_db
from src.data.models import PriorityLevel, Product
from src.data.repository import Repository


class TelegramBotService:
    """Driving adapter para controle interativo do PromoRadar via Telegram."""

    def __init__(
        self,
        product_manager: IProductManagementPort | None = None,
        repository: IRepository | None = None,
        runner: AdkMonitoringRunner | None = None,
        token: str | None = None,
    ):
        self.repository = repository or Repository(default_db)
        self.product_manager = product_manager or (
            self.repository if isinstance(self.repository, IProductManagementPort) else Repository(default_db)
        )
        self.runner = runner or AdkMonitoringRunner(repository=self.repository)
        self.token = token or settings.TELEGRAM_BOT_TOKEN
        self._running = False

    def is_authorized(self, chat_id: int | str) -> bool:
        """Verifica se o chat_id está na lista de autorizados."""
        str_id = str(chat_id).strip()
        allowed = settings.allowed_chat_ids
        if not allowed:
            # Se não houver chat_id configurado, não aceita ninguém por segurança
            return False
        return str_id in allowed

    async def send_message(
        self,
        chat_id: int | str,
        text: str,
        parse_mode: str = "HTML",
    ) -> bool:
        """Envia mensagem de resposta via API do Telegram."""
        if not self.token:
            logger.warning("[TelegramBot] Token não configurado. Mensagem simulada no console:\n" + text)
            return True

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                return resp.status_code == 200
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[TelegramBot] Erro ao enviar mensagem para {chat_id}: {exc}")
            return False

    async def handle_command(self, chat_id: int | str, text: str) -> str:
        """Processa um comando de texto determinístico e retorna a resposta formatada em HTML."""
        if not self.is_authorized(chat_id):
            logger.warning(f"[TelegramBot] Acesso negado para chat_id {chat_id}")
            return f"⛔ <b>Acesso Negado:</b> Seu chat_id (<code>{chat_id}</code>) não está autorizado."

        clean_text = text.strip()
        if not clean_text.startswith("/"):
            return (
                "🤖 Olá! Envie <b>/help</b> para ver todos os comandos disponíveis para monitorar ofertas."
            )

        parts = clean_text.split()
        cmd = parts[0].lower().split("@")[0]  # Remove sufixo @nome_do_bot se houver
        args = parts[1:]

        if cmd in ("/start", "/help"):
            return (
                "🛰️ <b>PromoRadar Bot — Central de Monitoramento</b>\n\n"
                "<b>Comandos disponíveis:</b>\n"
                "📋 <b>/list</b> — Lista todos os produtos monitorados\n"
                "➕ <b>/add &lt;id&gt; &lt;nome&gt; &lt;alvo&gt; &lt;max&gt; [prioridade]</b> — Cadastra produto\n"
                "🎯 <b>/priority &lt;id&gt; &lt;high|medium|low&gt;</b> — Altera prioridade\n"
                "⏸️ <b>/pause &lt;id&gt;</b> — Pausa o monitoramento de um produto\n"
                "▶️ <b>/resume &lt;id&gt;</b> — Retoma o monitoramento\n"
                "🎟️ <b>/coupons [loja]</b> — Lista cupons de desconto ativos\n"
                "🔍 <b>/check [id]</b> — Dispara um ciclo imediato de checagem\n"
                "ℹ️ <b>/status</b> — Informações de banco e saúde do sistema"
            )

        if cmd in ("/coupons", "/cupons"):
            mkt = args[0].lower() if args else None
            coupons = self.repository.list_active_coupons(marketplace=mkt) if hasattr(self.repository, "list_active_coupons") else []
            if not coupons:
                filter_str = f" para <b>{html.escape(mkt.upper())}</b>" if mkt else ""
                return f"🎟️ Nenhum cupom ativo registrado no momento{filter_str}."

            lines = ["🎟️ <b>Cupons Ativos no PromoRadar:</b>\n"]
            for c in coupons:
                if c.desconto_percentual:
                    val_str = f"{c.desconto_percentual:.0f}% OFF"
                elif c.desconto_fixo:
                    val_str = f"R$ {c.desconto_fixo:.2f} OFF"
                else:
                    val_str = c.descricao or "Promocional"

                lines.append(
                    f"• [<b>{html.escape(c.marketplace.upper())}</b>] <code>{html.escape(c.codigo)}</code> — {html.escape(val_str)}"
                )
            return "\n".join(lines)

        if cmd == "/list":
            products = self.product_manager.list_products(active_only=False)
            if not products:
                return "📋 Nenhum produto cadastrado no momento. Use <b>/add</b> para cadastrar."

            lines = ["📋 <b>Produtos Monitorados no PromoRadar:</b>\n"]
            for p in products:
                status_icon = "🟢" if p.ativo else "🔴"
                prio_icon = "⚡" if p.prioridade == PriorityLevel.HIGH else ("⏱️" if p.prioridade == PriorityLevel.MEDIUM else "⏳")
                min_price = self.repository.get_historical_min_price(p.id)
                min_str = f"R$ {min_price:.2f}" if min_price else "Sem dados"

                lines.append(
                    f"{status_icon} <b>{html.escape(p.nome)}</b> (<code>{p.id}</code>)\n"
                    f"   • Prioridade: {prio_icon} {p.prioridade.value.upper()}\n"
                    f"   • Alvo: R$ {p.preco_alvo:.2f} | Teto: R$ {p.preco_maximo:.2f}\n"
                    f"   • Mínima histórica: {min_str}\n"
                )
            return "\n".join(lines)

        if cmd == "/priority":
            if len(args) < 2:
                return "⚠️ Uso incorreto. Exemplo: <code>/priority huawei-freebuds-pro-5 high</code>"
            p_id, p_prio = args[0], args[1].lower()
            try:
                priority = PriorityLevel(p_prio)
            except ValueError:
                return f"⚠️ Prioridade inválida '{p_prio}'. Use: <code>high</code>, <code>medium</code> ou <code>low</code>."

            success = self.product_manager.set_product_priority(p_id, priority)
            if success:
                return f"✅ Prioridade de <b>{html.escape(p_id)}</b> alterada para <b>{priority.value.upper()}</b>!"
            return f"❌ Produto com ID <code>{html.escape(p_id)}</code> não encontrado."

        if cmd in ("/pause", "/resume"):
            if not args:
                return f"⚠️ Informe o ID do produto. Exemplo: <code>{cmd} huawei-freebuds-pro-5</code>"
            p_id = args[0]
            new_active = (cmd == "/resume")
            success = self.product_manager.set_product_active(p_id, new_active)
            if success:
                action_txt = "retomado" if new_active else "pausado"
                return f"✅ Monitoramento de <b>{html.escape(p_id)}</b> {action_txt} com sucesso!"
            return f"❌ Produto com ID <code>{html.escape(p_id)}</code> não encontrado."

        if cmd == "/add":
            if len(args) < 4:
                return (
                    "⚠️ Sintaxe: <code>/add &lt;id&gt; &lt;nome&gt; &lt;preco_alvo&gt; &lt;preco_maximo&gt; [prioridade]</code>\n"
                    "Exemplo: <code>/add fone-sony Sony WH-1000XM5 1500 1800 high</code>"
                )
            p_id = args[0]
            # O último ou penúltimo pode ser a prioridade se coincidir com high/medium/low
            prio = PriorityLevel.MEDIUM
            if args[-1].lower() in ("high", "medium", "low"):
                prio = PriorityLevel(args[-1].lower())
                raw_numbers = args[-3:-1]
                nome_tokens = args[1:-3]
            else:
                raw_numbers = args[-2:]
                nome_tokens = args[1:-2]

            try:
                alvo = float(raw_numbers[0].replace(",", "."))
                teto = float(raw_numbers[1].replace(",", "."))
            except ValueError:
                return "⚠️ Valores de preço alvo e máximo devem ser numéricos."

            nome = " ".join(nome_tokens) if nome_tokens else p_id
            product = Product(
                id=p_id,
                nome=nome,
                keywords=[nome, p_id],
                preco_alvo=alvo,
                preco_maximo=teto,
                prioridade=prio,
                ativo=True,
            )
            self.product_manager.upsert_product(product)
            return (
                f"✅ <b>Produto cadastrado com sucesso!</b>\n"
                f"• ID: <code>{html.escape(p_id)}</code>\n"
                f"• Nome: <b>{html.escape(nome)}</b>\n"
                f"• Alvo: R$ {alvo:.2f} | Teto: R$ {teto:.2f}\n"
                f"• Prioridade: {prio.value.upper()}"
            )

        if cmd == "/check":
            target_id = args[0] if args else None
            status_msg = f"Iniciando checagem para '{target_id}'..." if target_id else "Iniciando checagem de todos os produtos ativos..."
            logger.info(f"[TelegramBot] {status_msg}")

            summary = await self.runner.run_cycle(
                product_id=target_id,
                dry_run=False,
                generate_report=False,
            )

            total = summary.get("total_products", 0)
            cycles = summary.get("cycles", [])
            total_deals = sum(c.get("deals_found", 0) for c in cycles if isinstance(c, dict))
            total_prices = sum(c.get("prices_collected", 0) for c in cycles if isinstance(c, dict))

            return (
                f"🔍 <b>Ciclo Concluído com Sucesso!</b>\n"
                f"• Produtos verificados: {total}\n"
                f"• Preços coletados: {total_prices}\n"
                f"• Ofertas vantajosas encontradas: <b>{total_deals}</b>\n"
                f"<i>Se alguma promoção foi identificada, o alerta detalhado foi emitido no canal.</i>"
            )

        if cmd == "/status":
            products = self.product_manager.list_products(active_only=False)
            active_count = len([p for p in products if p.ativo])
            return (
                "ℹ️ <b>Status do PromoRadar:</b>\n"
                f"• Produtos cadastrados: {len(products)} ({active_count} ativos)\n"
                f"• Banco de Dados: SQLite WAL (<code>{settings.DATABASE_PATH}</code>)\n"
                f"• Engine de Agentes: Google ADK 2.8+\n"
                "• Status: 🟢 Online e operante"
            )

        return f"❓ Comando <code>{html.escape(cmd)}</code> não reconhecido. Digite <b>/help</b>."

    async def process_update(self, update: dict[str, Any]) -> None:
        """Processa um evento de update recebido da API do Telegram."""
        message = update.get("message") or update.get("edited_message")
        if not message:
            return

        chat = message.get("chat", {})
        chat_id = chat.get("id")
        text = message.get("text", "")

        if not chat_id or not text:
            return

        logger.debug(f"[TelegramBot] Mensagem recebida de {chat_id}: {text}")
        response_text = await self.handle_command(chat_id, text)
        await self.send_message(chat_id, response_text)

    async def start_polling(self, poll_interval: float = 1.0) -> None:
        """Inicia loop assíncrono de Long Polling para receber atualizações do Telegram."""
        if not self.token:
            logger.error("[TelegramBot] TELEGRAM_BOT_TOKEN não definido. Polling não iniciado.")
            return

        self._running = True
        offset = 0
        logger.info("🤖 PromoRadar Telegram Bot iniciado em modo Long Polling...")

        async with httpx.AsyncClient(timeout=40.0) as client:
            while self._running:
                try:
                    url = f"https://api.telegram.org/bot{self.token}/getUpdates"
                    params = {"offset": offset, "timeout": 25}
                    resp = await client.get(url, params=params)

                    if resp.status_code == 200:
                        data = resp.json()
                        updates = data.get("result", [])
                        for update in updates:
                            update_id = update["update_id"]
                            offset = max(offset, update_id + 1)
                            await self.process_update(update)
                    elif resp.status_code == 409:
                        logger.warning("[TelegramBot] Conflito de webhook/polling ativo. Aguardando 5s...")
                        await asyncio.sleep(5.0)
                    else:
                        logger.error(f"[TelegramBot] Erro HTTP {resp.status_code} ao buscar updates: {resp.text}")
                        await asyncio.sleep(poll_interval)

                except asyncio.CancelledError:
                    break
                except Exception as exc:  # noqa: BLE001
                    logger.error(f"[TelegramBot] Exceção no polling: {exc}")
                    await asyncio.sleep(poll_interval)

    def stop_polling(self) -> None:
        """Para o loop de polling."""
        self._running = False
