"""Skill de análise estatística de séries temporais de preço e detecção de anomalias."""

from __future__ import annotations

import math
import statistics
from datetime import datetime
from typing import Sequence

from pydantic import BaseModel, Field

from src.skills.base import BaseSkill


class PriceStatisticalProfile(BaseModel):
    """Perfil estatístico consolidado da série temporal de preços de um produto."""

    sample_size: int
    current_price: float
    min_price: float
    max_price: float
    mean: float
    median: float
    std_dev: float
    mad: float = Field(description="Median Absolute Deviation (Desvio Absoluto Mediano)")
    q1: float = Field(description="Primeiro Quartil (25%)")
    q3: float = Field(description="Terceiro Quartil (75%)")
    iqr: float = Field(description="Intervalo Interquartil (Q3 - Q1)")
    cv_percent: float = Field(description="Coeficiente de Variação (Volatilidade %)")
    z_score: float = Field(description="Z-Score Clássico vs Média")
    robust_z_score: float = Field(description="Z-Score Robusto via MAD vs Mediana")
    percentile_rank: float = Field(description="Posição percentílica empírica (0-100%)")
    trend_slope_brl_per_day: float = Field(description="Inclinação da tendência linear em R$/dia")
    regime_preco: str = Field(description="Classificação do momento de preço")
    deal_confidence_score: float = Field(description="Score ponderado de oportunidade (0 a 100)")


class PriceStatisticsSkill(BaseSkill):
    """Calcula métricas de Data Science sobre a série histórica de cotações."""

    name = "price_statistics"
    description = "Analisa distribuição estatística, Z-Score robusto, volatilidade e tendência linear de preços."

    def execute(
        self,
        historical_prices: Sequence[float],
        current_price: float,
        historical_dates: Sequence[datetime] | None = None,
        target_price: float | None = None,
        user_max_price: float | None = None,
        is_fake_discount: bool = False,
    ) -> PriceStatisticalProfile:
        """Calcula o perfil estatístico completo para a cotação atual.

        Args:
            historical_prices: Lista cronológica de preços históricos válidos.
            current_price: Preço atual coletado a ser posicionado contra o histórico.
            historical_dates: Opcional: timestamps dos preços para estimar tendência diária.
            target_price: Preço-alvo desejado pelo usuário (para Deal Score).
            user_max_price: Teto máximo aceitável pelo usuário.
            is_fake_discount: Flag indicando se a loja praticou maquiagem de preço.

        Returns:
            PriceStatisticalProfile preenchido.
        """
        all_prices = [float(p) for p in historical_prices if p is not None and p > 0]
        n = len(all_prices)

        # Se não houver histórico anterior suficiente, usa a própria cotação atual como referência inicial
        if n == 0:
            return PriceStatisticalProfile(
                sample_size=1,
                current_price=round(current_price, 2),
                min_price=round(current_price, 2),
                max_price=round(current_price, 2),
                mean=round(current_price, 2),
                median=round(current_price, 2),
                std_dev=0.0,
                mad=0.0,
                q1=round(current_price, 2),
                q3=round(current_price, 2),
                iqr=0.0,
                cv_percent=0.0,
                z_score=0.0,
                robust_z_score=0.0,
                percentile_rank=50.0,
                trend_slope_brl_per_day=0.0,
                regime_preco="NOVO_SEM_HISTORICO",
                deal_confidence_score=50.0 if not (target_price and current_price <= target_price) else 75.0,
            )

        sorted_prices = sorted(all_prices)
        min_p = sorted_prices[0]
        max_p = sorted_prices[-1]
        mean_val = statistics.mean(all_prices)
        median_val = statistics.median(all_prices)
        std_val = statistics.stdev(all_prices) if n > 1 else 0.0

        # 1. Median Absolute Deviation (MAD)
        abs_deviations = [abs(p - median_val) for p in all_prices]
        mad_val = statistics.median(abs_deviations)

        # 2. Quartis e IQR (Tukey)
        if n >= 4:
            # statistics.quantiles método inclusivo
            quantiles = statistics.quantiles(sorted_prices, n=4, method="inclusive")
            q1_val = quantiles[0]
            q3_val = quantiles[2]
        else:
            q1_val = sorted_prices[0]
            q3_val = sorted_prices[-1]
        iqr_val = max(0.0, q3_val - q1_val)

        # 3. Volatilidade (Coeficiente de Variação CV%)
        cv_val = (std_val / mean_val * 100.0) if mean_val > 0 else 0.0

        # 4. Z-Score Clássico
        if std_val > 0.001:
            z_score = (current_price - mean_val) / std_val
        else:
            z_score = 0.0

        # 5. Z-Score Robusto (Modified Z-Score)
        # Multiplicador 0.6745 alinha MAD com a distribuição normal
        if mad_val > 0.001:
            robust_z = 0.6745 * (current_price - median_val) / mad_val
        elif std_val > 0.001:
            robust_z = 0.6745 * (current_price - median_val) / std_val
        else:
            robust_z = 0.0

        # 6. Posição Percentílica Empírica (0.0 a 100.0%)
        lower_or_equal_count = sum(1 for p in all_prices if p <= current_price)
        percentile_rank = (lower_or_equal_count / n) * 100.0

        # 7. Tendência Linear (OLS Slope - Mínimos Quadrados)
        trend_slope = 0.0
        if historical_dates and len(historical_dates) == n and n >= 2:
            base_t = historical_dates[0]
            t_days = [(d - base_t).total_seconds() / 86400.0 for d in historical_dates]
            t_mean = statistics.mean(t_days)
            denom = sum((t - t_mean) ** 2 for t in t_days)
            if denom > 1e-4:
                numer = sum((t - t_mean) * (p - mean_val) for t, p in zip(t_days, all_prices))
                trend_slope = numer / denom

        # 8. Classificação do Regime de Preço
        if robust_z <= -2.0 or (current_price < min_p and n >= 3):
            regime = "QUEDA_ANOMALA"
        elif robust_z <= -0.75:
            regime = "PRECO_FAVORAVEL"
        elif robust_z >= 1.5 and trend_slope > 0.5:
            regime = "SOBREPRECO_ESQUENTA"
        elif robust_z >= 1.5:
            regime = "SOBREPRECO"
        else:
            regime = "ESTAVEL"

        # 9. Cálculo do Deal Confidence Score (0 a 100 pontos)
        deal_score = self._compute_deal_score(
            current_price=current_price,
            target_price=target_price,
            user_max_price=user_max_price,
            robust_z=robust_z,
            percentile_rank=percentile_rank,
            is_fake_discount=is_fake_discount,
        )

        return PriceStatisticalProfile(
            sample_size=n,
            current_price=round(current_price, 2),
            min_price=round(min_p, 2),
            max_price=round(max_p, 2),
            mean=round(mean_val, 2),
            median=round(median_val, 2),
            std_dev=round(std_val, 2),
            mad=round(mad_val, 2),
            q1=round(q1_val, 2),
            q3=round(q3_val, 2),
            iqr=round(iqr_val, 2),
            cv_percent=round(cv_val, 2),
            z_score=round(z_score, 2),
            robust_z_score=round(robust_z, 2),
            percentile_rank=round(percentile_rank, 1),
            trend_slope_brl_per_day=round(trend_slope, 2),
            regime_preco=regime,
            deal_confidence_score=round(deal_score, 1),
        )

    @staticmethod
    def _compute_deal_score(
        current_price: float,
        target_price: float | None,
        user_max_price: float | None,
        robust_z: float,
        percentile_rank: float,
        is_fake_discount: bool,
    ) -> float:
        """Combina os sinais de Data Science em um índice de confiança único de 0 a 100."""
        # Componente 1: Proximidade ou desconto em relação ao preço-alvo (35 pts)
        if target_price and target_price > 0:
            if current_price <= target_price:
                # Bateu o alvo: nota máxima proporcional à economia adicional
                extra_saving = (target_price - current_price) / target_price
                c1 = min(35.0, 25.0 + (extra_saving * 50.0))
            else:
                dist = (current_price - target_price) / target_price
                c1 = max(0.0, 25.0 * (1.0 - dist * 3.0))
        else:
            c1 = 17.5

        # Componente 2: Z-Score Robusto (30 pts)
        # Z-Scores fortemente negativos ganham pontuação cheia
        if robust_z <= -2.5:
            c2 = 30.0
        elif robust_z <= 0.0:
            # Mapeia [-2.5, 0.0] para [30.0, 10.0]
            ratio = (-robust_z) / 2.5
            c2 = 10.0 + (ratio * 20.0)
        else:
            # Preço acima da mediana perde pontos
            c2 = max(0.0, 10.0 - (robust_z * 5.0))

        # Componente 3: Posição Percentílica Histórica (20 pts)
        # Percentil 0% = 20 pts; Percentil 100% = 0 pts
        c3 = 20.0 * (1.0 - (percentile_rank / 100.0))

        # Componente 4: Legitimidade da Promoção e Teto Máximo (15 pts)
        c4 = 15.0
        if is_fake_discount:
            c4 -= 10.0
        if user_max_price and current_price > user_max_price:
            c4 -= 5.0

        total = max(0.0, min(100.0, c1 + c2 + c3 + c4))
        return total
