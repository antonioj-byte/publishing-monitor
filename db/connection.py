import sqlite3
from pathlib import Path

from bot.config import settings


def get_connection() -> sqlite3.Connection:
    db_path = Path(settings.database_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migrate_schema(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(medios)")}
    if "tier" not in cols:
        conn.execute(
            "ALTER TABLE medios ADD COLUMN tier INTEGER NOT NULL DEFAULT 2 CHECK (tier IN (1, 2))"
        )


def init_schema() -> None:
    schema_path = Path(__file__).parent / "schema.sql"
    with get_connection() as conn:
        conn.executescript(schema_path.read_text(encoding="utf-8"))
        _migrate_schema(conn)
        conn.commit()
