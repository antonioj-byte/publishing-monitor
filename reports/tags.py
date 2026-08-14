"""Topical tags for editorial content classification and filtering."""

from __future__ import annotations

import re
import unicodedata

# slug → display label (15 tags)
TOPICAL_TAGS: dict[str, str] = {
    # Contenido literario
    "ficcion": "Ficción",
    "no_ficcion": "No ficción",
    "literatura_traducida": "Literatura traducida",
    "literatura_local": "Literatura local",
    "ensayo_literario": "Ensayo literario/filosófico",
    "ensayo_politico": "Ensayo político/actualidad",
    "poesia": "Poesía",
    "lij": "Infantil y juvenil (LIJ)",
    "comic": "Cómic y novela gráfica",
    # Negocio e industria
    "mundo_editorial": "Mundo editorial",
    "derechos_traducciones": "Derechos y traducciones",
    "ia_tecnologia": "IA y tecnología editorial",
    "librerias_distribucion": "Librerías y distribución",
    "audiolibros_digital": "Audiolibros y digital",
    # Eventos
    "ferias_premios": "Ferias y premios",
}

TAG_GROUPS: dict[str, list[str]] = {
    "Contenido literario": [
        "ficcion",
        "no_ficcion",
        "literatura_traducida",
        "literatura_local",
        "ensayo_literario",
        "ensayo_politico",
        "poesia",
        "lij",
        "comic",
    ],
    "Negocio e industria": [
        "mundo_editorial",
        "derechos_traducciones",
        "ia_tecnologia",
        "librerias_distribucion",
        "audiolibros_digital",
    ],
    "Eventos": [
        "ferias_premios",
    ],
}

# Longest aliases first for greedy matching
TAG_ALIASES: list[tuple[str, str]] = sorted(
    [
        ("ferias y premios", "ferias_premios"),
        ("ferias del libro", "ferias_premios"),
        ("premios literarios", "ferias_premios"),
        ("ensayo literario", "ensayo_literario"),
        ("ensayo filosófico", "ensayo_literario"),
        ("ensayo filosofico", "ensayo_literario"),
        ("ensayo político", "ensayo_politico"),
        ("ensayo politico", "ensayo_politico"),
        ("literatura traducida", "literatura_traducida"),
        ("literatura local", "literatura_local"),
        ("infantil y juvenil", "lij"),
        ("infantil juvenil", "lij"),
        ("cómic", "comic"),
        ("comic", "comic"),
        ("novela gráfica", "comic"),
        ("novela grafica", "comic"),
        ("mundo editorial", "mundo_editorial"),
        ("derechos y traducciones", "derechos_traducciones"),
        ("derechos traducciones", "derechos_traducciones"),
        ("ia y tecnología editorial", "ia_tecnologia"),
        ("ia y tecnologia editorial", "ia_tecnologia"),
        ("tecnología editorial", "ia_tecnologia"),
        ("librerías y distribución", "librerias_distribucion"),
        ("librerias y distribucion", "librerias_distribucion"),
        ("audiolibros y digital", "audiolibros_digital"),
        ("audiolibros", "audiolibros_digital"),
        ("no ficción", "no_ficcion"),
        ("no ficcion", "no_ficcion"),
        ("ficción", "ficcion"),
        ("ficcion", "ficcion"),
        ("poesía", "poesia"),
        ("poesia", "poesia"),
        ("lij", "lij"),
        ("booker", "ferias_premios"),
        ("nobel", "ferias_premios"),
        ("frankfurt", "ferias_premios"),
    ],
    key=lambda pair: -len(pair[0]),
)

VALID_TAG_KEYS = frozenset(TOPICAL_TAGS)


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def resolve_tag(name: str) -> tuple[str | None, str | None]:
    """Resolve one token or phrase to (tag_key, label)."""
    normalized = _normalize(name)
    if not normalized:
        return None, None
    if normalized in VALID_TAG_KEYS:
        return normalized, TOPICAL_TAGS[normalized]
    for alias, key in TAG_ALIASES:
        if _normalize(alias) == normalized:
            return key, TOPICAL_TAGS[key]
    return None, None


def extract_tags_from_text(text: str) -> tuple[list[str], str]:
    """Find tags in free text; return keys and remainder without tag phrases."""
    normalized = _normalize(text)
    found: list[str] = []
    remainder = normalized

    for alias, key in TAG_ALIASES:
        alias_norm = _normalize(alias)
        if alias_norm in remainder:
            if key not in found:
                found.append(key)
            remainder = remainder.replace(alias_norm, " ")

    for key in VALID_TAG_KEYS:
        if re.search(rf"\b{re.escape(key.replace('_', ' '))}\b", remainder):
            if key not in found:
                found.append(key)
            remainder = re.sub(rf"\b{re.escape(key.replace('_', ' '))}\b", " ", remainder)

    remainder = re.sub(r"\s+", " ", remainder).strip(" ,.-")
    return found, remainder


def tag_labels(keys: list[str]) -> list[str]:
    return [TOPICAL_TAGS[k] for k in keys if k in TOPICAL_TAGS]


def list_available_tags() -> str:
    lines = ["🏷️ Tags editoriales disponibles", ""]
    for group, keys in TAG_GROUPS.items():
        lines.append(f"**{group}**")
        for key in keys:
            lines.append(f"  • {TOPICAL_TAGS[key]} — `{key}`")
        lines.append("")
    lines.extend(
        [
            "Ejemplos:",
            "  /informe 7 ficcion",
            "  /informe 7 alemania poesia",
            "  /tag ferias_premios 14",
            "  «informe últimos 7 días derechos y traducciones en españa»",
        ]
    )
    return "\n".join(lines)


def validate_tags(tags: list[str]) -> list[str]:
    """Return only valid tag keys."""
    return [t for t in tags if t in VALID_TAG_KEYS]
