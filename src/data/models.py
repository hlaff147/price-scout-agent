"""Data models for PromoRadar using Pydantic."""

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class PriorityLevel(str, Enum):
    """Níveis de prioridade de monitoramento de produtos."""
    HIGH = "high"      # Ciclo a cada 1 hora
    MEDIUM = "medium"  # Ciclo a cada 4 horas (padrão)
    LOW = "low"        # Ciclo a cada 12 horas


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
    prioridade: PriorityLevel = PriorityLevel.MEDIUM
    intervalo_customizado_min: int | None = None
    ultimo_ciclo_em: datetime | None = None
    proximo_ciclo_em: datetime | None = None
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


class MatchResult(BaseModel):
    """Resultado da deduplicação e correspondência semântica de variantes."""
    is_match: bool
    confidence: float = 1.0
    detected_variant: str | None = None
    divergence_reason: str | None = None
    method_used: str = "heuristic"  # "heuristic" | "embedding" | "llm_fallback"


class SelectorOverride(BaseModel):
    """Override persistido de seletores CSS auto-reparados para um marketplace."""
    id: int | None = None
    marketplace: str
    target_field: str  # "container", "titulo", "preco", "preco_original"
    original_selector: str
    healed_selector: str
    confidence_score: float = 1.0
    status: str = "active"  # "active" | "pending_review" | "rolled_back"
    sucessos_consecutivos: int = 0
    falhas_consecutivas: int = 0
    criado_em: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class HealingResult(BaseModel):
    """Resultado de uma tentativa de auto-reparo de seletores."""
    marketplace: str
    healed: bool
    proposed_selectors: dict[str, str] = Field(default_factory=dict)
    validation_success: bool = False
    validation_price: float | None = None
    validation_title: str | None = None
    reason: str = ""


class Coupon(BaseModel):
    """Representa um cupom ou código promocional detectado em um marketplace."""
    id: int | None = None
    marketplace: str
    product_id: str | None = None
    codigo: str
    descricao: str | None = None
    desconto_percentual: float | None = None
    desconto_fixo: float | None = None
    preco_minimo: float | None = None
    valido_ate: datetime | None = None
    primeira_vez_visto: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ultimo_visto: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ativo: bool = True



