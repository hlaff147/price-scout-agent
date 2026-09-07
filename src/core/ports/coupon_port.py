"""Port interface for Coupon repository persistence."""

from abc import ABC, abstractmethod

from src.data.models import Coupon


class ICouponRepositoryPort(ABC):
    """Porta para persistência e consulta de cupons de desconto."""

    @abstractmethod
    def save_coupon(self, coupon: Coupon) -> Coupon:
        """Salva ou atualiza um cupom no banco de dados."""
        ...

    @abstractmethod
    def get_coupon(self, marketplace: str, codigo: str) -> Coupon | None:
        """Busca um cupom específico por marketplace e código."""
        ...

    @abstractmethod
    def list_active_coupons(self, marketplace: str | None = None) -> list[Coupon]:
        """Lista cupons ativos cadastrados, opcionalmente filtrados por marketplace."""
        ...

    @abstractmethod
    def is_coupon_recent(self, marketplace: str, codigo: str, hours: int = 24) -> bool:
        """Verifica se o cupom já foi registrado recentemente para evitar alertas duplicados."""
        ...
