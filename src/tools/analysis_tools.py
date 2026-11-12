from src.core.ports.repository_port import IRepository
from src.data.database import default_db
from src.data.repository import Repository
from src.skills.detect_fake_discount.detector import DetectFakeDiscountSkill
from src.skills.price_statistics.analyzer import PriceStatisticalProfile, PriceStatisticsSkill


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


def compute_price_statistical_profile(
    product_id: str,
    current_price: float,
    days: int = 90,
    repository: IRepository | None = None,
    target_price: float | None = None,
    user_max_price: float | None = None,
    is_fake_discount: bool = False,
) -> PriceStatisticalProfile:
    """Calcula o perfil estatístico completo de um produto consultando o repositório.

    Args:
        product_id: Identificador do produto no banco.
        current_price: Preço atual a ser posicionado estatisticamente.
        days: Janela retroativa de dias no SQLite.
        repository: Repositório de dados opcional.
        target_price: Preço-alvo para Deal Score.
        user_max_price: Preço máximo tolerado.
        is_fake_discount: Se houve maquiagem no desconto.

    Returns:
        PriceStatisticalProfile preenchido.
    """
    repo = repository or Repository(default_db)
    records = repo.get_price_history(product_id, days=days)
    hist_prices = [r.preco for r in records if r.preco is not None and r.preco > 0]
    hist_dates = [r.coletado_em for r in records if r.preco is not None and r.preco > 0]

    skill = PriceStatisticsSkill()
    return skill.execute(
        historical_prices=hist_prices,
        current_price=current_price,
        historical_dates=hist_dates,
        target_price=target_price,
        user_max_price=user_max_price,
        is_fake_discount=is_fake_discount,
    )

