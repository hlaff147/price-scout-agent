"""Subagent for self-healing scraping selectors using Gemini LLM with sandbox validation."""

import json
import os
import re
from typing import Any

from bs4 import BeautifulSoup
from loguru import logger

from src.core.ports.selector_port import IHealerAgentPort, ISelectorRepositoryPort
from src.data.database import default_db
from src.data.models import HealingResult, Product, SelectorOverride
from src.data.repository import Repository
from src.subagents.base import BaseSubagent
from src.subagents.healing_agent.sanitizer import sanitize_html_for_llm


class GeminiHealerSubagent(BaseSubagent, IHealerAgentPort):
    """Subagente responsável por propor e validar novos seletores CSS quando o layout do site quebra."""

    name = "gemini_healer_agent"
    role = "CSS Selector Self-Healing Agent"

    def __init__(
        self,
        repository: ISelectorRepositoryPort | None = None,
        llm_client: Any | None = None,
    ):
        self.repository = repository or Repository(default_db)
        self.llm_client = llm_client

    async def run(self, *args: Any, **kwargs: Any) -> HealingResult:
        """Executa a rotina de auto-reparo do subagente."""
        return await self.heal(*args, **kwargs)

    def validate_selectors_in_sandbox(
        self,
        html_content: str,
        selectors: dict[str, str],
        product: Product,
    ) -> tuple[bool, float | None, str | None, str]:
        """Executa os seletores propostos em um ambiente sandbox isolado para validação rigorosa.

        Retorna (sucesso, preco_encontrado, titulo_encontrado, justificativa).
        """
        if not html_content or not selectors:
            return False, None, None, "HTML ou seletores ausentes"

        container_sel = selectors.get("container")
        title_sel = selectors.get("titulo")
        price_sel = selectors.get("preco")

        if not (title_sel and price_sel):
            return False, None, None, "Seletores incompletos: 'titulo' e 'preco' são obrigatórios"

        soup = BeautifulSoup(html_content, "html.parser")

        # Se houver seletor de container, busca dentro do primeiro container
        if container_sel:
            container = soup.select_one(container_sel)
            if not container:
                return False, None, None, f"Seletor de container '{container_sel}' não encontrou nenhum elemento"
            scope = container
        else:
            scope = soup

        # 1. Extração e validação do título
        title_el = scope.select_one(title_sel)
        if not title_el:
            return False, None, None, f"Seletor de título '{title_sel}' não encontrou nenhum elemento"

        extracted_title = title_el.get_text(strip=True)
        title_lower = extracted_title.lower()

        # Verifica se o título tem relação com o produto
        has_keyword = any(kw.lower() in title_lower for kw in product.keywords if len(kw) >= 3)
        if not has_keyword and product.nome.lower() not in title_lower:
            return (
                False,
                None,
                extracted_title,
                f"Título extraído ('{extracted_title}') não contém palavras-chave de '{product.nome}'",
            )

        # 2. Extração e validação do preço
        price_el = scope.select_one(price_sel)
        if not price_el:
            return False, None, extracted_title, f"Seletor de preço '{price_sel}' não encontrou elemento"

        price_text = price_el.get_text(strip=True)
        # Limpa texto numérico de moeda brasileira ou padrão
        num_clean = re.sub(r"[^\d,.]", "", price_text)
        if not num_clean:
            return False, None, extracted_title, f"Texto de preço '{price_text}' não contém números válidos"

        try:
            if "," in num_clean and "." in num_clean:
                # Ex: 1.234,56
                num_clean = num_clean.replace(".", "").replace(",", ".")
            elif "," in num_clean:
                num_clean = num_clean.replace(",", ".")
            extracted_price = float(num_clean)
        except ValueError:
            return False, None, extracted_title, f"Falha na conversão de preço '{price_text}'"

        # 3. Plausibilidade do preço (evita zero, centavos de frete ou valores absurdos)
        min_plausible = product.preco_alvo * 0.3
        max_plausible = product.preco_maximo * 3.0

        if not (min_plausible <= extracted_price <= max_plausible):
            return (
                False,
                extracted_price,
                extracted_title,
                f"Preço R$ {extracted_price:.2f} fora da faixa plausível (R$ {min_plausible:.2f} a R$ {max_plausible:.2f})",
            )

        return True, extracted_price, extracted_title, "Validação em sandbox concluída com sucesso"

    async def _call_gemini_for_selectors(
        self,
        marketplace: str,
        product: Product,
        sanitized_html: str,
        current_selectors: dict[str, str],
    ) -> dict[str, str] | None:
        """Chama a API do Gemini para inspecionar o markup e propor novos seletores CSS."""
        if self.llm_client:
            return await self.llm_client(marketplace, product, sanitized_html, current_selectors)

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            logger.warning("[SelfHealing] GEMINI_API_KEY não configurada no ambiente. Auto-reparo ignorado.")
            return None

        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        prompt = f"""
Você é um engenheiro especialista em web scraping e seletores CSS resilientes.
Um scraper para o marketplace '{marketplace}' falhou ao extrair o produto '{product.nome}'.

Seletores antigos que pararam de funcionar:
{json.dumps(current_selectors, indent=2)}

Analise o fragmento de HTML sanitizado abaixo e identifique novos seletores CSS válidos e modernos para:
1. "container": elemento pai do card/item do produto
2. "titulo": elemento contendo o nome/título do produto
3. "preco": elemento contendo o preço atual

HTML Sanitizado:
```html
{sanitized_html}
```

Responda ESTRITAMENTE em formato JSON com as chaves "container", "titulo", "preco". Exemplo:
{{"container": "div.product-card", "titulo": "h2.title", "preco": "span.price"}}
"""

        try:
            response = await client.aio.models.generate_content(
                model="gemini-1.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            )
            raw_text = response.text.strip()
            data = json.loads(raw_text)
            return data if isinstance(data, dict) else None
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[SelfHealing] Falha na chamada da LLM Gemini: {exc}")
            return None

    async def heal(
        self,
        marketplace: str,
        product: Product,
        html_content: str,
        current_selectors: dict[str, str],
    ) -> HealingResult:
        """Executa o ciclo completo de self-healing com sanitização, chamada de IA e validação."""
        mkt = marketplace.lower()

        # 1. Checagem do Circuit Breaker
        if self.repository.has_exceeded_healing_attempts(mkt, max_attempts=2, hours=24):
            msg = f"Circuit Breaker ativo para [{mkt.upper()}]. Limite de tentativas de reparo em 24h atingido."
            logger.warning(f"[SelfHealing] {msg}")
            return HealingResult(marketplace=mkt, healed=False, reason=msg)

        self.repository.record_healing_attempt(mkt)

        # 2. Sanitizar HTML
        sanitized = sanitize_html_for_llm(html_content)
        if not sanitized:
            return HealingResult(
                marketplace=mkt,
                healed=False,
                reason="HTML vazio ou sem conteúdo aproveitável",
            )

        logger.info(f"🩺 [SelfHealing] Acionando subagente reparador para [{mkt.upper()}] no produto '{product.nome}'...")

        # 3. Consulta ao Modelo de Linguagem
        proposed = await self._call_gemini_for_selectors(
            marketplace=mkt,
            product=product,
            sanitized_html=sanitized,
            current_selectors=current_selectors,
        )

        if not proposed:
            return HealingResult(
                marketplace=mkt,
                healed=False,
                reason="Modelo não retornou seletores utilizáveis",
            )

        # 4. Validação Obrigatória em Sandbox (NUNCA aplicar sem testar!)
        is_valid, price, title, reason = self.validate_selectors_in_sandbox(
            html_content=html_content,
            selectors=proposed,
            product=product,
        )

        if not is_valid:
            logger.warning(
                f"🩺 [SelfHealing] Seletores propostos para [{mkt.upper()}] REJEITADOS na validação sandbox: {reason}"
            )
            return HealingResult(
                marketplace=mkt,
                healed=False,
                proposed_selectors=proposed,
                validation_success=False,
                reason=reason,
            )

        # 5. Persistência dos novos seletores aprovados
        for field_name, selector_val in proposed.items():
            override = SelectorOverride(
                marketplace=mkt,
                target_field=field_name,
                original_selector=current_selectors.get(field_name, ""),
                healed_selector=selector_val,
                status="active",
                confidence_score=0.95,
            )
            self.repository.save_override(override)

        logger.info(
            f"🩺 [SelfHealing] ✅ Reparo APROVADO para [{mkt.upper()}]! "
            f"Preço validado: R$ {price:.2f} | Título: '{title}'"
        )

        return HealingResult(
            marketplace=mkt,
            healed=True,
            proposed_selectors=proposed,
            validation_success=True,
            validation_price=price,
            validation_title=title,
            reason="Reparo validado e persistido com sucesso",
        )
