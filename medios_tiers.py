"""Tier 1 / Tier 2 classification for media sources."""

from __future__ import annotations

# Revistas de ideas, ensayo y crítica — referencia editorial
TIER1_IDEAS = {
    "The New Yorker",
    "New York Review of Books",
    "The Paris Review",
    "Harper's Magazine",
    "The Atlantic",
    "London Review of Books",
    "Granta",
    "n+1",
    "The Believer",
    "The Threepenny Review",
    "Letras Libres",
    "Revista de Occidente",
    "Gatopardo",
    "El Malpensante",
    "Anfibia",
    "Nexos",
    "Jot Down",
    "La Maleta de Portbou",
    "Les Temps Modernes",
    "Esprit",
    "La Nouvelle Revue Française",
    "Le Débat",
    "XXI",
    "Nuovi Argomenti",
    "MicroMega",
    "Il Mulino",
    "Merkur",
    "Lettre International",
    "Sinn und Form",
}

# Cabeceras de prensa / semanarios con sección cultura-libros de alto perfil
TIER1_PRENSA = {
    "The Guardian Books",
    "NYT Books",
    "Le Monde Livres",
    "FAZ Feuilleton",
    "Neue Zürcher Zeitung Kultur",
    "Financial Times Books",
    "Die Zeit Kultur",
    "Courrier International",
    "Internazionale",
    "The Economist Culture",
    "El País Babelia",
}

TIER1_ALL = TIER1_IDEAS | TIER1_PRENSA


def get_tier(nombre: str, categoria_default: str = "") -> int:
    if nombre in TIER1_ALL:
        return 1
    if categoria_default == "ideas":
        return 1
    return 2


def tier_label(tier: int) -> str:
    return "Tier 1" if tier == 1 else "Tier 2"
