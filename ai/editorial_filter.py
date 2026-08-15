"""Detect whether an article belongs to the literary / publishing editorial scope."""

from __future__ import annotations

import re
import unicodedata

from bot.config import settings

# Strong off-topic signals (multilingual). Require literary counter-signals to keep.
OFF_TOPIC_TERMS = (
    # Music
    "album",
    "concert",
    "concierto",
    "recital",
    "festival de musica",
    "festival de música",
    "music festival",
    "grammy",
    "billboard",
    "spotify",
    "single release",
    "tour dates",
    "gira musical",
    "hip-hop",
    "hip hop",
    "rock band",
    "banda de rock",
    "pop star",
    "cantante",
    "cantautor",
    "musician",
    "músico",
    "musico",
    "orquesta",
    "symphony",
    "operetta",
    # Film / TV / streaming
    "pelicula",
    "película",
    "movie",
    "film review",
    "film festival",
    "festival de cine",
    "cannes film",
    "oscar",
    "emmy",
    "netflix series",
    "tv series",
    "serie de television",
    "serie de televisión",
    "streaming platform",
    "box office",
    "taquilla",
    "director de cine",
    "screenplay",
    "guion cinematografico",
    "guion cinematográfico",
    # Sports
    "football",
    "soccer",
    "futbol",
    "fútbol",
    "basketball",
    "tennis",
    "formula 1",
    "f1 ",
    " olympics",
    "olimpiadas",
    " mundial ",
    "champions league",
    # Fashion / lifestyle / food
    "fashion week",
    "pasarela",
    "runway",
    "makeup trend",
    "restaurant review",
    "restaurante",
    "chef ",
    "receta de cocina",
    "recipe ",
    # Gaming / tech / business general (not publishing-specific)
    "video game",
    "videojuego",
    "playstation",
    "xbox",
    "smartphone launch",
    "startup funding round",
    "job seeker",
    "job seekers",
    "resume",
    "résumé",
    "curriculum vitae",
    "marketer",
    "marketers",
    "marketing campaign",
    "payment company",
    "fintech",
    "private equity",
    "merger talks",
    "acquisition talks",
    "stock price",
    "earnings report",
    "wall street",
    "stripe",
    "paypal",
)

# Literary / publishing signals. Any match helps keep the article.
ON_TOPIC_TERMS = (
    "book",
    "books",
    "libro",
    "libros",
    "novel",
    "novela",
    "novelist",
    "author",
    "autor",
    "autora",
    "writer",
    "escritor",
    "escritora",
    "poet",
    "poeta",
    "poetry",
    "poesia",
    "poesía",
    "publisher",
    "publishers",
    "publishing",
    "publishing house",
    "book publisher",
    "trade publishing",
    "imprint",
    "industria editorial",
    "book industry",
    "publishing industry",
    "publishing sector",
    "mundo editorial",
    "book trade",
    "manuscrito",
    "bestseller",
    "best seller",
    "bookshop",
    "bookstore",
    "libreria",
    "librería",
    "book fair",
    "feria del libro",
    "salon du livre",
    "buchmesse",
    "literature",
    "literatura",
    "literary",
    "literario",
    "literaria",
    # German / French (common in EU feeds)
    "roman",
    "romans",
    "buch",
    "bucher",
    "bücher",
    "autorin",
    "schriftsteller",
    "verlag",
    "verlage",
    "livre",
    "livres",
    "auteur",
    "autrice",
    "editeur",
    "éditeur",
    "editions",
    "éditions",
    "essay",
    "ensayo",
    "memoir",
    "memorias",
    "biography",
    "biografia",
    "biografía",
    "translation rights",
    "derechos de traduccion",
    "derechos de traducción",
    "book review",
    "reseña",
    "critica literaria",
    "crítica literaria",
    "reading list",
    "short story",
    "relato",
    "cuento",
    "anthology",
    "antologia",
    "antología",
    "booker",
    "pulitzer",
    "nobel de literatura",
    "nobel prize in literature",
    "print run",
    "tirada",
    "hardcover",
    "paperback",
    "tapa dura",
    "tapa blanda",
    "isbn",
    "copyright",
    "derechos de autor",
)

# If these appear without strong on-topic terms, usually off-scope for this monitor.
WEAK_OFF_TOPIC_TERMS = (
    " musica",
    " música",
    " music ",
    " cine ",
    " cinema ",
    " serie ",
    " deporte",
    " sports ",
    " moda ",
    " fashion ",
)

_NEGATED_SCOPE = re.compile(
    r"("
    r"sin relaci[oó]n con libros|sin relacion con libros|"
    r"no guarda relaci[oó]n|not related to books|"
    r"without.*(?:book|literary|publishing)|"
    r"no.*(?:literary|editorial|book).*(?:angle|vinculo|vínculo)"
    r")",
    re.IGNORECASE,
)


def _normalize(text: str) -> str:
    text = text.lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _count_terms(text: str, terms: tuple[str, ...]) -> int:
    return sum(1 for term in terms if term in text)


def is_editorial_scope(
    *,
    titulo: str = "",
    titular_traducido: str | None = None,
    resumen: str | None = None,
    resumen_generado: str | None = None,
) -> bool:
    """
    Return True if the article plausibly belongs to books / publishing / literary culture.

    Used as a safety net after LLM classification for broad culture feeds.
    """
    parts = [
        titular_traducido or "",
        titulo or "",
        resumen_generado or "",
        resumen or "",
    ]
    text = _normalize(" ".join(p for p in parts if p))
    if not text:
        return False

    if _NEGATED_SCOPE.search(text):
        return False

    on_topic = _count_terms(text, ON_TOPIC_TERMS)
    off_topic = _count_terms(text, OFF_TOPIC_TERMS)
    weak_off = _count_terms(text, WEAK_OFF_TOPIC_TERMS)

    if on_topic >= 2:
        return True
    if on_topic >= 1 and off_topic == 0 and weak_off == 0:
        return True
    if off_topic >= 1 and on_topic == 0:
        return False
    if weak_off >= 2 and on_topic == 0:
        return False
    if weak_off >= 1 and on_topic == 0:
        return False
    if off_topic >= 1 and on_topic <= off_topic:
        return False
    return on_topic > 0


def filter_editorial_scope(articles: list[dict]) -> list[dict]:
    """Keep only articles within literary / publishing editorial scope."""
    kept: list[dict] = []
    for article in articles:
        if is_editorial_scope(
            titulo=article.get("titulo_original", ""),
            titular_traducido=article.get("titular_traducido"),
            resumen=article.get("resumen_raw"),
            resumen_generado=article.get("resumen_generado"),
        ):
            kept.append(article)
    return kept


def apply_keyword_scope_filter(articles: list[dict]) -> list[dict]:
    """
    Keyword safety net after LLM classification.

    Articles with relevance_score >= min_relevance_score skip re-filtering only
    when they still pass is_editorial_scope (avoids EN/ES-heavy false negatives
    on valid DE/FR pieces, but drops mis-tagged business/tech noise).
    """
    kept: list[dict] = []
    min_score = settings.min_relevance_score
    for article in articles:
        in_scope = is_editorial_scope(
            titulo=article.get("titulo_original", ""),
            titular_traducido=article.get("titular_traducido"),
            resumen=article.get("resumen_raw"),
            resumen_generado=article.get("resumen_generado"),
        )
        score = article.get("relevance_score") or 0
        if in_scope:
            kept.append(article)
        elif score < min_score:
            continue
        # High LLM score but keyword filter disagrees — drop (likely false positive).
    return kept
