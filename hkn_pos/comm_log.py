"""Communication logger — tracks webhook exchanges with rotation."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MAX_ENTRIES = 100


class CommLog:
    """SQLite-backed communication log with automatic rotation.

    Keeps the last *max_entries* exchange records. Older entries
    are automatically pruned on each write.
    """

    def __init__(
        self,
        db_path: str | Path = "hkn_pos.db",
        max_entries: int = DEFAULT_MAX_ENTRIES,
    ) -> None:
        self.db_path = str(db_path)
        self.max_entries = max_entries
        self._init_db()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS comm_log (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp  TEXT NOT NULL,
                    direction  TEXT NOT NULL,
                    event      TEXT NOT NULL,
                    detail     TEXT,
                    status     TEXT
                )
            """)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    # ── Write ──────────────────────────────────────────────────────────

    def log(
        self,
        direction: str,
        event: str,
        detail: Any = None,
        status: str = "ok",
    ) -> None:
        """Record a communication exchange.

        Args:
            direction: "OUT" (we sent) or "IN" (we received)
            event: Event type, e.g. "interrupt", "query", "ack"
            detail: Any JSON-serializable detail payload
            status: "ok", "error", "timeout", etc.
        """
        detail_json = json.dumps(detail) if detail is not None else None
        ts = datetime.now().isoformat(timespec="seconds")

        with self._connect() as conn:
            conn.execute(
                "INSERT INTO comm_log (timestamp, direction, event, detail, status) "
                "VALUES (?, ?, ?, ?, ?)",
                (ts, direction, event, detail_json, status),
            )
            # Rotate: keep only the last N entries
            conn.execute(
                "DELETE FROM comm_log WHERE id NOT IN "
                "(SELECT id FROM comm_log ORDER BY id DESC LIMIT ?)",
                (self.max_entries,),
            )
            conn.commit()

        logger.debug("CommLog: %s %s %s", direction, event, status)

    # ── Read ───────────────────────────────────────────────────────────

    def get_all(self) -> list[dict[str, Any]]:
        """Return all log entries, oldest first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, timestamp, direction, event, detail, status "
                "FROM comm_log ORDER BY id ASC"
            ).fetchall()
        return [
            {
                "id": r[0],
                "timestamp": r[1],
                "direction": r[2],
                "event": r[3],
                "detail": json.loads(r[4]) if r[4] else None,
                "status": r[5],
            }
            for r in rows
        ]

    def get_recent(self, n: int = 20) -> list[dict[str, Any]]:
        """Return the most recent *n* entries."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, timestamp, direction, event, detail, status "
                "FROM comm_log ORDER BY id DESC LIMIT ?",
                (n,),
            ).fetchall()
        entries = [
            {
                "id": r[0],
                "timestamp": r[1],
                "direction": r[2],
                "event": r[3],
                "detail": json.loads(r[4]) if r[4] else None,
                "status": r[5],
            }
            for r in rows
        ]
        return list(reversed(entries))  # oldest first

    def count(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM comm_log").fetchone()[0]

    def clear(self) -> int:
        with self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM comm_log").fetchone()[0]
            conn.execute("DELETE FROM comm_log")
            conn.commit()
        return count
