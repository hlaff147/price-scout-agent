#!/usr/bin/env python3
"""CLI para avaliação contínua de Machine Learning e Data Science dos agentes do PromoRadar."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Garante execução no .venv do projeto
venv_python = PROJECT_ROOT / ".venv" / "bin" / "python"
if venv_python.exists() and Path(sys.executable).resolve() != venv_python.resolve():
    os.execv(str(venv_python), [str(venv_python)] + sys.argv)

os.chdir(PROJECT_ROOT)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.agent_benchmark import AgentBenchmarkRunner


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Avaliação de Machine Learning, Precisão, Recall e F1-Score dos Agentes do PromoRadar"
    )
    parser.add_argument(
        "--benchmark",
        type=str,
        default="data/benchmarks/agents_ground_truth.yaml",
        help="Caminho para o Golden Dataset em YAML.",
    )
    parser.add_argument(
        "--markdown",
        type=str,
        default="reports/ml_agents_evaluation.md",
        help="Caminho para salvar o relatório consolidado em Markdown.",
    )
    parser.add_argument(
        "--json",
        type=str,
        default=None,
        help="Caminho opcional para exportar as métricas brutas em JSON.",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Não imprime o resumo no terminal.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    runner = AgentBenchmarkRunner(benchmark_yaml_path=args.benchmark)

    if not args.quiet:
        print("🔍 Executando benchmark de Machine Learning para os agentes do PromoRadar...")

    results = await runner.run_full_suite()
    md_content = runner.generate_markdown_report(results)

    # Salvar Markdown
    if args.markdown:
        out_md = Path(args.markdown)
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text(md_content, encoding="utf-8")
        if not args.quiet:
            print(f"📄 Relatório Markdown gerado em: {out_md}")

    # Salvar JSON se solicitado
    if args.json:
        out_json = Path(args.json)
        out_json.parent.mkdir(parents=True, exist_ok=True)
        # Serializar modelos Pydantic
        clean_dict = {
            k: {
                sub_k: (sub_v.model_dump() if hasattr(sub_v, "model_dump") else sub_v)
                for sub_k, sub_v in v.items()
            }
            if isinstance(v, dict)
            else v
            for k, v in results.items()
        }
        out_json.write_text(json.dumps(clean_dict, indent=2, ensure_ascii=False), encoding="utf-8")
        if not args.quiet:
            print(f"📊 Métricas brutas JSON exportadas em: {out_json}")

    # Exibição no console
    if not args.quiet:
        m_glob = results["matcher"]["global"]
        fd_m = results["fake_discount"]["metrics"]
        an_m = results["analyst"]["metrics"]
        print("\n" + "=" * 65)
        print("🏆 SCORECARD DOS AGENTES (ML & DATA SCIENCE)")
        print("=" * 65)
        print(f"🤖 HybridProductMatcher  | Acc: {m_glob.accuracy:.1%} | Prec: {m_glob.precision:.1%} | Rec: {m_glob.recall:.1%} | F0.5: {m_glob.f05_score:.3f} | MCC: {m_glob.mcc:.3f}")
        print(f"🕵️ DetectFakeDiscount    | Acc: {fd_m.accuracy:.1%} | Prec: {fd_m.precision:.1%} | Rec: {fd_m.recall:.1%} | F1:   {fd_m.f1_score:.3f} | MCC: {fd_m.mcc:.3f}")
        print(f"📈 PriceAnalystSubagent  | Acc: {an_m.accuracy:.1%} | Prec: {an_m.precision:.1%} | Rec: {an_m.recall:.1%} | F1:   {an_m.f1_score:.3f} | MCC: {an_m.mcc:.3f}")
        print("=" * 65 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
