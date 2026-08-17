"""Resolve user-facing media outlet names for filtered reports."""

from __future__ import annotations

import csv
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from bot.config import MEDIOS_CSV, settings
from db.connection import get_connection

_MEDIO_PREFIXES = ("el ", "la ", "le ", "les ", "the ")


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[_\-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _slug(text: str) -> str:
    return _normalize(text).replace(" ", "_")


@lru_cache(maxsize=1)
def _catalog_from_csv() -> tuple[str, ...]:
    names: list[str] = []
    if not MEDIOS_CSV.is_file():
        return tuple()
    with MEDIOS_CSV.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("activo", "true").strip().lower() in ("1", "true", "yes"):
                name = row.get("nombre", "").strip()
                if name:
                    names.append(name)
    return tuple(sorted(names, key=len, reverse=True))


def _aliases_for_name(name: str) -> list[str]:
    normalized = _normalize(name)
    aliases = {normalized, _slug(name)}
    for prefix in _MEDIO_PREFIXES:
        if normalized.startswith(prefix):
            aliases.add(normalized[len(prefix) :].strip())
    return sorted(aliases, key=len, reverse=True)


@lru_cache(maxsize=1)
def _alias_map() -> tuple[tuple[str, str], ...]:
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for name in _catalog_from_csv():
        for alias in _aliases_for_name(name):
            if alias in seen:
                continue
            seen.add(alias)
            pairs.append((alias, name))
    return tuple(sorted(pairs, key=lambda item: -len(item[0])))


def resolve_medio(name: str) -> str | None:
    """Resolve one token or phrase to the canonical medio name."""
    normalized = _normalize(name)
    if not normalized:
        return None
    for alias, canonical in _alias_map():
        if normalized == alias:
            return canonical
    return None


def extract_medio_from_text(text: str) -> tuple[str | None, str]:
    """Find a medio in free text; return canonical name and cleaned remainder."""
    normalized = _normalize(text)
    if not normalized:
        return None, text.strip()

    for alias, canonical in _alias_map():
        pattern = rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])"
        if re.search(pattern, normalized):
            remainder = re.sub(pattern, " ", normalized)
            remainder = re.sub(r"\s+", " ", remainder).strip(" ,.-_")
            return canonical, remainder
    return None, text.strip()


def lookup_medio_id(nombre: str) -> int | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM medios WHERE nombre = ? AND activo = 1",
            (nombre,),
        ).fetchone()
    return int(row["id"]) if row else None


def list_available_medios(*, limit: int = 25) -> str:
    names = list(_catalog_from_csv())
    lines = [
        "📰 Medios disponibles para /informe",
        "",
        "Ejemplos:",
        "  /informe 7 les inrocks",
        "  /informe le monde livres",
        "  /informe 14 the guardian books",
        "",
    ]
    if not names:
        lines.append("(Catálogo vacío — revisa medios.csv)")
        return "\n".join(lines)

    shown = names[:limit]
    for name in shown:
        lines.append(f"  • {name}")
    if len(names) > limit:
        lines.append(f"  … y {len(names) - limit} más (escribe el nombre en /informe)")
    lines.extend(
        [
            "",
            "Combina con tags o países:",
            "  /informe 7 les inrocks ficcion",
            "  /informe 7 francia  (todos los medios FR)",
        ]
    )
    return "\n".join(lines)
