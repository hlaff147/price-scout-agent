from src.core.ports.repository_port import IRepository
from src.data.database import default_db
from src.data.repository import Repository
from src.skills.detect_fake_discount.detector import DetectFakeDiscountSkill


def evaluate_fake_discount(
    current_price: float,
    original_price_announced: float | None = None,
    historical_avg: float | None = None,
    user_max_price: float | None = None,
) -> dict:
    """Verifica se um desconto anunciado é legítimo ou maquiado ('metade do dobro').

    Args:
        current_price: Preço atual praticado pela loja.
        original_price_announced: Preço original anunciado ('de').
        historical_avg: Média histórica dos últimos 60 dias.
        user_max_price: Preço máximo aceitável definido pelo usuário.

    Returns:
        Dicionário com percentual anunciado, percentual real e flag is_fake_discount.
    """
    detector = DetectFakeDiscountSkill()
    announced, real, is_fake = detector.execute(
        current_price=current_price,
        original_price_announced=original_price_announced,
        historical_avg=historical_avg,
        user_max_price=user_max_price,
    )
    return {
        "desconto_anunciado_percent": announced,
        "desconto_real_percent": real,
        "is_fake_discount": is_fake,
    }


def query_historical_prices(
    product_id: str,
    days: int = 90,
    repository: IRepository | None = None,
) -> dict:
    """Consulta os parâmetros históricos de preço de um produto no banco de dados.

    Args:
        product_id: Identificador único do produto.
        days: Janela de dias para histórico.
        repository: Instância opcional de IRepository (injeção de dependência).

    Returns:
        Dicionário contendo preço mínimo histórico e média histórica.
    """
    repo = repository or Repository(default_db)
    min_price = repo.get_historical_min_price(product_id)
    avg_price = repo.get_historical_average_price(product_id, days=days)
    return {
        "product_id": product_id,
        "minimo_historico": min_price,
        "media_historica": avg_price,
    }
