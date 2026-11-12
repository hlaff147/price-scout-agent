"""Unit tests and automated quality gates for Machine Learning and Data Science metrics."""

import math
from datetime import datetime, timedelta, timezone

import pytest

from src.evaluation.agent_benchmark import AgentBenchmarkRunner
from src.evaluation.ml_metrics import (
    compute_classification_metrics,
    confusion_matrix_dict,
    threshold_tuning_curve,
)
from src.skills.price_statistics.analyzer import (
    PriceStatisticalProfile,
    PriceStatisticsSkill,
)


class TestBinaryClassificationMetrics:
    def test_exact_analytical_metrics(self):
        # 4 amostras: TP=1, FP=1, FN=1, TN=1
        y_true = [1, 0, 1, 0]
        y_pred = [1, 1, 0, 0]
        probs = [0.9, 0.8, 0.2, 0.1]

        m = compute_classification_metrics(y_true, y_pred, y_prob=probs)

        assert m.total_samples == 4
        assert m.tp == 1
        assert m.fp == 1
        assert m.fn == 1
        assert m.tn == 1

        assert m.accuracy == 0.50
        assert m.precision == 0.50
        assert m.recall == 0.50
        assert m.specificity == 0.50
        assert m.f1_score == 0.50
        assert m.f05_score == 0.50
        assert m.f2_score == 0.50
        assert m.mcc == 0.0

        # Brier Score esperado:
        # i=0: (0.9 - 1)^2 = 0.01
        # i=1: (0.8 - 0)^2 = 0.64
        # i=2: (0.2 - 1)^2 = 0.64
        # i=3: (0.1 - 0)^2 = 0.01
        # Média = (0.01 + 0.64 + 0.64 + 0.01) / 4 = 1.30 / 4 = 0.325
        assert m.brier_score == 0.325

    def test_perfect_classification(self):
        y_true = [1, 1, 0, 0]
        y_pred = [1, 1, 0, 0]
        probs = [1.0, 1.0, 0.0, 0.0]

        m = compute_classification_metrics(y_true, y_pred, y_prob=probs)

        assert m.accuracy == 1.0
        assert m.precision == 1.0
        assert m.recall == 1.0
        assert m.f1_score == 1.0
        assert m.f05_score == 1.0
        assert m.mcc == 1.0
        assert m.brier_score == 0.0

    def test_empty_input_graceful_handling(self):
        m = compute_classification_metrics([], [])
        assert m.total_samples == 0
        assert m.accuracy == 0.0
        assert m.precision == 0.0
        assert m.recall == 0.0

    def test_confusion_matrix_dict(self):
        y_true = [1, 0, 1]
        y_pred = [1, 0, 0]
        cm = confusion_matrix_dict(y_true, y_pred)
        assert cm["tp"] == 1
        assert cm["tn"] == 1
        assert cm["fn"] == 1
        assert cm["fp"] == 0

    def test_threshold_tuning(self):
        y_true = [1, 1, 0, 0]
        y_scores = [0.85, 0.65, 0.45, 0.15]
        tuning = threshold_tuning_curve(y_true, y_scores, metric="f05", steps=10)
        assert "best_threshold" in tuning
        assert tuning["best_score"] == 1.0
        assert 0.45 <= tuning["best_threshold"] <= 0.65


class TestPriceStatisticsSkill:
    def test_single_or_empty_price_history(self):
        skill = PriceStatisticsSkill()
        profile = skill.execute(historical_prices=[], current_price=1000.0)
        assert profile.sample_size == 1
        assert profile.mean == 1000.0
        assert profile.median == 1000.0
        assert profile.mad == 0.0
        assert profile.robust_z_score == 0.0
        assert profile.regime_preco == "NOVO_SEM_HISTORICO"

    def test_robust_z_score_detects_abrupt_price_drop(self):
        skill = PriceStatisticsSkill()
        # Série estável em torno de R$ 1.000 com leve ruído
        history = [1000.0, 1005.0, 995.0, 1002.0, 998.0, 1000.0, 1003.0, 997.0]
        # Queda abrupta para R$ 850 (15% abaixo)
        profile = skill.execute(
            historical_prices=history,
            current_price=850.0,
            target_price=900.0,
            user_max_price=1100.0,
        )

        assert profile.median == 1000.0
        assert profile.mad > 0
        # Z-Score robusto deve ser fortemente negativo
        assert profile.robust_z_score < -2.0
        assert profile.percentile_rank == 0.0
        assert profile.regime_preco == "QUEDA_ANOMALA"
        # Deal score deve ser alto
        assert profile.deal_confidence_score >= 80.0

    def test_trend_slope_calculation(self):
        skill = PriceStatisticsSkill()
        base_time = datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc)
        # Preço subindo R$ 10 a cada dia (inflação prévia)
        history = [1000.0, 1010.0, 1020.0, 1030.0]
        dates = [base_time + timedelta(days=i) for i in range(4)]

        profile = skill.execute(
            historical_prices=history,
            current_price=1040.0,
            historical_dates=dates,
        )

        assert math.isclose(profile.trend_slope_brl_per_day, 10.0, rel_tol=0.05)
        assert profile.robust_z_score > 1.0


class TestMLQualityGates:
    """Quality gates automatizados assegurando que os agentes atendam aos patamares mínimos de ML."""

    @pytest.mark.asyncio
    async def test_matcher_quality_gate_precision_and_f05(self):
        runner = AgentBenchmarkRunner()
        results = await runner.evaluate_matcher()
        m = results["global"]

        # Quality Gate 1: Precision >= 95% para não poluir banco com acessórios/variantes
        assert m.precision >= 0.95, f"Precision do Matcher caiu para {m.precision:.2%}"

        # Quality Gate 2: F0.5 >= 0.90
        assert m.f05_score >= 0.90, f"F0.5 do Matcher caiu para {m.f05_score:.3f}"

        # Quality Gate 3: Recall >= 90% para não perder promoções reais
        assert m.recall >= 0.90, f"Recall do Matcher caiu para {m.recall:.2%}"

        # Quality Gate 4: MCC >= 0.85
        assert m.mcc >= 0.85, f"MCC do Matcher caiu para {m.mcc:.3f}"

    def test_fake_discount_quality_gate(self):
        runner = AgentBenchmarkRunner()
        results = runner.evaluate_fake_discount()
        m = results["metrics"]

        assert m.accuracy >= 0.90, f"Acurácia do DetectFakeDiscount caiu para {m.accuracy:.2%}"
        assert m.f1_score >= 0.90, f"F1 do DetectFakeDiscount caiu para {m.f1_score:.3f}"

    @pytest.mark.asyncio
    async def test_price_analyst_quality_gate(self):
        runner = AgentBenchmarkRunner()
        results = await runner.evaluate_price_analyst()
        m = results["metrics"]

        assert m.accuracy >= 0.90, f"Acurácia do PriceAnalyst caiu para {m.accuracy:.2%}"
        assert m.recall >= 0.90, f"Recall do PriceAnalyst caiu para {m.recall:.2%}"
