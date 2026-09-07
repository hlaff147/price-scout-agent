"""Base class for PromoRadar subagents."""

import time
from abc import ABC, abstractmethod
from typing import Any

from loguru import logger


class BaseSubagent(ABC):
    """Classe base para subagentes especialistas com isolamento e métricas."""

    name: str = "base_subagent"
    role: str = "General Worker"

    @abstractmethod
    async def run(self, *args: Any, **kwargs: Any) -> Any:
        """Execução assíncrona da tarefa do subagente."""

    async def execute_safe(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Wrapper de segurança com medição de latência e captura de erros."""
        start_time = time.perf_counter()
        logger.debug(f"Iniciando subagente [{self.name}] ({self.role})...")
        try:
            result = await self.run(*args, **kwargs)
            duration = time.perf_counter() - start_time
            logger.debug(f"Subagente [{self.name}] concluído com sucesso em {duration:.2f}s.")
            return {"success": True, "result": result, "duration": duration, "error": None}
        except Exception as exc:  # noqa: BLE001
            duration = time.perf_counter() - start_time
            logger.error(f"Erro no subagente [{self.name}] após {duration:.2f}s: {exc}")
            return {"success": False, "result": None, "duration": duration, "error": str(exc)}
