"""ADK Tools for scraping and HTML extraction."""

from src.subagents.scraper_agent.agent import ScraperSubagent
from src.tools.http_client import http_client

_PARSERS: dict[str, object] = {
    mkt: skill_cls() for mkt, skill_cls in ScraperSubagent.SKILL_REGISTRY.items()
}


async def fetch_page_content(url: str) -> str:
    """Faz download do conteúdo HTML de uma página web com proteção anti-bloqueio.

    Args:
        url: URL completa da página a ser baixada.

    Returns:
        O conteúdo HTML bruto da página.
    """
    return await http_client.fetch(url)


def parse_marketplace_html(
    html: str,
    marketplace: str,
    url: str,
    keywords: list[str] | None = None,
) -> dict:
    """Extrai informações estruturadas de preço, título e disponibilidade do HTML de um marketplace.

    Args:
        html: Conteúdo HTML da página de produto ou busca.
        marketplace: Nome do marketplace ('amazon', 'mercadolivre', 'shopee', etc.).
        url: URL original da consulta.
        keywords: Palavras-chave para filtro de relevância.

    Returns:
        Dicionário com os dados extraídos (success, preco, preco_original, titulo, disponivel, etc.).
    """
    parser = _PARSERS.get(marketplace.lower())
    if not parser:
        return {
            "marketplace": marketplace,
            "success": False,
            "url": url,
            "error_message": f"Nenhum parser configurado para '{marketplace}'.",
        }

    scraped = parser.execute(html=html, url=url, keywords=keywords)
    return scraped.model_dump()
