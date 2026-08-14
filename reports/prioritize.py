"""Editorial filtering and prioritization via semantic event clustering."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np

from bot.config import settings

logger = logging.getLogger(__name__)

_EMBEDDER = None

# Generic listicles share vocabulary ("best books 2026") and must not form mega-clusters.
GENERIC_ROUNDUP_PATTERNS = (
    r"\bbest books\b",
    r"\bbooks of (?:the )?year\b",
    r"\bbooks to read\b",
    r"\bmust[- ]read\b",
    r"\bwhat to read\b",
    r"\breading list\b",
    r"\blibros del (?:ano|año)\b",
    r"\bmejores libros\b",
    r"\bbest of \d{4}\b",
    r"\bso far in \d{4}\b",
    r"\b\d{4} so far\b",
    r"\bsummer reads?\b",
    r"\bwinter reads?\b",
    r"\bspring reads?\b",
    r"\bholiday reads?\b",
)


@dataclass(frozen=True)
class ScoreBreakdown:
    """Weighted and raw scores for one editorial event."""

    repetition_raw: float
    recency_raw: float
    tier_raw: float
    repetition_weighted: float
    recency_weighted: float
    tier_weighted: float
    total: float
    distinct_sources: int
    has_tier1: bool
    newest_age_hours: float | None
    explanation: str


@dataclass
class EditorialEvent:
    """Cluster of articles covering the same editorial event."""

    event_id: int
    articles: list[dict]
    medios: list[dict]
    representative_title: str
    score: ScoreBreakdown


@dataclass
class PrioritizationResult:
    """Output of the editorial prioritization agent."""

    events: list[EditorialEvent]
    articles: list[dict]
    total_input: int
    total_events: int
    events_above_threshold: int


def _get_embedder():
    global _EMBEDDER
    if _EMBEDDER is None:
        from fastembed import TextEmbedding

        _EMBEDDER = TextEmbedding(model_name=settings.prioritize_embedding_model)
    return _EMBEDDER


def _article_text(article: dict) -> str:
    title = article.get("titular_traducido") or article.get("titulo_original") or ""
    summary = article.get("resumen_generado") or article.get("resumen_raw") or ""
    original = article.get("titulo_original") or ""
    if original and original != title:
        return f"{title}. {original}. {summary}".strip()
    return f"{title}. {summary}".strip()


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        return dt
    except ValueError:
        return None


def _article_timestamp(article: dict) -> datetime | None:
    return _parse_datetime(article.get("fecha_publicacion")) or _parse_datetime(
        article.get("fecha_ingesta")
    )


def _article_priority_key(article: dict) -> tuple[int, int, float]:
    """Sort best articles first: relevance, Tier 1, then recency."""
    ts = _article_timestamp(article)
    ts_ord = ts.timestamp() if ts else 0.0
    tier = int(article.get("medio_tier") or 2)
    return (
        -(article.get("relevance_score") or 0),
        tier,
        -ts_ord,
    )


def _batch_priority_key(article: dict) -> tuple[int, float]:
    """Batch cap: relevance and recency only — tier is scored at event level."""
    ts = _article_timestamp(article)
    ts_ord = ts.timestamp() if ts else 0.0
    return (-(article.get("relevance_score") or 0), -ts_ord)


def _compute_embeddings(texts: list[str]) -> np.ndarray:
    if not texts:
        return np.empty((0, 0))

    embedder = _get_embedder()
    prefix = settings.prioritize_embedding_prefix
    prefixed = [f"{prefix}{text}" if prefix else text for text in texts]
    vectors = list(embedder.embed(prefixed))
    matrix = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return matrix / norms


def _article_title(article: dict) -> str:
    return article.get("titular_traducido") or article.get("titulo_original") or ""


def _is_generic_roundup(article: dict) -> bool:
    text = _article_title(article).lower()
    return any(re.search(pattern, text) for pattern in GENERIC_ROUNDUP_PATTERNS)


def _merge_threshold(article_a: dict, article_b: dict, base_threshold: float) -> float:
    same_medio = (article_a.get("medio_nombre") or "") == (article_b.get("medio_nombre") or "")
    if same_medio and article_a.get("medio_nombre"):
        return settings.prioritize_same_medio_similarity_threshold
    if _is_generic_roundup(article_a) or _is_generic_roundup(article_b):
        return settings.prioritize_generic_similarity_threshold
    return base_threshold


def _union_find_clusters(
    similarity: np.ndarray,
    articles: list[dict],
    threshold: float,
) -> list[list[int]]:
    n = similarity.shape[0]
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    for i in range(n):
        for j in range(i + 1, n):
            merge_at = _merge_threshold(articles[i], articles[j], threshold)
            if similarity[i, j] >= merge_at:
                union(i, j)

    groups: dict[int, list[int]] = {}
    for idx in range(n):
        root = find(idx)
        groups.setdefault(root, []).append(idx)

    return list(groups.values())


def _split_oversized_clusters(
    groups: list[list[int]],
    similarity: np.ndarray,
    articles: list[dict],
) -> list[list[int]]:
    max_size = settings.prioritize_max_cluster_size
    result: list[list[int]] = []

    for group in groups:
        if len(group) <= max_size:
            result.append(group)
            continue

        sub_articles = [articles[i] for i in group]
        sub_sim = similarity[np.ix_(group, group)]
        strict = max(
            settings.prioritize_generic_similarity_threshold,
            settings.prioritize_similarity_threshold + 0.08,
        )
        sub_groups = _union_find_clusters(sub_sim, sub_articles, strict)

        for sub_group in sub_groups:
            mapped = [group[i] for i in sub_group]
            if len(mapped) <= max_size:
                result.append(mapped)
            else:
                result.extend([[idx] for idx in mapped])

    return result


def limit_batch_for_prioritization(articles: list[dict]) -> tuple[list[dict], int]:
    """Cap batch size for embedding performance; prefer score, tier and recency."""
    total = len(articles)
    cap = settings.prioritize_max_batch
    if total <= cap:
        return articles, total

    ranked = sorted(articles, key=_batch_priority_key)
    logger.info(
        "Prioritization batch capped: %d → %d articles (PRIORITIZE_MAX_BATCH)",
        total,
        cap,
    )
    return ranked[:cap], total


def _distinct_medios(articles: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for article in articles:
        name = article.get("medio_nombre") or ""
        if not name or name in seen:
            continue
        seen[name] = {
            "nombre": name,
            "tier": int(article.get("medio_tier") or 2),
        }
    return list(seen.values())


def _repetition_score(distinct_sources: int) -> float:
    cap = max(1, settings.prioritize_repetition_cap)
    return min(distinct_sources / cap, 1.0)


def _recency_score(newest: datetime | None, now: datetime) -> float:
    if newest is None:
        return settings.prioritize_recency_unknown_score

    age = now - newest.astimezone(ZoneInfo("UTC"))
    hours = age.total_seconds() / 3600

    if hours <= settings.prioritize_recency_hours_full:
        return 1.0
    if hours <= settings.prioritize_recency_hours_partial:
        span = settings.prioritize_recency_hours_partial - settings.prioritize_recency_hours_full
        if span <= 0:
            return settings.prioritize_recency_partial_score
        ratio = (hours - settings.prioritize_recency_hours_full) / span
        return 1.0 - ratio * (1.0 - settings.prioritize_recency_partial_score)
    return settings.prioritize_recency_old_score


def _tier_score(distinct_sources: int, medios: list[dict]) -> float:
    has_tier1 = any(m["tier"] == 1 for m in medios)
    if has_tier1:
        return settings.prioritize_tier1_score
    if distinct_sources >= settings.prioritize_tier2_rep_threshold:
        return settings.prioritize_tier2_high_rep_score
    return settings.prioritize_tier2_low_rep_score


def _score_event(articles: list[dict], now: datetime) -> ScoreBreakdown:
    medios = _distinct_medios(articles)
    distinct_sources = len(medios)
    has_tier1 = any(m["tier"] == 1 for m in medios)

    rep_raw = _repetition_score(distinct_sources)

    timestamps = [_article_timestamp(a) for a in articles]
    valid_ts = [ts for ts in timestamps if ts is not None]
    newest = max(valid_ts) if valid_ts else None
    rec_raw = _recency_score(newest, now)

    tier_raw = _tier_score(distinct_sources, medios)

    w_rep = settings.prioritize_weight_repetition
    w_rec = settings.prioritize_weight_recency
    w_tier = settings.prioritize_weight_tier

    rep_w = rep_raw * w_rep
    rec_w = rec_raw * w_rec
    tier_w = tier_raw * w_tier
    total = rep_w + rec_w + tier_w

    age_hours: float | None = None
    if newest is not None:
        age_hours = (now - newest.astimezone(ZoneInfo("UTC"))).total_seconds() / 3600

    tier1_names = sorted(m["nombre"] for m in medios if m["tier"] == 1)
    tier_parts: list[str] = []
    if tier1_names:
        tier_parts.append(f"Tier 1: {', '.join(tier1_names)}")
    elif distinct_sources >= settings.prioritize_tier2_rep_threshold:
        tier_parts.append(
            f"solo Tier 2 con alta repetición ({distinct_sources} fuentes)"
        )
    else:
        tier_parts.append(f"solo Tier 2 ({distinct_sources} fuente(s))")

    if age_hours is not None:
        if age_hours <= 24:
            age_label = f"hace {age_hours:.0f}h"
        else:
            age_label = f"hace {age_hours / 24:.1f} días"
    else:
        age_label = "fecha desconocida"

    explanation = (
        f"{distinct_sources} fuente(s) distintas → repetición {rep_raw:.2f} "
        f"(+{rep_w:.2f}) · {age_label} → actualidad {rec_raw:.2f} (+{rec_w:.2f}) · "
        f"{tier_parts[0]} → tier {tier_raw:.2f} (+{tier_w:.2f}) · "
        f"total {total:.2f}"
    )

    return ScoreBreakdown(
        repetition_raw=rep_raw,
        recency_raw=rec_raw,
        tier_raw=tier_raw,
        repetition_weighted=rep_w,
        recency_weighted=rec_w,
        tier_weighted=tier_w,
        total=total,
        distinct_sources=distinct_sources,
        has_tier1=has_tier1,
        newest_age_hours=age_hours,
        explanation=explanation,
    )


def _pick_representative_title(articles: list[dict]) -> str:
    best = min(articles, key=_article_priority_key)
    return best.get("titular_traducido") or best.get("titulo_original") or "(sin título)"


def _order_articles_within_event(articles: list[dict]) -> list[dict]:
    return sorted(articles, key=_article_priority_key)


def cluster_articles(articles: list[dict]) -> list[list[dict]]:
    """Group articles into semantic event clusters using embedding similarity."""
    if not articles:
        return []

    if len(articles) == 1:
        return [articles]

    texts = [_article_text(a) for a in articles]
    try:
        embeddings = _compute_embeddings(texts)
    except Exception:
        logger.exception("Embedding computation failed; falling back to singleton clusters")
        return [[a] for a in articles]

    similarity = embeddings @ embeddings.T
    threshold = settings.prioritize_similarity_threshold
    index_groups = _union_find_clusters(similarity, articles, threshold)
    index_groups = _split_oversized_clusters(index_groups, similarity, articles)
    return [[articles[i] for i in group] for group in index_groups]


def score_event_cluster(articles: list[dict], event_id: int, now: datetime | None = None) -> EditorialEvent:
    """Score a single event cluster."""
    now = now or datetime.now(ZoneInfo(settings.timezone))
    score = _score_event(articles, now)
    return EditorialEvent(
        event_id=event_id,
        articles=_order_articles_within_event(articles),
        medios=_distinct_medios(articles),
        representative_title=_pick_representative_title(articles),
        score=score,
    )


def prioritize_articles(articles: list[dict]) -> PrioritizationResult:
    """
    Run the full editorial prioritization pipeline:
    1. Semantic clustering into events
    2. Weighted scoring (repetition + recency + tier)
    3. Filter by configurable threshold and sort
    """
    if not articles:
        return PrioritizationResult(
            events=[],
            articles=[],
            total_input=0,
            total_events=0,
            events_above_threshold=0,
        )

    now = datetime.now(ZoneInfo(settings.timezone))
    clusters = cluster_articles(articles)

    events: list[EditorialEvent] = []
    for idx, cluster in enumerate(clusters):
        events.append(score_event_cluster(cluster, event_id=idx, now=now))

    events.sort(key=lambda e: (-e.score.total, -e.score.distinct_sources))

    threshold = settings.prioritize_score_threshold
    selected = [e for e in events if e.score.total >= threshold]

    output_articles: list[dict] = []
    for event in selected:
        for article in event.articles:
            enriched = dict(article)
            enriched["event_id"] = event.event_id
            enriched["event_score"] = event.score.total
            enriched["event_explanation"] = event.score.explanation
            enriched["en_tendencia"] = event.score.distinct_sources >= 2
            output_articles.append(enriched)

    logger.info(
        "Prioritization: %d articles → %d events → %d above threshold (%.2f)",
        len(articles),
        len(events),
        len(selected),
        threshold,
    )

    return PrioritizationResult(
        events=selected,
        articles=output_articles,
        total_input=len(articles),
        total_events=len(events),
        events_above_threshold=len(selected),
    )


def events_to_trends(events: list[EditorialEvent], min_medios: int = 2) -> list[dict]:
    """Convert prioritized events to the trends format used by the report generator."""
    trends: list[dict] = []
    for event in events:
        if event.score.distinct_sources < min_medios:
            continue
        medios = {m["nombre"] for m in event.medios}
        trends.append(
            {
                "topic_key": str(event.event_id),
                "topic_label": event.representative_title[:120],
                "medios": medios,
                "articles": event.articles,
                "event_score": event.score.total,
                "event_explanation": event.score.explanation,
            }
        )
    trends.sort(key=lambda t: (-t["event_score"], -len(t["medios"])))
    return trends
