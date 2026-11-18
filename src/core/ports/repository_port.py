"""Port interface for data persistence adapters."""

from abc import ABC, abstractmethod
from datetime import datetime

from src.core.models import Alert, Coupon, PriceRecord, Product, Source


class IRepository(ABC):
    """Porta para adapters de repositório e persistência (SQLite, PostgreSQL, etc.)."""

    # Produtos
    @abstractmethod
    def upsert_product(self, product: Product) -> Product: ...

    def sync_catalog_product(self, product: Product) -> Product:
        """Sincroniza metadados de catálogo preservando estado operacional (pausa/prioridade manual)."""
        return self.upsert_product(product)

    @abstractmethod
    def get_product(self, product_id: str) -> Product | None: ...

    @abstractmethod
    def list_active_products(self) -> list[Product]: ...

    def get_due_products(self) -> list[Product]:
        """Retorna produtos ativos elegíveis para checagem no ciclo atual."""
        return self.list_active_products()

    def update_product_schedule(
        self, product_id: str, last_run: datetime, next_run: datetime
    ) -> None:
        """Atualiza agendamento de execução do produto (no-op padrão em mocks mínimos)."""
        return

    # Fontes
    @abstractmethod
    def upsert_source(self, source: Source) -> Source: ...

    @abstractmethod
    def get_sources_for_product(self, product_id: str) -> list[Source]: ...

    @abstractmethod
    def get_active_sources_for_product(self, product_id: str) -> list[Source]: ...

    # Registros de Preço
    @abstractmethod
    def save_price_record(self, record: PriceRecord) -> PriceRecord: ...

    @abstractmethod
    def get_price_history(self, product_id: str, days: int = 90) -> list[PriceRecord]: ...

    @abstractmethod
    def get_price_history_by_source(self, source_id: int, days: int = 90) -> list[PriceRecord]: ...

    @abstractmethod
    def get_historical_min_price(self, product_id: str) -> float | None: ...

    @abstractmethod
    def get_historical_average_price(self, product_id: str, days: int = 60) -> float | None: ...

    # Alertas
    @abstractmethod
    def save_alert(self, alert: Alert) -> Alert: ...

    @abstractmethod
    def has_recent_alert(self, product_id: str, hours: int = 12) -> bool: ...

    @abstractmethod
    def get_recent_alerts(self, product_id: str, limit: int = 10) -> list[Alert]: ...

    # Cupons (extensão opcional segura para implementações completas)
    def save_coupon(self, coupon: Coupon) -> Coupon:
        return coupon

    def list_active_coupons(self, marketplace: str | None = None) -> list[Coupon]:
        return []
