"""Canonical domain primitives for BRL currency, storage capacities, accessories, and security boundaries."""

from __future__ import annotations

import html
import ipaddress
import json
import math
import re
import unicodedata
from urllib.parse import urlparse

STORAGE_EXPLICIT_RE = re.compile(r"\b(\d+)\s*(gb|tb)\b", re.IGNORECASE)
STORAGE_COMPACT_RE = re.compile(
    r"\b(?:4|6|8|12|16|24)\s*/\s*(64|128|256|512|1024)\b",
    re.IGNORECASE,
)
STORAGE_TOKEN_RE = re.compile(r"^\d+(?:gb|tb)$")

REFURBISHED_TERMS: frozenset[str] = frozenset({
    "recondicionado",
    "recondicionada",
    "seminovo",
    "seminova",
    "usado",
    "usada",
    "vitrine",
    "refurbished",
    "reembalado",
    "reembalada",
    "mostruario",
})

STRICT_SPARE_PART_WORDS: frozenset[str] = frozenset({
    "capinha",
    "capinhas",
    "pelicula",
    "peliculas",
    "ponteira",
    "ponteiras",
    "pulseira",
    "pulseiras",
    "bracelete",
    "braceletes",
    "strap",
    "straps",
    "bezel",
    "parafuso",
    "parafusos",
})

DEVICE_HEAD_PREFIXES: tuple[str, ...] = (
    "smartphone ",
    "celular ",
    "iphone ",
    "monitor ",
    "smartwatch ",
    "relogio ",
    "tablet ",
    "fone ",
    "smart tv ",
    "tv ",
    "leitor ",
    "novo kindle ",
    "kindle ",
)

ACCESSORY_HEAD_PREFIXES: tuple[str, ...] = (
    "capa ",
    "capas ",
    "capinha ",
    "case ",
    "cases ",
    "pelicula ",
    "kit capa",
    "kit pelicula",
    "kit 2 peliculas",
    "kit 3 peliculas",
    "kit parafuso",
    "protetor ",
    "cabo ",
    "cabos ",
    "fonte ",
    "carregador ",
    "suporte ",
    "suportes ",
    "adaptador ",
    "tela ",
    "display ",
    "bateria ",
    "tampa ",
    "lente ",
    "placa ",
    "pedestal ",
    "pulseira ",
    "bracelete ",
    "strap ",
    "dock ",
    "base ",
)

ACCESSORY_COMPATIBILITY_PHRASES: tuple[str, ...] = (
    "capa para ",
    "capa case ",
    "capinha para ",
    "case para ",
    "pelicula para ",
    "pelicula de vidro",
    "protetor para ",
    "fonte para ",
    "fonte carregador",
    "carregador para ",
    "cabo carregador",
    "cabo displayport",
    "cabo hdmi",
    "cabo usb",
    "cabo para ",
    "dock de carregamento",
    "dock base",
    "base de carregador",
    "pulseira para ",
    "pulseira compativel",
    "pulseira milanese",
    "bracelete para ",
    "bracelete compativel",
    "suporte para ",
    "suporte articulado de mesa pistao a gas para monitor",
    "adaptador para ",
    "placa principal",
    "base pedestal",
    "tela reposicao",
    "display reposicao",
    "kit parafusos",
)

ELECTRONIC_DEVICE_MARKERS: frozenset[str] = frozenset({
    "monitor",
    "qhd",
    "fhd",
    "uhd",
    "4k",
    "ips",
    "oled",
    "hz",
    "144hz",
    "180hz",
    "240hz",
    "smartphone",
    "celular",
    "5g",
    "gb",
    "tb",
    "smartwatch",
    "relogio",
    "garmin",
    "forerunner",
    "amazfit",
    "watch",
    "kindle",
    "freebuds",
    "fone",
    "tv",
    "dell",
    "aoc",
    "asus",
    "lg",
    "samsung",
    "motorola",
    "xiaomi",
    "poco",
    "redmi",
    "realme",
})

COLOR_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Preto", ("preto", "preta", "black", "grafite", "graphite")),
    ("Branco", ("branco", "branca", "white")),
    ("Cinza", ("cinza", "gray", "grey")),
    ("Azul", ("azul", "blue")),
    ("Verde", ("verde", "green")),
    ("Prata", ("prata", "silver")),
    ("Dourado", ("dourado", "gold")),
    ("Rosa", ("rosa", "pink")),
)

TELEGRAM_TOKEN_URL_RE = re.compile(r"(https?://api\.telegram\.org/bot)([^/\s]+)")


def normalize_text(text: str, *, keep_hyphen: bool = False) -> str:
    """Remove acentos, converte para minúsculas e colapsa espaços."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_only = "".join(c for c in nfkd if not unicodedata.combining(c))
    pattern = r"[^\w\s-]" if keep_hyphen else r"[^\w\s]"
    cleaned = re.sub(pattern, " ", ascii_only.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def match_view(text: str) -> str:
    """Normaliza símbolos semânticos de catálogo ('S25+' -> 's25 plus', '512 GB' -> '512gb')."""
    if not text:
        return ""
    expanded = re.sub(r"(?<=\w)\+", " plus ", text)
    return STORAGE_EXPLICIT_RE.sub(lambda m: f"{m.group(1)}{m.group(2).lower()}", normalize_text(expanded))


def parse_brl_money(raw: str | float | None) -> float | None:
    """Converte representações monetárias BRL/US em float positivo exato (> 0).

    Invariante INV-01:
    - 'R$ 2.499' -> 2499.0 (milhar inteiro sem centavos JAMAIS trunca para 2.49)
    - 'R$ 1.299,90' -> 1299.90
    - '1,450.00' -> 1450.0
    - '1,450' -> 1450.0
    - '849,99' -> 849.99
    - '849.99' -> 849.99
    """
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        val = float(raw)
        return round(val, 2) if math.isfinite(val) and val > 0 else None

    cleaned = str(raw).replace("R$", "").replace("BRL", "").replace("\xa0", " ").strip()
    if not cleaned:
        return None
    if re.match(r"^-\s*\d", cleaned):
        return None

    token_match = re.search(r"\d+(?:[.,]\d+)*", cleaned)
    if not token_match:
        return None

    token = token_match.group(0)

    if "," in token and "." in token:
        if token.rfind(",") > token.rfind("."):
            # Formato brasileiro: 1.234,56 ou 12.345.678,90
            normalized = token.replace(".", "").replace(",", ".")
        else:
            # Formato americano: 1,234.56
            normalized = token.replace(",", "")
    elif "," in token:
        # Vírgula de milhar americana (ex.: 1,450 ou 12,345,678) vs vírgula decimal brasileira (849,99)
        if re.fullmatch(r"\d{1,3}(?:,\d{3})+", token):
            normalized = token.replace(",", "")
        else:
            parts = token.split(",")
            if len(parts) > 2:
                return None
            normalized = token.replace(",", ".")
    elif "." in token:
        # Ponto de milhar brasileiro sem centavos (ex.: 2.499 ou 10.499 ou 1.000.000)
        if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", token):
            normalized = token.replace(".", "")
        else:
            parts = token.split(".")
            if len(parts) > 2:
                return None
            normalized = token
    else:
        normalized = token

    try:
        value = float(normalized)
    except ValueError:
        return None

    if not math.isfinite(value) or value <= 0:
        return None
    return round(value, 2)


def extract_storage_capacities_gb(text: str) -> list[int]:
    """Extrai capacidades de memória/armazenamento convertidas para GB inteiros."""
    if not text:
        return []
    norm = normalize_text(text)
    capacities: list[int] = []

    for num_str, unit in STORAGE_EXPLICIT_RE.findall(norm):
        val = int(num_str)
        gb_val = val * 1024 if unit.lower() == "tb" else val
        if gb_val not in capacities:
            capacities.append(gb_val)

    for rom_str in STORAGE_COMPACT_RE.findall(text):
        rom_gb = int(rom_str)
        if rom_gb not in capacities:
            capacities.append(rom_gb)

    return capacities


def extract_canonical_colors(text: str) -> list[str]:
    """Retorna lista ordenada de cores canônicas detectadas como palavras inteiras no texto."""
    if not text:
        return []
    words = set(normalize_text(text).split())
    found: list[str] = []
    for canonical, aliases in COLOR_GROUPS:
        if any(a in words for a in aliases):
            found.append(canonical)
    return found


def target_required_color(target_name: str) -> str | None:
    """Determina se o nome do produto-alvo exige uma única cor estrita.

    Quando o catálogo expressa alternativas ('ELG F80N (ou F80W Branco)' / 'Preto/Branco')
    ou múltiplas cores, não restringe a cor.
    """
    norm_name = normalize_text(target_name)
    if " ou " in f" {norm_name} " or "/" in target_name:
        return None
    colors = extract_canonical_colors(target_name)
    if len(colors) == 1:
        return colors[0]
    return None


def is_accessory_or_part_listing(
    candidate_title: str,
    target_name: str = "",
    target_keywords: list[str] | None = None,
    *,
    has_anchored_storage: bool = False,
) -> tuple[bool, str | None]:
    """Avalia de forma unificada se `candidate_title` é acessório/peça avulsa do `target`."""
    norm_title = normalize_text(candidate_title)
    if not norm_title:
        return False, None

    keywords = target_keywords or []
    positive_kw_parts = [
        p
        for kw in keywords
        for p in normalize_text(kw).split()
        if p and not p.startswith("-")
    ]
    norm_target = normalize_text(target_name)
    target_tokens = set(norm_target.split()) | set(positive_kw_parts)
    norm_target_blob = f"{norm_target} {' '.join(positive_kw_parts)}".strip()

    title_tokens = set(norm_title.split())
    leads_with_device = norm_title.startswith(DEVICE_HEAD_PREFIXES) or has_anchored_storage

    # 1. Se o título começa com substantivo de acessório/peça e o alvo NÃO é esse acessório:
    for prefix in ACCESSORY_HEAD_PREFIXES:
        head_word = prefix.strip().split()[0]
        if norm_title.startswith(prefix) and head_word not in target_tokens:
            # Exceção importante: produtos cujo próprio domínio É suporte articulado (ex.: 'Zinnia Nimbo 110 V2'),
            # identificados pela ausência de marcadores de monitor/celular/relógio/áudio no alvo:
            if head_word in ("suporte", "suportes") and not (target_tokens & ELECTRONIC_DEVICE_MARKERS):
                continue
            return True, head_word

    # 2. Palavras estritas de peças avulsas (capinha, película, pulseira, parafuso, ponteira)
    if not leads_with_device:
        for word in STRICT_SPARE_PART_WORDS:
            if word in title_tokens and word not in target_tokens:
                return True, word
    else:
        # Mesmo quando cita capacidade ('Capa Capinha Para Edge 50 Ultra 512GB'), o item já foi barrado
        # na regra 1 se começar com acessório; ainda barramos 'kit parafusos' ou 'pelicula' isolada sem lead de aparelho.
        if not norm_title.startswith(DEVICE_HEAD_PREFIXES):
            for word in ("capinha", "pelicula", "peliculas", "pulseira", "bracelete", "parafuso", "parafusos"):
                if word in title_tokens and word not in target_tokens:
                    return True, word

    # 3. Frases preposicionadas de compatibilidade ('fonte para ...', 'suporte para ...', 'carregador para ...')
    for phrase in ACCESSORY_COMPATIBILITY_PHRASES:
        clean_phrase = phrase.strip()
        if phrase in norm_title and clean_phrase not in norm_target_blob:
            head_word = clean_phrase.split()[0]
            if head_word in ("suporte", "suportes") and (
                "suporte" in target_tokens or not (target_tokens & ELECTRONIC_DEVICE_MARKERS)
            ):
                continue
            if leads_with_device and not norm_title.startswith(ACCESSORY_HEAD_PREFIXES):
                continue
            return True, clean_phrase

    # 4. 'cabo' isolado fora de anúncios que começam como dispositivo ('Monitor ... Cabo DP')
    if (
        "cabo" in title_tokens
        and "cabo" not in target_tokens
        and not norm_title.startswith(DEVICE_HEAD_PREFIXES)
    ):
        return True, "cabo"

    return False, None


def safe_json_for_html_script(data: object) -> str:
    """Serializa objeto em JSON seguro para incorporação dentro de tags <script> HTML (anti-XSS)."""
    raw = json.dumps(data, ensure_ascii=False)
    return (
        raw.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def escape_telegram_html(value: object) -> str:
    """Escapa texto dinâmico para uso seguro em mensagens Telegram com parse_mode='HTML'."""
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def redact_secrets(text: str, extra_secret: str | None = None) -> str:
    """Remove tokens de bot Telegram e segredos de mensagens de erro/log."""
    if not text:
        return ""
    redacted = TELEGRAM_TOKEN_URL_RE.sub(r"\1***REDACTED***", str(text))
    if extra_secret and len(extra_secret) >= 6:
        redacted = redacted.replace(extra_secret, "***REDACTED***")
    return redacted


def validate_external_http_url(url: str, *, allow_private: bool = False) -> str:
    """Valida que uma URL utiliza http/https e não aponta para loopback, link-local ou rede interna (anti-SSRF)."""
    if not url or not isinstance(url, str):
        raise ValueError("URL vazia ou inválida.")
    cleaned = url.strip()
    parsed = urlparse(cleaned)
    if parsed.scheme.lower() not in ("http", "https"):
        raise ValueError(f"Esquema de URL não permitido ('{parsed.scheme}'): use http ou https.")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise ValueError("URL sem hostname válido.")

    if not allow_private:
        blocked_hosts = {"localhost", "metadata.google.internal", "0.0.0.0"}
        if host in blocked_hosts or host.endswith((".local", ".internal")):
            raise ValueError(f"Host interno/local bloqueado por política anti-SSRF: '{host}'.")
        try:
            ip = ipaddress.ip_address(host)
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
                or ip.is_unspecified
            ):
                raise ValueError(f"Endereço IP restrito bloqueado por política anti-SSRF: '{host}'.")
        except ValueError as exc:
            if "anti-SSRF" in str(exc):
                raise

    return cleaned
