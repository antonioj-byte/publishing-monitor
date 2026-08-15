"""Natural-language and voice report intents (informal Spanish)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from bot.report_parser import ParsedReportRequest, parse_command_args, parse_free_text

RequestKind = Literal["daily", "hoy", "filtered", "continuation", "unknown"]

_MORE_TEXT = re.compile(
    r"^(?:/informe_mas|informe\s+mas|informe\s+más|más\s+informaci[oó]n|"
    r"mas\s+informaci[oó]n|continuar|sigue|siguiente|"
    r"(?:dame|ponme)\s+(?:el\s+)?resto|lo\s+dem[aá]s)\s*$",
    re.IGNORECASE,
)

_HOY_TEXT = re.compile(
    r"\b("
    r"hoy|de hoy|esta mañana|informe de hoy|qu[eé] hay hoy|"
    r"lo de hoy|novedades de hoy"
    r")\b",
    re.IGNORECASE,
)

_DAILY_TEXT = re.compile(
    r"\b("
    r"informe del d[ií]a|informe diario|lo de siempre|"
    r"el informe|resumen del d[ií]a|digest"
    r")\b",
    re.IGNORECASE,
)

_FLUFF_PREFIXES: tuple[str, ...] = (
    r"^eh?\s+",
    r"^(?:oye|bueno|vale|ok|perfecto)[,\s]+",
    r"^(?:dame|ponme|p[aá]same|p[aá]samelo|ens[eé][aá]me|mu[eé]strame|muestrame|quiero ver|quiero|a ver|me gustar[ií]a ver)\s+",
    r"^podr[ií]as (?:darme|mandarme|pasarme)\s+",
    r"^(?:un\s+)?(?:el\s+)?(?:informe|resumen|digest)\s+",
    r"^(?:de\s+|sobre\s+|del?\s+)",
)

_INFORMAL_DAY_PHRASES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(esta|la)\s+semana\b", re.IGNORECASE), "7 días"),
    (re.compile(r"\buna semana\b", re.IGNORECASE), "7 días"),
    (re.compile(r"\b(quincena|dos semanas)\b", re.IGNORECASE), "14 días"),
    (re.compile(r"\bel mes\b", re.IGNORECASE), "30 días"),
    (re.compile(r"\b(últimos|ultimos)\s+d[ií]as\b", re.IGNORECASE), "últimos 7 días"),
    (re.compile(r"\bhace unos d[ií]as\b", re.IGNORECASE), "7 días"),
)


@dataclass(frozen=True)
class UserRequest:
    kind: RequestKind
    filter: ParsedReportRequest | None = None
    raw_text: str = ""


def normalize_informal_text(text: str) -> str:
    """Expand colloquial time phrases before rule-based parsing."""
    cleaned = re.sub(r"\s+", " ", text.strip())
    for pattern, replacement in _INFORMAL_DAY_PHRASES:
        cleaned = pattern.sub(replacement, cleaned)
    return cleaned


def _strip_leading_fluff(text: str) -> str:
    blob = text.strip()
    for _ in range(8):
        changed = False
        for pattern in _FLUFF_PREFIXES:
            updated = re.sub(pattern, "", blob, count=1, flags=re.IGNORECASE).strip()
            if updated != blob:
                blob = updated
                changed = True
        if not changed:
            break
    return blob


def _parse_loose_blob(blob: str) -> ParsedReportRequest | None:
    """Parse fragments like «ficción en alemania» or «qué hay de poesía»."""
    work = blob.strip().rstrip("?.!")
    if not work:
        return None

    work = re.sub(
        r"^(?:qu[eé] hay|que hay|algo de|cosas de|novedades de)\s+(?:de\s+)?",
        "",
        work,
        flags=re.IGNORECASE,
    ).strip()

    days: int | None = None
    match = re.search(r"(\d+)\s+d[ií]as?", work, re.IGNORECASE)
    if match:
        days = int(match.group(1))
        work = (work[: match.start()] + work[match.end() :]).strip()

    try:
        return parse_command_args(work.split())
    except ValueError:
        pass

    try:
        synthetic = f"informe últimos {days or 7} días {work}"
        return parse_free_text(synthetic)
    except ValueError:
        return None


def informal_ack(request: UserRequest) -> str:
    """Short, friendly confirmation before generating a report."""
    if request.kind == "continuation":
        return "Vale, sigo con el informe anterior…"
    if request.kind == "hoy":
        return "Perfecto, miro qué ha salido hoy…"
    if request.kind == "daily":
        return "Genial, te preparo el informe del día…"
    if request.kind == "filtered" and request.filter:
        bits: list[str] = []
        if request.filter.tag_labels:
            bits.append(request.filter.tag_labels[0].lower())
        if request.filter.location_label:
            bits.append(f"en {request.filter.location_label.lower()}")
        topic = " · ".join(bits) if bits else "con esos filtros"
        return f"Entendido — informe de {topic} ({request.filter.days} días). Dame un momento…"
    return "No he pillado del todo la petición. Prueba «informe 7 ficción» o un audio más claro."


def parse_user_request(text: str) -> UserRequest:
    """Parse informal text or voice transcription into a report intent."""
    raw = text.strip()
    if not raw or raw.startswith("/"):
        return UserRequest(kind="unknown", raw_text=raw)

    if _MORE_TEXT.match(raw):
        return UserRequest(kind="continuation", raw_text=raw)

    normalized = normalize_informal_text(raw)

    if _HOY_TEXT.search(normalized) and not re.search(r"\b\d+\s+d[ií]as", normalized, re.I):
        return UserRequest(kind="hoy", raw_text=raw)

    try:
        parsed = parse_free_text(normalized)
    except ValueError:
        parsed = None
    if parsed:
        return UserRequest(kind="filtered", filter=parsed, raw_text=raw)

    blob = _strip_leading_fluff(normalized)
    if blob:
        try:
            loose = _parse_loose_blob(blob)
        except ValueError:
            loose = None
        if loose:
            return UserRequest(kind="filtered", filter=loose, raw_text=raw)

    if _DAILY_TEXT.search(normalized) or re.fullmatch(
        r"(?:informe|resumen|digest)\s*",
        normalized,
        flags=re.IGNORECASE,
    ):
        return UserRequest(kind="daily", raw_text=raw)

    return UserRequest(kind="unknown", raw_text=raw)
