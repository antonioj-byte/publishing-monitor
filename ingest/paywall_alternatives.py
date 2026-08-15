"""RSS alternatives for paywalled or blocked sources."""

from __future__ import annotations

from urllib.parse import quote_plus

# Official FT RSS uses ?format=rss on section URLs (works without paywall session).
FT_BOOKS_RSS = "https://www.ft.com/books?format=rss"

# Granta's on-site /feed/ returns HTML; Substack mirrors magazine posts.
GRANTA_SUBSTACK_RSS = "https://grantamag.substack.com/feed"

# Google News RSS indexes public headlines/snippets when direct feeds or scraping fail.
GOOGLE_NEWS_QUERIES: dict[str, str] = {
    "Wall Street Journal Books": "site:wsj.com/arts-culture/books",
    "The Times Books": "site:thetimes.com culture books review",
    "Washington Post Books": "site:washingtonpost.com/entertainment/books",
    "The Globe and Mail Books": "site:theglobeandmail.com/arts/books",
}


def google_news_rss(query: str, *, hl: str = "en", gl: str = "US", ceid: str = "US:en") -> str:
    q = quote_plus(query)
    return f"https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={ceid}"


PAYWALL_ALTERNATIVES: dict[str, dict[str, str]] = {
    "Financial Times Books": {
        "problema": "Scraping devuelve 403 Forbidden",
        "alternativa": "RSS oficial de sección",
        "url": FT_BOOKS_RSS,
        "metodo": "rss",
    },
    "Wall Street Journal Books": {
        "problema": "Scraping 401; feeds Dow Jones requieren API key",
        "alternativa": "Google News RSS (titulares públicos indexados)",
        "url": google_news_rss("site:wsj.com/arts-culture/books"),
        "metodo": "rss",
    },
    "The Times Books": {
        "problema": "Sin RSS oficial; scraping mezcla secciones de cultura",
        "alternativa": "Google News RSS acotado a libros/reseñas",
        "url": google_news_rss(
            "site:thetimes.com culture books review", hl="en-GB", gl="GB", ceid="GB:en"
        ),
        "metodo": "rss",
    },
    "Washington Post Books": {
        "problema": "Feed directo feeds.washingtonpost.com/.../books vacío",
        "alternativa": "Google News RSS de la sección Books",
        "url": google_news_rss("site:washingtonpost.com/entertainment/books"),
        "metodo": "rss",
    },
    "The Globe and Mail Books": {
        "problema": "URL /arts/books/rss/ rota; categoría books sin outbound feed",
        "alternativa": "Google News RSS acotado a /arts/books",
        "url": google_news_rss(
            "site:theglobeandmail.com/arts/books", hl="en-CA", gl="CA", ceid="CA:en"
        ),
        "metodo": "rss",
    },
    "Granta": {
        "problema": "granta.com/feed/ devuelve HTML (403 en scraping)",
        "alternativa": "Feed Substack oficial de la revista",
        "url": GRANTA_SUBSTACK_RSS,
        "metodo": "rss",
    },
}
