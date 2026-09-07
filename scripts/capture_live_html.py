#!/usr/bin/env python3
"""Script utilitário para capturar o HTML retornado em tempo real pelo HttpClient.

Salva as respostas em tests/fixtures/live/ para análise detalhada e criação de fixtures de teste realistas.
"""

import asyncio
import os
import sys
from pathlib import Path

# Garante a execução dentro do .venv caso o usuário execute com o python3 global
venv_python = Path(__file__).resolve().parent.parent / ".venv" / "bin" / "python"
if venv_python.exists() and sys.executable != str(venv_python):
    os.execv(str(venv_python), [str(venv_python)] + sys.argv)

import yaml
from loguru import logger

from src.tools.http_client import http_client

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "live"


async def capture_source(marketplace: str, url: str) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_file = OUTPUT_DIR / f"{marketplace}_search_live.html"
    logger.info(f"Capturando HTML de [{marketplace.upper()}] a partir de: {url}")
    try:
        html = await http_client.fetch(url)
        out_file.write_text(html, encoding="utf-8")
        logger.success(
            f"[{marketplace.upper()}] Salvo com sucesso em {out_file} ({len(html)} bytes, {len(html.splitlines())} linhas)"
        )
    except Exception as exc:
        logger.error(f"[{marketplace.upper()}] Falha na captura de {url}: {exc}")


async def main():
    config_path = Path(__file__).resolve().parent.parent / "src" / "config" / "products.yaml"
    if not config_path.exists():
        logger.error(f"Configuração {config_path} não encontrada.")
        return

    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    tasks = []
    for product in data.get("products", []):
        for source in product.get("sources", []):
            if source.get("ativo", True):
                tasks.append(capture_source(source["marketplace"], source["url_produto"]))

    logger.info(f"Iniciando captura de {len(tasks)} fontes ativas...")
    await asyncio.gather(*tasks, return_exceptions=True)
    logger.info(f"Captura concluída. Verifique os arquivos em: {OUTPUT_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
