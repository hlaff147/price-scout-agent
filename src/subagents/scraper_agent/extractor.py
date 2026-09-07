"""Helper for extracting pricing data using learned selector overrides."""

import re

from bs4 import BeautifulSoup

from src.data.models import ScrapedData


def extract_with_overrides(
    html: str,
    overrides: dict[str, str],
    url: str,
    marketplace: str,
) -> ScrapedData | None:
    """Tenta extrair título e preço usando seletores customizados/reparados."""
    if not html or not overrides:
        return None

    title_sel = overrides.get("titulo")
    price_sel = overrides.get("preco")
    container_sel = overrides.get("container")

    if not (title_sel and price_sel):
        return None

    soup = BeautifulSoup(html, "html.parser")
    items = soup.select(container_sel) if container_sel else [soup]

    for item in items:
        t_el = item.select_one(title_sel)
        p_el = item.select_one(price_sel)

        if not (t_el and p_el):
            continue

        title = t_el.get_text(strip=True)
        raw_price = p_el.get_text(strip=True)

        num_clean = re.sub(r"[^\d,.]", "", raw_price)
        if not num_clean:
            continue

        try:
            if "," in num_clean and "." in num_clean:
                num_clean = num_clean.replace(".", "").replace(",", ".")
            elif "," in num_clean:
                num_clean = num_clean.replace(",", ".")
            price = float(num_clean)

            return ScrapedData(
                marketplace=marketplace,
                success=True,
                titulo=title,
                preco=price,
                url=url,
            )
        except ValueError:
            continue

    return None
