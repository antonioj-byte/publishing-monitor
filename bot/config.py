import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str
    telegram_bot_token: str
    telegram_chat_id: str
    database_path: str
    min_relevance_score: int
    max_articles_per_informe: int
    max_destacados: int
    max_relevantes: int
    max_secundarios: int
    max_report_words: int
    timezone: str
    # Editorial prioritization agent
    prioritize_weight_repetition: float
    prioritize_weight_recency: float
    prioritize_weight_tier: float
    prioritize_repetition_cap: int
    prioritize_similarity_threshold: float
    prioritize_score_threshold: float
    prioritize_recency_hours_full: float
    prioritize_recency_hours_partial: float
    prioritize_recency_partial_score: float
    prioritize_recency_old_score: float
    prioritize_recency_unknown_score: float
    prioritize_tier1_score: float
    prioritize_tier2_high_rep_score: float
    prioritize_tier2_low_rep_score: float
    prioritize_tier2_rep_threshold: int
    prioritize_embedding_model: str
    prioritize_embedding_prefix: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
            database_path=os.getenv("DATABASE_PATH", "./data/editorial.db"),
            min_relevance_score=int(os.getenv("MIN_RELEVANCE_SCORE", "3")),
            max_articles_per_informe=int(os.getenv("MAX_ARTICLES_PER_INFORME", "30")),
            max_destacados=int(os.getenv("MAX_DESTACADOS", "8")),
            max_relevantes=int(os.getenv("MAX_RELEVANTES", "12")),
            max_secundarios=int(os.getenv("MAX_SECUNDARIOS", "10")),
            max_report_words=int(os.getenv("MAX_REPORT_WORDS", "2500")),
            timezone=os.getenv("TIMEZONE", "Europe/Madrid"),
            prioritize_weight_repetition=float(os.getenv("PRIORITIZE_WEIGHT_REPETITION", "0.35")),
            prioritize_weight_recency=float(os.getenv("PRIORITIZE_WEIGHT_RECENCY", "0.30")),
            prioritize_weight_tier=float(os.getenv("PRIORITIZE_WEIGHT_TIER", "0.35")),
            prioritize_repetition_cap=int(os.getenv("PRIORITIZE_REPETITION_CAP", "10")),
            prioritize_similarity_threshold=float(os.getenv("PRIORITIZE_SIMILARITY_THRESHOLD", "0.68")),
            prioritize_score_threshold=float(os.getenv("PRIORITIZE_SCORE_THRESHOLD", "0.35")),
            prioritize_recency_hours_full=float(os.getenv("PRIORITIZE_RECENCY_HOURS_FULL", "24")),
            prioritize_recency_hours_partial=float(os.getenv("PRIORITIZE_RECENCY_HOURS_PARTIAL", "48")),
            prioritize_recency_partial_score=float(os.getenv("PRIORITIZE_RECENCY_PARTIAL_SCORE", "0.55")),
            prioritize_recency_old_score=float(os.getenv("PRIORITIZE_RECENCY_OLD_SCORE", "0.15")),
            prioritize_recency_unknown_score=float(os.getenv("PRIORITIZE_RECENCY_UNKNOWN_SCORE", "0.40")),
            prioritize_tier1_score=float(os.getenv("PRIORITIZE_TIER1_SCORE", "1.0")),
            prioritize_tier2_high_rep_score=float(os.getenv("PRIORITIZE_TIER2_HIGH_REP_SCORE", "0.60")),
            prioritize_tier2_low_rep_score=float(os.getenv("PRIORITIZE_TIER2_LOW_REP_SCORE", "0.35")),
            prioritize_tier2_rep_threshold=int(os.getenv("PRIORITIZE_TIER2_REP_THRESHOLD", "4")),
            prioritize_embedding_model=os.getenv(
                "PRIORITIZE_EMBEDDING_MODEL",
                "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            ),
            prioritize_embedding_prefix=os.getenv("PRIORITIZE_EMBEDDING_PREFIX", ""),
        )


settings = Settings.from_env()
PROJECT_ROOT = Path(__file__).resolve().parent.parent
MEDIOS_CSV = PROJECT_ROOT / "medios.csv"
EDITORIAL_CRITERIA = PROJECT_ROOT / "editorial_criterios.md"
