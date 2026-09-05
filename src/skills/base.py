"""Base class for PromoRadar skills."""

from abc import ABC, abstractmethod
from typing import Any


class BaseSkill(ABC):
    """Classe base para todas as skills modulares do PromoRadar."""

    name: str = "base_skill"
    description: str = "Base skill description"

    @abstractmethod
    def execute(self, *args: Any, **kwargs: Any) -> Any:
        """Executa a lógica procedural da skill."""
