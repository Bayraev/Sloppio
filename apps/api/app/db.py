"""SQLite connection + tiny versioned migration runner.

Migrations are numbered SQL files in app/migrations/*.sql, applied in order
inside a transaction and tracked in the schema_migrations table.
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from app.config import Settings

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

# Serialize write transactions across threads (budget checks must be atomic).
_write_lock = threading.Lock()


def connect(settings: Settings) -> sqlite3.Connection:
    db_path = settings.resolved_storage_root() / "database" / "studio.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


@contextmanager
def write_tx(conn: sqlite3.Connection):
    """Serialized immediate transaction — safe for check-then-write sequences."""
    with _write_lock:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
        else:
            conn.commit()


def apply_migrations(conn: sqlite3.Connection) -> list[str]:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (datetime('now')))"
    )
    applied = {r["version"] for r in conn.execute("SELECT version FROM schema_migrations")}
    done: list[str] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = path.name
        if version in applied:
            continue
        sql = path.read_text(encoding="utf-8")
        with write_tx(conn):
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_migrations (version) VALUES (?)", (version,)
            )
        done.append(version)
    return done
