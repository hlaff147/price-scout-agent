"""Evaluation and machine learning metrics for classification and regression."""

from __future__ import annotations

import math
from typing import Any, Sequence

from pydantic import BaseModel, Field


class BinaryClassificationMetrics(BaseModel):
    """Métricas consolidadas de classificação binária supervisionada."""

    total_samples: int
    tp: int = Field(description="Verdadeiros Positivos")
    fp: int = Field(description="Falsos Positivos")
    tn: int = Field(description="Verdadeiros Negativos")
    fn: int = Field(description="Falsos Negativos")

    accuracy: float = Field(description="Acurácia Global (TP+TN)/Total")
    precision: float = Field(description="Precisão TP/(TP+FP)")
    recall: float = Field(description="Revocação / Sensibilidade TP/(TP+FN)")
    specificity: float = Field(description="Especificidade TN/(TN+FP)")
    f1_score: float = Field(description="F1-Score balanceado (beta=1.0)")
    f05_score: float = Field(description="F0.5-Score focado em Precisão (beta=0.5)")
    f2_score: float = Field(description="F2-Score focado em Recall (beta=2.0)")
    mcc: float = Field(description="Matthews Correlation Coefficient (-1 a +1)")
    balanced_accuracy: float = Field(description="(Recall + Specificity) / 2")
    brier_score: float | None = Field(default=None, description="Brier Score de calibração de probabilidade")


class RegressionMetrics(BaseModel):
    """Métricas de avaliação de regressão e séries temporais de preço."""

    total_samples: int
    mae: float = Field(description="Mean Absolute Error")
    rmse: float = Field(description="Root Mean Squared Error")
    mape: float | None = Field(default=None, description="Mean Absolute Percentage Error (%)")
    max_error: float = Field(description="Maior erro absoluto pontual")


def compute_classification_metrics(
    y_true: Sequence[bool | int],
    y_pred: Sequence[bool | int],
    y_prob: Sequence[float] | None = None,
) -> BinaryClassificationMetrics:
    """Calcula todas as métricas padrão de classificação binária.

    Args:
        y_true: Valores reais de referência (ground truth: True/1 ou False/0).
        y_pred: Valores preditos pelo agente / modelo (True/1 ou False/0).
        y_prob: Opcional: probabilidades ou confiança estimada pelo agente (0.0 a 1.0).

    Returns:
        Instância tipada de BinaryClassificationMetrics.
    """
    if len(y_true) != len(y_pred):
        raise ValueError(f"Tamanhos divergentes: y_true={len(y_true)}, y_pred={len(y_pred)}")

    n = len(y_true)
    if n == 0:
        return BinaryClassificationMetrics(
            total_samples=0,
            tp=0,
            fp=0,
            tn=0,
            fn=0,
            accuracy=0.0,
            precision=0.0,
            recall=0.0,
            specificity=0.0,
            f1_score=0.0,
            f05_score=0.0,
            f2_score=0.0,
            mcc=0.0,
            balanced_accuracy=0.0,
            brier_score=None,
        )

    tp = 0
    fp = 0
    tn = 0
    fn = 0

    for yt, yp in zip(y_true, y_pred):
        yt_bool = bool(yt)
        yp_bool = bool(yp)
        if yt_bool and yp_bool:
            tp += 1
        elif not yt_bool and yp_bool:
            fp += 1
        elif not yt_bool and not yp_bool:
            tn += 1
        else:
            fn += 1

    accuracy = (tp + tn) / n if n > 0 else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0

    def f_beta(beta: float) -> float:
        beta_sq = beta**2
        denom = (beta_sq * precision) + recall
        if denom == 0:
            return 0.0
        return (1.0 + beta_sq) * (precision * recall) / denom

    f1 = f_beta(1.0)
    f05 = f_beta(0.5)
    f2 = f_beta(2.0)

    # Matthews Correlation Coefficient (MCC)
    mcc_denom = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    if mcc_denom > 0:
        mcc = ((tp * tn) - (fp * fn)) / mcc_denom
    else:
        mcc = 0.0

    balanced_acc = (recall + specificity) / 2.0

    # Brier Score (Erro Quadrático Médio das Probabilidades)
    brier: float | None = None
    if y_prob is not None and len(y_prob) == n:
        brier = sum((float(p) - (1.0 if yt else 0.0)) ** 2 for yt, p in zip(y_true, y_prob)) / n

    return BinaryClassificationMetrics(
        total_samples=n,
        tp=tp,
        fp=fp,
        tn=tn,
        fn=fn,
        accuracy=round(accuracy, 4),
        precision=round(precision, 4),
        recall=round(recall, 4),
        specificity=round(specificity, 4),
        f1_score=round(f1, 4),
        f05_score=round(f05, 4),
        f2_score=round(f2, 4),
        mcc=round(mcc, 4),
        balanced_accuracy=round(balanced_acc, 4),
        brier_score=round(brier, 4) if brier is not None else None,
    )


def confusion_matrix_dict(y_true: Sequence[bool | int], y_pred: Sequence[bool | int]) -> dict[str, Any]:
    """Retorna a matriz de confusão formatada em dicionário legível."""
    metrics = compute_classification_metrics(y_true, y_pred)
    return {
        "matrix": [
            [metrics.tn, metrics.fp],
            [metrics.fn, metrics.tp],
        ],
        "labels": ["Negativo (Rejeitado)", "Positivo (Compatível)"],
        "tp": metrics.tp,
        "fp": metrics.fp,
        "tn": metrics.tn,
        "fn": metrics.fn,
    }


def threshold_tuning_curve(
    y_true: Sequence[bool | int],
    y_scores: Sequence[float],
    metric: str = "f05",
    steps: int = 40,
) -> dict[str, Any]:
    """Varre limiares de decisão de 0.0 a 1.0 para calibrar o ponto de corte ótimo.

    Args:
        y_true: Rótulos reais de referência.
        y_scores: Scores de confiança contínuos produzidos pelo agente (ex: overlap_ratio).
        metric: Métrica a maximizar ('f05', 'f1', 'precision', 'mcc', 'accuracy').
        steps: Número de pontos de discretização.

    Returns:
        Dicionário com o limiar ótimo ('best_threshold'), o valor da métrica ('best_score')
        e a curva completa com os pontos testados.
    """
    if not y_true or not y_scores or len(y_true) != len(y_scores):
        return {"best_threshold": 0.5, "best_score": 0.0, "curve": []}

    curve = []
    best_th = 0.5
    best_score = -1.0

    for i in range(steps + 1):
        th = round(i / steps, 3)
        y_pred = [1 if s >= th else 0 for s in y_scores]
        m = compute_classification_metrics(y_true, y_pred, y_prob=y_scores)

        score_val = getattr(m, f"{metric}_score" if hasattr(m, f"{metric}_score") else metric, m.f05_score)
        curve.append({
            "threshold": th,
            "score": score_val,
            "precision": m.precision,
            "recall": m.recall,
            "f1": m.f1_score,
            "f05": m.f05_score,
            "mcc": m.mcc,
        })

        if score_val > best_score:
            best_score = score_val
            best_th = th

    return {
        "best_threshold": best_th,
        "best_score": round(best_score, 4),
        "target_metric": metric,
        "curve": curve,
    }
