"""Port interface for product management and scheduling operations."""

from abc import ABC, abstractmethod
from datetime import datetime

from src.data.models import PriorityLevel, Product


class IProductManagementPort(ABC):
    """Porta para gestão de produtos monitorados, prioridades e despacho."""

    @abstractmethod
    def upsert_product(self, product: Product) -> Product:
        """Cadastra ou atualiza um produto no sistema."""
        ...

    @abstractmethod
    def get_product(self, product_id: str) -> Product | None:
        """Recupera um produto por seu ID."""
        ...

    @abstractmethod
    def list_products(self, active_only: bool = True) -> list[Product]:
        """Lista os produtos cadastrados."""
        ...

    @abstractmethod
    def set_product_priority(self, product_id: str, priority: PriorityLevel) -> bool:
        """Altera o nível de prioridade de um produto."""
        ...

    @abstractmethod
    def set_product_active(self, product_id: str, active: bool) -> bool:
        """Ativa ou desativa o monitoramento de um produto."""
        ...

    @abstractmethod
    def get_due_products(self) -> list[Product]:
        """Retorna os produtos que estão prontos para execução no ciclo atual."""
        ...

    @abstractmethod
    def update_product_schedule(
        self, product_id: str, last_run: datetime, next_run: datetime
    ) -> None:
        """Atualiza os timestamps do último ciclo e do próximo agendamento."""
        ...
