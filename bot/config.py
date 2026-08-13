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
    timezone: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
            database_path=os.getenv("DATABASE_PATH", "./data/editorial.db"),
            min_relevance_score=int(os.getenv("MIN_RELEVANCE_SCORE", "3")),
            max_articles_per_informe=int(os.getenv("MAX_ARTICLES_PER_INFORME", "50")),
            timezone=os.getenv("TIMEZONE", "Europe/Madrid"),
        )


settings = Settings.from_env()
PROJECT_ROOT = Path(__file__).resolve().parent.parent
MEDIOS_CSV = PROJECT_ROOT / "medios.csv"
