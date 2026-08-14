"""Country codes, aliases and filters for regional reports."""

from __future__ import annotations

import re
import unicodedata

from db.connection import get_connection

# ISO 3166-1 alpha-2 per medio (nombre exacto en medios.csv)
MEDIO_PAISES: dict[str, str] = {
    "Publishers Weekly": "us",
    "The Bookseller": "gb",
    "Publishing Perspectives": "us",
    "Livres Hebdo": "fr",
    "El País Babelia": "es",
    "El Mundo Cultura": "es",
    "La Vanguardia Cultura": "es",
    "ABC Cultura": "es",
    "Cinco Días Cultura": "es",
    "Le Monde Livres": "fr",
    "Le Figaro Livres": "fr",
    "Libération Livres": "fr",
    "FAZ Feuilleton": "de",
    "Süddeutsche Kultur": "de",
    "Die Welt Kultur": "de",
    "Corriere Cultura": "it",
    "La Repubblica Cultura": "it",
    "La Stampa Cultura": "it",
    "Il Sole 24 Ore Cultura": "it",
    "Il Fatto Quotidiano Cultura": "it",
    "The Guardian Books": "gb",
    "The Times Books": "gb",
    "Financial Times Books": "gb",
    "The Telegraph Books": "gb",
    "Neue Zürcher Zeitung Kultur": "ch",
    "Le Temps Culture": "ch",
    "Le Soir Culture": "be",
    "Der Standard Kultur": "at",
    "Die Presse Kultur": "at",
    "NYT Books": "us",
    "Washington Post Books": "us",
    "Wall Street Journal Books": "us",
    "Los Angeles Times Books": "us",
    "Boston Globe Books": "us",
    "Chicago Tribune Books": "us",
    "The Globe and Mail Books": "ca",
    "National Post Books": "ca",
    "La Presse Arts": "ca",
    "La Nación Libros": "ar",
    "Clarín Cultura": "ar",
    "Reforma Cultura": "mx",
    "El Universal Cultura": "mx",
    "El Mercurio Cultura": "cl",
    "La Tercera Cultura": "cl",
    "El Tiempo Cultura": "co",
    "El Espectador Libros": "co",
    "El Comercio Cultura": "pe",
    "El País Uruguay Cultura": "uy",
    "Folha de S.Paulo Ilustrada": "br",
    "O Globo Cultura": "br",
    "The Japan Times Culture": "jp",
    "Nikkei Asia Culture": "jp",
    "South China Morning Post Culture": "hk",
    "The Hindu Books": "in",
    "The New Yorker": "us",
    "New York Review of Books": "us",
    "The Paris Review": "us",
    "Harper's Magazine": "us",
    "The Atlantic": "us",
    "London Review of Books": "gb",
    "Granta": "gb",
    "n+1": "us",
    "The Believer": "us",
    "The Threepenny Review": "us",
    "Letras Libres": "mx",
    "Revista de Occidente": "es",
    "Gatopardo": "mx",
    "El Malpensante": "co",
    "Anfibia": "ar",
    "Nexos": "mx",
    "Jot Down": "es",
    "La Maleta de Portbou": "es",
    "Les Temps Modernes": "fr",
    "Esprit": "fr",
    "La Nouvelle Revue Française": "fr",
    "Le Débat": "fr",
    "XXI": "fr",
    "Nuovi Argomenti": "it",
    "MicroMega": "it",
    "Il Mulino": "it",
    "Merkur": "de",
    "Lettre International": "de",
    "Sinn und Form": "de",
    "The Economist Culture": "gb",
    "Time": "us",
    "Newsweek": "us",
    "Der Spiegel Kultur": "de",
    "Die Zeit Kultur": "de",
    "Focus Kultur": "de",
    "Stern Kultur": "de",
    "Courrier International": "fr",
    "L'Obs Culture": "fr",
    "Le Point Culture": "fr",
    "L'Express Culture": "fr",
    "Les Inrocks": "fr",
    "Internazionale": "it",
    "L'Espresso Cultura": "it",
    "Panorama Cultura": "it",
}

PAIS_LABELS: dict[str, str] = {
    "us": "Estados Unidos",
    "gb": "Reino Unido",
    "es": "España",
    "fr": "Francia",
    "de": "Alemania",
    "it": "Italia",
    "ch": "Suiza",
    "at": "Austria",
    "be": "Bélgica",
    "ca": "Canadá",
    "mx": "México",
    "ar": "Argentina",
    "cl": "Chile",
    "co": "Colombia",
    "pe": "Perú",
    "uy": "Uruguay",
    "br": "Brasil",
    "jp": "Japón",
    "hk": "China (Hong Kong)",
    "in": "India",
}

REGION_LABELS: dict[str, str] = {
    "eu": "Europa",
    "us": "Estados Unidos (región)",
    "uk": "Reino Unido (región)",
    "latam": "Latinoamérica",
    "ca": "Canadá (región)",
    "apac": "Asia-Pacífico",
}

# Aliases → ISO code or region key (prefixed with @ for regions)
ALIASES: dict[str, str] = {
    "alemania": "de",
    "germany": "de",
    "deutschland": "de",
    "espana": "es",
    "españa": "es",
    "spain": "es",
    "francia": "fr",
    "france": "fr",
    "italia": "it",
    "italy": "it",
    "reino unido": "gb",
    "uk": "gb",
    "britain": "gb",
    "gran bretana": "gb",
    "estados unidos": "us",
    "eeuu": "us",
    "usa": "us",
    "us": "us",
    "mexico": "mx",
    "méxico": "mx",
    "argentina": "ar",
    "chile": "cl",
    "colombia": "co",
    "peru": "pe",
    "perú": "pe",
    "uruguay": "uy",
    "brasil": "br",
    "brazil": "br",
    "canada": "ca",
    "canadá": "ca",
    "japon": "jp",
    "japón": "jp",
    "japan": "jp",
    "china": "hk",
    "india": "in",
    "suiza": "ch",
    "switzerland": "ch",
    "austria": "at",
    "belgica": "be",
    "bélgica": "be",
    "belgium": "be",
    "europa": "@eu",
    "europe": "@eu",
    "latam": "@latam",
    "america latina": "@latam",
    "américa latina": "@latam",
    "latinoamerica": "@latam",
    "latinoamérica": "@latam",
    "asia": "@apac",
    "apac": "@apac",
    "asia pacifico": "@apac",
    "asia-pacífico": "@apac",
}

MAX_REPORT_DAYS = 30


def _normalize_key(text: str) -> str:
    text = text.lower().strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"\s+", " ", text)
    return text


def resolve_location(name: str) -> tuple[str | None, str | None, str]:
    """
    Resolve user input to (pais_code, region_code, display_label).
    Exactly one of pais or region is set when successful.
    """
    key = _normalize_key(name)
    if not key:
        raise ValueError("Indica un país o región.")

    if key in ALIASES:
        target = ALIASES[key]
    elif key in PAIS_LABELS:
        target = key
    elif key in REGION_LABELS:
        target = f"@{key}"
    else:
        matches = [
            (alias, code)
            for alias, code in ALIASES.items()
            if key in alias or alias in key
        ]
        if len(matches) == 1:
            target = matches[0][1]
        else:
            raise ValueError(
                f"No reconozco «{name}». Usa /paises para ver opciones."
            )

    if target.startswith("@"):
        region = target[1:]
        return None, region, REGION_LABELS.get(region, region.upper())

    return target, None, PAIS_LABELS.get(target, target.upper())


def get_pais_for_medio(nombre: str) -> str:
    return MEDIO_PAISES.get(nombre, "xx")


def list_available_locations() -> str:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT pais, COUNT(*) AS n
            FROM medios
            WHERE activo = 1 AND pais IS NOT NULL AND pais != 'xx'
            GROUP BY pais
            ORDER BY n DESC, pais
            """
        ).fetchall()
        regions = conn.execute(
            """
            SELECT region, COUNT(*) AS n
            FROM medios
            WHERE activo = 1
            GROUP BY region
            ORDER BY n DESC
            """
        ).fetchall()

    lines = ["Países con medios monitorizados:", ""]
    for row in rows:
        label = PAIS_LABELS.get(row["pais"], row["pais"])
        lines.append(f"• {label} ({row['pais']}) — {row['n']} medios")

    lines.extend(["", "Regiones amplias:", ""])
    for row in regions:
        label = REGION_LABELS.get(row["region"], row["region"])
        lines.append(f"• {label} — {row['n']} medios")

    lines.extend(
        [
            "",
            "Ejemplos:",
            "/informe 7 alemania",
            "/informe 10 china",
            "/informe 3 latam",
            "",
            "También en texto libre:",
            "«informe últimos 7 días en alemania»",
            "",
            f"Máximo: {MAX_REPORT_DAYS} días.",
            "",
            "Nota: cobertura de China vía SCMP (Hong Kong).",
        ]
    )
    return "\n".join(lines)
