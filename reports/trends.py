"""Detect cross-media trends (same topic in multiple outlets)."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict

STOPWORDS = {
    "about", "after", "against", "book", "books", "con", "culture", "cultura",
    "desde", "editorial", "entre", "from", "into", "livre", "livres", "more",
    "news", "over", "para", "por", "review", "that", "the", "this", "through",
    "under", "with", "without", "como", "como", "para", "sobre", "nuevo",
    "nueva", "first", "last", "year", "years", "interview", "entrevista",
}


def _normalize(text: str) -> str:
    text = text.lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _keywords(title: str) -> set[str]:
    words = _normalize(title).split()
    return {w for w in words if len(w) >= 5 and w not in STOPWORDS}


def _cluster_key(title: str) -> str | None:
    kws = sorted(_keywords(title), key=len, reverse=True)
    if len(kws) >= 2:
        return f"{kws[0]}|{kws[1]}"
    if len(kws) == 1:
        return kws[0]
    return None


def find_cross_media_trends(articles: list[dict], min_medios: int = 2) -> list[dict]:
    """
    Return trend groups where >= min_medios distinct sources cover similar topic.
    Each group: {topic, medios: set, articles: list}
    """
    buckets: dict[str, list[dict]] = defaultdict(list)
    for article in articles:
        title = article.get("titular_traducido") or article.get("titulo_original") or ""
        key = _cluster_key(title)
        if key:
            buckets[key].append(article)

    trends: list[dict] = []
    for key, group in buckets.items():
        medios = {a.get("medio_nombre", "") for a in group}
        if len(medios) >= min_medios:
            trends.append(
                {
                    "topic_key": key,
                    "topic_label": key.replace("|", " · "),
                    "medios": medios,
                    "articles": group,
                }
            )

    trends.sort(key=lambda t: (-len(t["medios"]), -len(t["articles"])))
    return trends


def boost_trend_scores(articles: list[dict], trends: list[dict]) -> list[dict]:
    """Copy articles with virtual boost flag for sorting (trend items first)."""
    trend_ids = {a["id"] for t in trends for a in t["articles"]}
    boosted = []
    for a in articles:
        item = dict(a)
        item["en_tendencia"] = a["id"] in trend_ids
        boosted.append(item)
    boosted.sort(
        key=lambda x: (
            not x.get("en_tendencia"),
            -(x.get("medio_tier") or 2),
            -(x.get("relevance_score") or 0),
        )
    )
    return boosted
