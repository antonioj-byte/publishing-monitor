"""Detect whether an article belongs to the literary / publishing editorial scope."""

from __future__ import annotations

import re
import unicodedata

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
    # Gaming / tech general
    "video game",
    "videojuego",
    "playstation",
    "xbox",
    "smartphone launch",
    "startup funding round",
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
    "editorial",
    "editoriales",
    "imprint",
    "manuscript",
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
