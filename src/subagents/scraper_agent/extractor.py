"""Helper for extracting pricing data using learned selector overrides with CSS syntax and keyword guards."""

from __future__ import annotations

import soupsieve
from bs4 import BeautifulSoup
from loguru import logger

from src.core.domain import parse_brl_money
from src.core.models import Product, ScrapedData
from src.skills.normalize_product.normalizer import NormalizeProductSkill


def is_safe_css_selector(selector: str | None) -> bool:
    """Valida sintaxe CSS via soupsieve e rejeita construções perigosas ou excessivamente longas."""
    if not selector or not isinstance(selector, str):
        return False
    cleaned = selector.strip()
    if not cleaned or len(cleaned) > 200:
        return False
    forbidden_tokens = ("<", ">", "{", "}", ";", "javascript:", "@import", "expression(")
    if any(tok in cleaned.lower() for tok in forbidden_tokens):
        return False
    try:
        soupsieve.compile(cleaned)
        return True
    except Exception:  # noqa: BLE001
        return False


def extract_with_overrides(
    html: str,
    overrides: dict[str, str],
    url: str,
    marketplace: str,
    keywords: list[str] | None = None,
    product: Product | None = None,
) -> ScrapedData | None:
    """Extrai o melhor preço correspondente usando seletores aprendidos e validando relevância."""
    if not html or not overrides:
        return None

    title_sel = overrides.get("titulo")
    price_sel = overrides.get("preco")
    container_sel = overrides.get("container")

    if not (is_safe_css_selector(title_sel) and is_safe_css_selector(price_sel)):
        logger.warning(f"[Overrides] Seletores inválidos ignorados para [{marketplace.upper()}].")
        return None
    if container_sel and not is_safe_css_selector(container_sel):
        logger.warning(
            f"[Overrides] Seletor de container inválido ignorado para [{marketplace.upper()}]."
        )
        return None

    soup = BeautifulSoup(html, "html.parser")
    try:
        items = soup.select(container_sel) if container_sel else [soup]
    except Exception:  # noqa: BLE001
        return None

    effective_keywords = keywords if keywords is not None else (product.keywords if product else None)
    candidates: list[ScrapedData] = []

    for item in items:
        try:
            t_el = item.select_one(title_sel)  # type: ignore[arg-type]
            p_el = item.select_one(price_sel)  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[Overrides] Falha pontual de seletor em [{marketplace}]: {exc}")
            continue

        if not (t_el and p_el):
            continue

        title = t_el.get_text(strip=True)
        if not title:
            continue

        if effective_keywords and not NormalizeProductSkill.matches_keywords(
            title, effective_keywords
        ):
            continue

        price = parse_brl_money(p_el.get_text(strip=True))
        if price is None:
            continue

        if (
            product
            and product.preco_alvo > 0
            and product.preco_maximo > 0
            and not (product.preco_alvo * 0.30 <= price <= product.preco_maximo * 3.0)
        ):
            continue

        link_el = item.select_one("a[href]") if item is not soup else None
        item_url = str(link_el.get("href")) if link_el and link_el.get("href") else url

        candidates.append(
            ScrapedData(
                marketplace=marketplace,
                success=True,
                titulo=title,
                preco=price,
                url=item_url,
            )
        )

    if not candidates:
        return None

    candidates.sort(key=lambda c: c.preco or float("inf"))
    return candidates[0]
