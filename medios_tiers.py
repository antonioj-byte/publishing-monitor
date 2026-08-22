"""Tier 1 / Tier 2 classification for media sources."""

from __future__ import annotations

# Revistas literarias / ensayo de referencia internacional (lista cerrada)
TIER1_IDEAS = {
    "The New Yorker",
    "New York Review of Books",
    "The Paris Review",
    "London Review of Books",
    "Harper's Magazine",
}

# Prensa especializada + cabeceras generalistas con sección libros/cultura editorial
TIER1_PRENSA = {
    # Industria editorial
    "Publishers Weekly",
    "The Bookseller",
    "Publishing Perspectives",
    "Livres Hebdo",
    "Publishnews",
    # Generalistas — secciones libros / cultura editorial
    "El País Babelia",
    "La Vanguardia Cultura",
    "Le Monde Livres",
    "FAZ Feuilleton",
    "Corriere Cultura",
    "La Repubblica Cultura",
    "The Guardian Books",
    "Financial Times Books",
    "NYT Books",
    "Washington Post Books",
    "Neue Zürcher Zeitung Kultur",
}

TIER1_ALL = TIER1_IDEAS | TIER1_PRENSA


def get_tier(nombre: str, categoria_default: str = "") -> int:
    """Return canonical tier for a media outlet. Only explicit Tier 1 lists qualify."""
    del categoria_default  # no blanket promotion by category
    if nombre in TIER1_ALL:
        return 1
    return 2


def tier_label(tier: int) -> str:
    return "Tier 1" if tier == 1 else "Tier 2"
