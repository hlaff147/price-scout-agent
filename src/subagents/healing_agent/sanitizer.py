"""HTML DOM sanitizer stripping unnecessary tags and attributes for LLM inspection."""

import re

from bs4 import BeautifulSoup, Comment


def sanitize_html_for_llm(html: str, max_chars: int = 40000) -> str:
    """Sanitiza o HTML removendo ruídos (scripts, estilos, svgs, imagens, comentários) para análise enxuta por LLM.

    Args:
        html: Código HTML bruto capturado da página.
        max_chars: Limite de caracteres para contenção de tokens.

    Returns:
        HTML simplificado e compactado mantendo a estrutura semântica essencial.
    """
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")

    # Remove elementos sem relevância para extração de dados
    for tag in soup(["script", "style", "noscript", "svg", "path", "link", "iframe", "canvas", "picture"]):
        tag.decompose()

    # Remove comentários HTML
    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()

    # Remove atributos desnecessários ou gigantes (data: base64, styles inline, eventos on*)
    for el in soup.find_all(True):
        attrs_to_remove = []
        for attr, val in list(el.attrs.items()):
            if attr in ("style", "onclick", "onload", "onerror") or attr.startswith("aria-") or isinstance(val, str) and (val.startswith("data:image") or len(val) > 200):
                attrs_to_remove.append(attr)
        for attr in attrs_to_remove:
            del el[attr]

    # Busca focar no container principal caso exista
    target_node = (
        soup.find("main")
        or soup.find("div", {"id": re.compile(r"root|app|search|results", re.IGNORECASE)})
        or soup.find("ol", class_=re.compile(r"search|results", re.IGNORECASE))
        or soup.body
        or soup
    )

    clean_str = str(target_node)
    # Remove múltiplos espaços em branco e quebras redundantes
    clean_str = re.sub(r"\n\s*\n", "\n", clean_str)
    clean_str = re.sub(r"[ \t]+", " ", clean_str)

    if len(clean_str) > max_chars:
        clean_str = clean_str[:max_chars] + "\n<!-- [HTML truncado pelo sanitizer para contenção de tokens] -->"

    return clean_str
