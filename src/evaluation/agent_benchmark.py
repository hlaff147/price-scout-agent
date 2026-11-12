"""Runner and reporter for the agents benchmark suite."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from src.data.database import Database
from src.data.models import PriceRecord, Product, ScrapedData, Source
from src.data.repository import Repository
from src.evaluation.ml_metrics import (
    BinaryClassificationMetrics,
    compute_classification_metrics,
)
from src.skills.detect_fake_discount.detector import DetectFakeDiscountSkill
from src.subagents.matcher.hybrid_matcher import HybridProductMatcher
from src.subagents.price_analyst_agent.agent import PriceAnalystSubagent


class AgentBenchmarkRunner:
    """Executa a bateria de avaliação de Machine Learning contra o Golden Dataset."""

    def __init__(self, benchmark_yaml_path: str | Path = "data/benchmarks/agents_ground_truth.yaml"):
        self.benchmark_path = Path(benchmark_yaml_path)
        if not self.benchmark_path.exists():
            raise FileNotFoundError(f"Dataset de benchmark não encontrado: {self.benchmark_path}")
        with open(self.benchmark_path, "r", encoding="utf-8") as f:
            self.data = yaml.safe_load(f) or {}

    async def evaluate_matcher(self) -> dict[str, Any]:
        """Avalia o HybridProductMatcher globalmente e por categoria vertical."""
        matcher = HybridProductMatcher()
        cases = self.data.get("matcher_cases", [])

        y_true_all: list[int] = []
        y_pred_all: list[int] = []
        y_prob_all: list[float] = []

        by_cat: dict[str, dict[str, list[Any]]] = {}

        for item in cases:
            cat = item.get("category", "outros")
            if cat not in by_cat:
                by_cat[cat] = {"true": [], "pred": [], "prob": []}

            product = Product(
                id=item["target_id"],
                nome=item["target_name"],
                keywords=item.get("target_keywords", []),
                preco_alvo=1000.0,
                preco_maximo=1500.0,
            )

            res = await matcher.match(
                target=product,
                candidate_title=item["candidate_title"],
            )

            yt = 1 if item["expected_match"] else 0
            yp = 1 if res.is_match else 0
            prob = res.confidence if res.is_match else (1.0 - res.confidence)

            y_true_all.append(yt)
            y_pred_all.append(yp)
            y_prob_all.append(prob)

            by_cat[cat]["true"].append(yt)
            by_cat[cat]["pred"].append(yp)
            by_cat[cat]["prob"].append(prob)

        global_metrics = compute_classification_metrics(y_true_all, y_pred_all, y_prob_all)

        category_metrics: dict[str, BinaryClassificationMetrics] = {}
        for cat, values in by_cat.items():
            category_metrics[cat] = compute_classification_metrics(
                values["true"], values["pred"], values["prob"]
            )

        return {
            "global": global_metrics,
            "by_category": category_metrics,
            "total_cases": len(cases),
        }

    def evaluate_fake_discount(self) -> dict[str, Any]:
        """Avalia o DetectFakeDiscountSkill."""
        skill = DetectFakeDiscountSkill()
        cases = self.data.get("fake_discount_cases", [])

        y_true: list[int] = []
        y_pred: list[int] = []

        for item in cases:
            _, _, is_fake = skill.execute(
                current_price=float(item["current_price"]),
                original_price_announced=float(item["original_price_announced"]) if item.get("original_price_announced") else None,
                historical_avg=float(item["historical_avg"]) if item.get("historical_avg") else None,
                user_max_price=float(item["user_max_price"]) if item.get("user_max_price") else None,
            )
            y_true.append(1 if item["expected_is_fake"] else 0)
            y_pred.append(1 if is_fake else 0)

        metrics = compute_classification_metrics(y_true, y_pred)
        return {
            "metrics": metrics,
            "total_cases": len(cases),
        }

    async def evaluate_price_analyst(self) -> dict[str, Any]:
        """Avalia o PriceAnalystSubagent em cenários controlados em memória."""
        cases = self.data.get("deal_cases", [])
        y_true: list[int] = []
        y_pred: list[int] = []

        for item in cases:
            db = Database(":memory:")
            repo = Repository(db)

            product = Product(
                id=item["product_id"],
                nome=f"Produto {item['product_id']}",
                keywords=[f"Produto {item['product_id']}", item["product_id"]],
                preco_alvo=float(item["target_price"]),
                preco_maximo=float(item["max_price"]),
            )
            repo.upsert_product(product)
            source = repo.upsert_source(
                Source(product_id=product.id, marketplace="mercadolivre", url_produto="http://ml.com")
            )

            for hp in item.get("historical_prices", []):
                repo.save_price_record(PriceRecord(source_id=source.id, preco=float(hp)))

            analyst = PriceAnalystSubagent(repository=repo)
            scraped = ScrapedData(
                marketplace="mercadolivre",
                success=True,
                preco=float(item["scraped_price"]),
                titulo=product.nome,
                url="http://ml.com/oferta",
            )
            analyses = await analyst.run(product, [(source, scraped)])

            yt = 1 if item["expected_is_deal"] else 0
            yp = 1 if (analyses and analyses[0].is_deal) else 0

            y_true.append(yt)
            y_pred.append(yp)

        metrics = compute_classification_metrics(y_true, y_pred)
        return {
            "metrics": metrics,
            "total_cases": len(cases),
        }

    async def run_full_suite(self) -> dict[str, Any]:
        """Executa toda a suíte de avaliação dos agentes."""
        matcher_res = await self.evaluate_matcher()
        fake_disc_res = self.evaluate_fake_discount()
        analyst_res = await self.evaluate_price_analyst()

        return {
            "matcher": matcher_res,
            "fake_discount": fake_disc_res,
            "analyst": analyst_res,
        }

    def generate_markdown_report(self, results: dict[str, Any]) -> str:
        """Gera um relatório completo e elegante em Markdown com todas as métricas."""
        m_glob: BinaryClassificationMetrics = results["matcher"]["global"]
        fd_m: BinaryClassificationMetrics = results["fake_discount"]["metrics"]
        an_m: BinaryClassificationMetrics = results["analyst"]["metrics"]

        md = []
        md.append("# Relatório Executivo de Avaliação de Machine Learning & Data Science — PromoRadar\n")
        md.append("> Avaliação automatizada de acurácia, precisão, revocação, F1-score e calibração estatística dos agentes contra o Golden Dataset Multi-Vertical.\n")

        md.append("## 1. Desempenho Global dos Agentes\n")
        md.append("| Agente / Componente | Casos | Accuracy | Precision | Recall | $F_1$-Score | $F_{0.5}$-Score | MCC | Brier Score |")
        md.append("|---|---|---|---|---|---|---|---|---|")
        md.append(
            f"| **HybridProductMatcher** | {results['matcher']['total_cases']} | "
            f"`{m_glob.accuracy:.1%}` | `{m_glob.precision:.1%}` | `{m_glob.recall:.1%}` | "
            f"`{m_glob.f1_score:.3f}` | `{m_glob.f05_score:.3f}` | `{m_glob.mcc:.3f}` | `{m_glob.brier_score or 0.0:.3f}` |"
        )
        md.append(
            f"| **DetectFakeDiscountSkill** | {results['fake_discount']['total_cases']} | "
            f"`{fd_m.accuracy:.1%}` | `{fd_m.precision:.1%}` | `{fd_m.recall:.1%}` | "
            f"`{fd_m.f1_score:.3f}` | `{fd_m.f05_score:.3f}` | `{fd_m.mcc:.3f}` | — |"
        )
        md.append(
            f"| **PriceAnalystSubagent** | {results['analyst']['total_cases']} | "
            f"`{an_m.accuracy:.1%}` | `{an_m.precision:.1%}` | `{an_m.recall:.1%}` | "
            f"`{an_m.f1_score:.3f}` | `{an_m.f05_score:.3f}` | `{an_m.mcc:.3f}` | — |\n"
        )

        md.append("## 2. Detalhamento do HybridProductMatcher por Vertical\n")
        md.append("| Categoria Vertical | Casos | TP | FP | TN | FN | Precision | Recall | $F_{0.5}$-Score | MCC |")
        md.append("|---|---|---|---|---|---|---|---|---|---|")
        for cat, cm in results["matcher"]["by_category"].items():
            label = {
                "smartphones_512": "Smartphones 512GB (R$ 3.000)",
                "smartwatches": "Smartwatches (R$ 800 - R$ 1.200)",
                "monitores_27": "Monitores 27 Ergonômicos",
            }.get(cat, cat.upper())
            md.append(
                f"| **{label}** | {cm.total_samples} | {cm.tp} | {cm.fp} | {cm.tn} | {cm.fn} | "
                f"`{cm.precision:.1%}` | `{cm.recall:.1%}` | `{cm.f05_score:.3f}` | `{cm.mcc:.3f}` |"
            )
        md.append("\n")

        md.append("## 3. Matrizes de Confusão\n")
        md.append("### HybridProductMatcher (Global)")
        md.append("```")
        md.append(f"Verdadeiros Negativos (Rejeições de Acessórios/Erros): {m_glob.tn} | Falsos Positivos (Vazamentos): {m_glob.fp}")
        md.append(f"Falsos Negativos (Descartes Indevidos):               {m_glob.fn} | Verdadeiros Positivos (Corretos):     {m_glob.tp}")
        md.append("```\n")

        md.append("### DetectFakeDiscountSkill")
        md.append("```")
        md.append(f"TN: {fd_m.tn} | FP: {fd_m.fp}")
        md.append(f"FN: {fd_m.fn} | TP: {fd_m.tp}")
        md.append("```\n")

        md.append("## 4. Conclusão Técnica e Calibração dos Modelos\n")
        if m_glob.precision >= 0.95 and m_glob.f05_score >= 0.90:
            md.append(
                "- ✅ **Alta Precisão do Matcher**: A métrica $F_{0.5}$ está acima da meta de 0.90, "
                "garantindo que o SQLite permaneça livre de acessórios (pulseiras, docks, capas) e variantes incorretas (256GB).\n"
            )
        if fd_m.accuracy >= 0.90:
            md.append(
                "- ✅ **Detecção Robusta de Fraude Promocional**: O classificador de falso desconto "
                "identificou corretamente as maquiagens de preço de Black Friday sem penalizar promoções reais.\n"
            )
        if an_m.recall >= 0.90:
            md.append(
                "- ✅ **Analista de Oportunidades**: O detector de anomalias temporais via Z-Score Robusto "
                "capturou quedas expressivas e respeitou a linha de base histórica.\n"
            )

        return "\n".join(md)
