"""Data models for PromoRadar using Pydantic."""

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class Source(BaseModel):
    """Fonte de coleta associada a um produto."""
    id: int | None = None
    product_id: str
    marketplace: str  # ex: "mercadolivre", "amazon", "kabum", "shopee", "aliexpress"
    url_produto: str
    metodo_coleta: str = "scraping_html"  # "scraping_html" | "browser" | "api"
    ativo: bool = True
    motivo_desativacao: str | None = None


class Product(BaseModel):
    """Produto monitorado pelo PromoRadar."""
    id: str
    nome: str
    keywords: list[str] = Field(default_factory=list)
    preco_alvo: float
    preco_maximo: float
    ativo: bool = True
    sources: list[Source] = Field(default_factory=list)


class PriceRecord(BaseModel):
    """Registro histórico de preço coletado em uma fonte."""
    id: int | None = None
    source_id: int
    preco: float
    preco_original: float | None = None
    moeda: str = "BRL"
    disponivel: bool = True
    cupom: str | None = None
    titulo_coletado: str | None = None
    url_encontrada: str | None = None
    coletado_em: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Alert(BaseModel):
    """Alerta disparado para o usuário quando uma condição vantajosa é atendida."""
    id: int | None = None
    product_id: str
    price_record_id: int
    motivo: str  # "abaixo_do_alvo" | "minimo_historico" | "cupom_novo" | "desconto_real"
    detalhes: str | None = None
    enviado_em: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    canal: str = "telegram"


class ScrapedData(BaseModel):
    """Dados brutos extraídos por uma skill de scraping."""
    marketplace: str
    success: bool
    titulo: str | None = None
    preco: float | None = None
    preco_original: float | None = None
    moeda: str = "BRL"
    disponivel: bool = True
    cupom: str | None = None
    url: str
    error_message: str | None = None


class DealAnalysis(BaseModel):
    """Resultado da análise de oportunidade de compra."""
    product_id: str
    source_id: int
    marketplace: str
    preco_atual: float
    preco_original_anunciado: float | None = None
    preco_minimo_historico: float | None = None
    preco_medio_historico: float | None = None
    desconto_anunciado_percent: float | None = None
    desconto_real_percent: float | None = None
    is_fake_discount: bool = False
    is_all_time_low: bool = False
    is_below_target: bool = False
    is_deal: bool = False
    motivo_alerta: str | None = None
    justificativa: str = ""
    url: str
    cupom: str | None = None
