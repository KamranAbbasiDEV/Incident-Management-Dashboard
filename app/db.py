"""SQLite persistence for incidents and their audit timelines.

Database location can be overridden using INCIDENT_DB_PATH. SQL values are
parameterized, and write operations are committed as a single transaction.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import os
import sqlite3


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connection():
    path = Path(os.environ.get("INCIDENT_DB_PATH", "incident_dashboard.db")).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize() -> None:
    with connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                service TEXT NOT NULL,
                severity TEXT NOT NULL CHECK(severity IN ('P1', 'P2', 'P3', 'P4')),
                status TEXT NOT NULL DEFAULT 'open'
                    CHECK(status IN ('open', 'investigating', 'mitigated', 'resolved')),
                owner TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                resolved_at TEXT
            );
            CREATE TABLE IF NOT EXISTS incident_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_id INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
                event_type TEXT NOT NULL,
                detail TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_incidents_status ON incidents(status);
            CREATE INDEX IF NOT EXISTS ix_incidents_severity ON incidents(severity);
            CREATE INDEX IF NOT EXISTS ix_events_incident ON incident_events(incident_id, id);
        """)


def event(conn, incident_id: int, event_type: str, detail: str) -> None:
    conn.execute(
        "INSERT INTO incident_events(incident_id,event_type,detail,created_at) VALUES(?,?,?,?)",
        (incident_id, event_type, detail, utcnow()),
    )


def one(conn, incident_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM incidents WHERE id=?", (incident_id,)).fetchone()
    return dict(row) if row else None
