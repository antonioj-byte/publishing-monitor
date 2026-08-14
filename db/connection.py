import sqlite3
from pathlib import Path

from bot.config import settings


def get_connection() -> sqlite3.Connection:
    db_path = Path(settings.database_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def _migrate_schema(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(medios)")}
    if "tier" not in cols:
        conn.execute(
            "ALTER TABLE medios ADD COLUMN tier INTEGER NOT NULL DEFAULT 2 CHECK (tier IN (1, 2))"
        )
    if "pais" not in cols:
        conn.execute(
            "ALTER TABLE medios ADD COLUMN pais TEXT NOT NULL DEFAULT 'xx'"
        )

    art_cols = {row[1] for row in conn.execute("PRAGMA table_info(articulos)")}
    if "tags" not in art_cols:
        conn.execute("ALTER TABLE articulos ADD COLUMN tags TEXT")

    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    if "informe_sesiones" not in tables:
        conn.execute(
            """
            CREATE TABLE informe_sesiones (
                chat_id TEXT PRIMARY KEY,
                mode TEXT NOT NULL,
                since_iso TEXT NOT NULL,
                include_sent INTEGER NOT NULL DEFAULT 0,
                report_filter TEXT,
                article_ids TEXT NOT NULL,
                cursor INTEGER NOT NULL DEFAULT 0,
                trends_included INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )


def init_schema() -> None:
    schema_path = Path(__file__).parent / "schema.sql"
    with get_connection() as conn:
        conn.executescript(schema_path.read_text(encoding="utf-8"))
        _migrate_schema(conn)
        conn.commit()
