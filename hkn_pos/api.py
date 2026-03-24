"""FastAPI server exposing the order query and ACK endpoints."""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

if TYPE_CHECKING:
    from hkn_pos.comm_log import CommLog

logger = logging.getLogger(__name__)

# ── Request / response models ─────────────────────────────────────────

class AckRequest(BaseModel):
    passkey: str
    received_keys: list[str]


class AckResponse(BaseModel):
    status: str
    cleaned: list[str]
    remaining: int


class OrdersResponse(BaseModel):
    orders: list[dict[str, Any]]
    count: int


# ── App factory ────────────────────────────────────────────────────────

def create_app(config, store, webhook_client, comm_log: CommLog | None = None) -> FastAPI:
    """Create and return the FastAPI application."""
    app = FastAPI(title="HKN POS API", version="0.1.0")

    def _verify_passkey(passkey: str) -> None:
        if not config.api_passkey:
            raise HTTPException(
                status_code=500,
                detail="API_PASSKEY not configured on server",
            )
        if passkey != config.api_passkey:
            raise HTTPException(status_code=403, detail="Invalid passkey")

    # ── GET /orders ────────────────────────────────────────────────

    @app.get("/orders", response_model=OrdersResponse)
    def get_orders(passkey: str = Query(..., description="Shared secret")):
        """Return all unread orders."""
        _verify_passkey(passkey)
        orders = store.get_unread()
        logger.info("Served %d unread orders", len(orders))
        if comm_log:
            comm_log.log("IN", "query", {"count": len(orders)}, "ok")
        return OrdersResponse(orders=orders, count=len(orders))

    # ── POST /orders/ack ───────────────────────────────────────────

    @app.post("/orders/ack", response_model=AckResponse)
    def ack_orders(req: AckRequest):
        """ACK received order keys — matched orders are cleaned from DB."""
        _verify_passkey(req.passkey)

        cleaned = store.ack(req.received_keys)
        remaining = store.count()

        logger.info(
            "ACK received: cleaned=%s remaining=%d", cleaned, remaining,
        )
        if comm_log:
            comm_log.log("IN", "ack", {
                "received_keys": req.received_keys,
                "cleaned": cleaned,
                "remaining": remaining,
            }, "ok")

        # Let the webhook client know about the ACK
        webhook_client.on_ack_received(cleaned)

        return AckResponse(
            status="ok",
            cleaned=cleaned,
            remaining=remaining,
        )

    # ── GET /health ────────────────────────────────────────────────

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "unread_orders": store.count(),
        }

    return app
