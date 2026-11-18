"""Pure domain entities, value contracts, and cycle result schemas for PromoRadar."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class PriorityLevel(str, Enum):
    """Níveis de prioridade de monitoramento de produtos."""

    HIGH = "high"  # Ciclo a cada 1 hora
    MEDIUM = "medium"  # Ciclo a cada 4 horas (padrão)
    LOW = "low"  # Ciclo a cada 12 horas


class Source(BaseModel):
    """Fonte de coleta associada a um produto."""

    id: int | None = None
    product_id: str
    marketplace: str
    url_produto: str
    metodo_coleta: str = "scraping_html"
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
    price_record_id: int | None = None
    motivo: str
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
    price_record_id: int | None = None
    marketplace: str
    preco_atual: float
    preco_efetivo: float | None = None
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
    z_score: float | None = None
    robust_z_score: float | None = None
    percentile_rank: float | None = None
    cv_volatilidade_percent: float | None = None
    tendencia_diaria_brl: float | None = None
    regime_preco: str | None = None
    deal_score: float | None = None
    match_confidence: float | None = None


class MatchResult(BaseModel):
    """Resultado da deduplicação e correspondência semântica de variantes.

    Invariante: `confidence` em [0.0, 1.0] expressa a confiança na decisão `is_match`;
    `match_probability` expressa P(is_match == True) calibrada em [0.0, 1.0].
    """

    is_match: bool
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    detected_variant: str | None = None
    divergence_reason: str | None = None
    method_used: str = "heuristic"

    @property
    def match_probability(self) -> float:
        clamped = max(0.0, min(1.0, self.confidence))
        return clamped if self.is_match else round(1.0 - clamped, 4)


class SelectorOverride(BaseModel):
    """Override persistido de seletores CSS auto-reparados para um marketplace."""

    id: int | None = None
    marketplace: str
    target_field: str
    original_selector: str
    healed_selector: str
    confidence_score: float = 1.0
    status: str = "active"
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


class ProductCycleResult(BaseModel):
    """Contrato tipado para o resultado de monitoramento de um produto em um ciclo."""

    product_id: str
    product_name: str | None = None
    success: bool = True
    error: str | None = None
    sources_checked: int = 0
    prices_collected: int = 0
    deals_found: int = 0
    notifications_sent: int = 0
    no_results: int = 0
    errors: int = 0
    analyses: list[DealAnalysis] = Field(default_factory=list)
    report_path: str | None = None

    def to_summary_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "product_id": self.product_id,
            "success": self.success,
            "sources_checked": self.sources_checked,
            "prices_collected": self.prices_collected,
            "deals_found": self.deals_found,
            "notifications_sent": self.notifications_sent,
            "no_results": self.no_results,
            "errors": self.errors,
            "analyses": self.analyses,
            "report_path": self.report_path,
        }
        if self.product_name is not None:
            data["product_name"] = self.product_name
        if self.error is not None:
            data["error"] = self.error
        return data


class MonitoringCycleSummary(BaseModel):
    """Resumo consolidado e tipado de uma rodada completa de monitoramento."""

    cycle_id: str
    total_products: int = 0
    cycles: list[ProductCycleResult] = Field(default_factory=list)

    def to_legacy_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "total_products": self.total_products,
            "cycles": [c.to_summary_dict() for c in self.cycles],
        }
