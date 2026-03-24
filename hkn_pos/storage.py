"""SQLite-backed storage for parsed orders."""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

from hkn_pos.models import OrderData

logger = logging.getLogger(__name__)


def _order_to_dict(order: OrderData) -> dict[str, Any]:
    """Serialize an OrderData to a JSON-safe dict."""
    return {
        "order_number": order.order_number,
        "order_date": order.order_date,
        "customer_id": order.customer_id,
        "customer_name": order.customer_name,
        "store_code": order.store_code,
        "store_name": order.store_name,
        "reload_amount": str(order.reload_amount),
        "subtotal": str(order.subtotal),
        "shipping": str(order.shipping_total),
        "sales_tax": str(order.sales_tax_total),
        "total": str(order.total),
        "paid": order.paid,
        "pickup_location": order.pickup_location,
        "ship_to_address": order.ship_to_address,
        "source_pdf": order.source_pdf,
    }


class OrderStore:
    """Simple SQLite store for parsed orders.

    Each order gets a UUID key and a status (unread / acked).
    """

    def __init__(self, db_path: str | Path = "hkn_pos.db") -> None:
        self.db_path = str(db_path)
        self._init_db()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    key        TEXT PRIMARY KEY,
                    data       TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    # ── Write ──────────────────────────────────────────────────────────

    def insert(self, order: OrderData) -> str:
        """Store an order and return its UUID key."""
        key = uuid.uuid4().hex
        data_json = json.dumps(_order_to_dict(order))
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO orders (key, data) VALUES (?, ?)",
                (key, data_json),
            )
            conn.commit()
        logger.info("Stored order %s with key %s", order.order_number, key)
        return key

    # ── Read ───────────────────────────────────────────────────────────

    def get_unread(self) -> list[dict[str, Any]]:
        """Return all orders currently in the store.

        Returns a list of ``{"key": "...", "data": {...}}`` dicts.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT key, data FROM orders ORDER BY created_at"
            ).fetchall()
        return [{"key": row[0], "data": json.loads(row[1])} for row in rows]

    def get_unread_keys(self) -> list[str]:
        """Return just the keys of all unread orders."""
        with self._connect() as conn:
            rows = conn.execute("SELECT key FROM orders ORDER BY created_at").fetchall()
        return [row[0] for row in rows]

    def count(self) -> int:
        """Return the number of orders in the store."""
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]

    # ── ACK / cleanup ──────────────────────────────────────────────────

    def ack(self, keys: list[str]) -> list[str]:
        """Delete orders matching *keys*. Return the keys that were actually deleted."""
        if not keys:
            return []
        with self._connect() as conn:
            # Find which keys actually exist
            placeholders = ",".join("?" * len(keys))
            existing = conn.execute(
                f"SELECT key FROM orders WHERE key IN ({placeholders})", keys
            ).fetchall()
            existing_keys = [row[0] for row in existing]

            if existing_keys:
                placeholders = ",".join("?" * len(existing_keys))
                conn.execute(
                    f"DELETE FROM orders WHERE key IN ({placeholders})",
                    existing_keys,
                )
                conn.commit()
                logger.info("ACK'd and cleaned %d orders: %s", len(existing_keys), existing_keys)

        return existing_keys

    def clear(self) -> int:
        """Delete all orders. Returns count deleted."""
        with self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
            conn.execute("DELETE FROM orders")
            conn.commit()
        return count
