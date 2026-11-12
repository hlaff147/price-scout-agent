"""Módulo de avaliação, métricas de Machine Learning e benchmarks dos agentes do PromoRadar."""

from src.evaluation.ml_metrics import (
    BinaryClassificationMetrics,
    RegressionMetrics,
    compute_classification_metrics,
    confusion_matrix_dict,
    threshold_tuning_curve,
)

__all__ = [
    "BinaryClassificationMetrics",
    "RegressionMetrics",
    "compute_classification_metrics",
    "confusion_matrix_dict",
    "threshold_tuning_curve",
]
