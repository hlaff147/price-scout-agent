"""Tests for product priority scheduling, fault isolation, and domain rate limiting."""

import asyncio
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from src.agents.adk_runner import AdkMonitoringRunner
from src.data.database import Database
from src.data.models import (
    PriorityLevel,
    Product,
    Source,
)
from src.data.repository import Repository, calculate_next_run
from src.tools.rate_limiter import DomainRateLimiter


@pytest.fixture
def temp_repo():
    """Repositório isolado em memória com banco SQLite fresco."""
    db = Database(db_path=":memory:")
    return Repository(db)


def test_product_priority_and_calculate_next_run():
    """Testa o cálculo do próximo ciclo de execução com base na prioridade."""
    base_time = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)

    p_high = Product(
        id="p1", nome="Prod High", preco_alvo=100, preco_maximo=150, prioridade=PriorityLevel.HIGH
    )
    assert calculate_next_run(p_high, from_time=base_time) == base_time + timedelta(hours=1)

    p_med = Product(
        id="p2", nome="Prod Med", preco_alvo=100, preco_maximo=150, prioridade=PriorityLevel.MEDIUM
    )
    assert calculate_next_run(p_med, from_time=base_time) == base_time + timedelta(hours=4)

    p_low = Product(
        id="p3", nome="Prod Low", preco_alvo=100, preco_maximo=150, prioridade=PriorityLevel.LOW
    )
    assert calculate_next_run(p_low, from_time=base_time) == base_time + timedelta(hours=12)

    p_custom = Product(
        id="p4",
        nome="Prod Custom",
        preco_alvo=100,
        preco_maximo=150,
        prioridade=PriorityLevel.LOW,
        intervalo_customizado_min=45,
    )
    assert calculate_next_run(p_custom, from_time=base_time) == base_time + timedelta(minutes=45)


def test_repository_priority_operations(temp_repo):
    """Testa persistência, consulta e ordenação por prioridade no repositório."""
    now = datetime.now(timezone.utc)

    p_low = Product(
        id="item-low",
        nome="Item Baixa",
        preco_alvo=100,
        preco_maximo=150,
        prioridade=PriorityLevel.LOW,
        proximo_ciclo_em=now - timedelta(minutes=10),
    )
    p_high = Product(
        id="item-high",
        nome="Item Alta",
        preco_alvo=200,
        preco_maximo=300,
        prioridade=PriorityLevel.HIGH,
        proximo_ciclo_em=now - timedelta(minutes=5),
    )
    p_future = Product(
        id="item-future",
        nome="Item Futuro",
        preco_alvo=50,
        preco_maximo=80,
        prioridade=PriorityLevel.HIGH,
        proximo_ciclo_em=now + timedelta(hours=2),
    )

    temp_repo.upsert_product(p_low)
    temp_repo.upsert_product(p_high)
    temp_repo.upsert_product(p_future)

    # Verifica get_due_products: deve retornar apenas os vencidos, com alta prioridade primeiro
    due = temp_repo.get_due_products()
    assert len(due) == 2
    assert due[0].id == "item-high"
    assert due[1].id == "item-low"

    # Atualiza prioridade
    assert temp_repo.set_product_priority("item-low", PriorityLevel.HIGH)
    updated = temp_repo.get_product("item-low")
    assert updated.prioridade == PriorityLevel.HIGH

    # Desativa produto
    assert temp_repo.set_product_active("item-high", False)
    due_after_deactivation = temp_repo.get_due_products()
    assert len(due_after_deactivation) == 1
    assert due_after_deactivation[0].id == "item-low"


@pytest.mark.asyncio
async def test_domain_rate_limiter_spacing():
    """Testa se o DomainRateLimiter espaça requisições concorrentes para o mesmo domínio."""
    limiter = DomainRateLimiter(default_min_delay=0.1)
    limiter.DEFAULT_DELAYS = {"test-mkt.com": 0.2}

    timestamps = []

    async def worker(idx: int):
        async with limiter.acquire("https://test-mkt.com/item"):
            timestamps.append(time.time())

    # Dispara 3 workers simultâneos para o mesmo domínio
    await asyncio.gather(worker(1), worker(2), worker(3))

    assert len(timestamps) == 3
    # Verifica que o espaçamento entre chamadas consecutivas respeitou o delay mínimo (~0.2s)
    for i in range(1, len(timestamps)):
        diff = timestamps[i] - timestamps[i - 1]
        assert diff >= 0.18, f"Intervalo entre chamadas ({diff:.3f}s) menor que o esperado"


@pytest.mark.asyncio
async def test_domain_rate_limiter_independent_domains():
    """Testa se domínios distintos não bloqueiam a execução um do outro."""
    limiter = DomainRateLimiter(default_min_delay=0.5)

    start = time.time()

    async def hit(domain: str):
        async with limiter.acquire(domain):
            await asyncio.sleep(0.05)

    # Dispara chamadas concorrentes para domínios diferentes
    await asyncio.gather(
        hit("https://amazon.com.br/p1"),
        hit("https://mercadolivre.com.br/p2"),
        hit("https://kabum.com.br/p3"),
    )

    total_time = time.time() - start
    # Devem rodar praticamente em paralelo (tempo bem inferior a 3 * 0.5s)
    assert total_time < 0.6


@pytest.mark.asyncio
async def test_adk_runner_fault_isolation_across_products(temp_repo):
    """Testa que a falha catastrófica em um produto não interrompe os demais."""
    p1 = Product(
        id="prod-fail",
        nome="Produto Falho",
        preco_alvo=100,
        preco_maximo=150,
        prioridade=PriorityLevel.HIGH,
        sources=[Source(product_id="prod-fail", marketplace="ml", url_produto="http://fail.com")],
    )
    p2 = Product(
        id="prod-ok",
        nome="Produto Sucesso",
        preco_alvo=200,
        preco_maximo=300,
        prioridade=PriorityLevel.MEDIUM,
        sources=[Source(product_id="prod-ok", marketplace="amazon", url_produto="http://ok.com")],
    )

    temp_repo.upsert_product(p1)
    temp_repo.upsert_product(p2)

    runner = AdkMonitoringRunner(repository=temp_repo)

    # Mocka _run_single_product_adk para lançar exceção apenas no primeiro produto
    async def fake_run_single(product, **kwargs):
        if product.id == "prod-fail":
            raise RuntimeError("Falha de rede irreparável no produto 1")
        return {
            "product_id": product.id,
            "prices_collected": 1,
            "deals_found": 0,
            "errors": 0,
        }

    with (
        patch.object(runner, "_run_single_product_adk", side_effect=fake_run_single),
        patch.object(runner, "run_cycle", wraps=runner.run_cycle),
        patch("src.orchestrator.orchestrator.Orchestrator.load_products_from_yaml"),
    ):
        summary = await runner.run_cycle(dry_run=True, generate_report=False)

    assert summary["total_products"] == 2
    assert len(summary["cycles"]) == 2

    # Produto 1 falhou com registro de erro isolado
    cycle_1 = summary["cycles"][0]
    assert cycle_1["product_id"] == "prod-fail"
    assert cycle_1["success"] is False
    assert "Falha de rede irreparável" in cycle_1["error"]

    # Produto 2 executou com sucesso
    cycle_2 = summary["cycles"][1]
    assert cycle_2["product_id"] == "prod-ok"
    assert cycle_2["prices_collected"] == 1
