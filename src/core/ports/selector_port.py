"""Port interface for selector override persistence and healing adapters."""

from abc import ABC, abstractmethod

from src.data.models import HealingResult, Product, SelectorOverride


class ISelectorRepositoryPort(ABC):
    """Porta para persistência e consulta de seletores aprendidos e circuito de segurança."""

    @abstractmethod
    def get_active_overrides(self, marketplace: str) -> dict[str, str]:
        """Retorna os seletores ativos para o marketplace (field -> selector)."""
        ...

    @abstractmethod
    def save_override(self, override: SelectorOverride) -> SelectorOverride:
        """Salva ou atualiza um seletor reparado."""
        ...

    @abstractmethod
    def has_exceeded_healing_attempts(
        self, marketplace: str, max_attempts: int = 2, hours: int = 24
    ) -> bool:
        """Verifica se o limite de tentativas de reparo foi atingido (Circuit Breaker)."""
        ...

    @abstractmethod
    def record_healing_attempt(self, marketplace: str) -> None:
        """Registra uma tentativa de reparo para o circuito de segurança."""
        ...


class IHealerAgentPort(ABC):
    """Porta para o subagente LLM reparador de seletores."""

    @abstractmethod
    async def heal(
        self,
        marketplace: str,
        product: Product,
        html_content: str,
        current_selectors: dict[str, str],
    ) -> HealingResult:
        """Propõe novos seletores para o marketplace após inspeção do HTML."""
        ...
