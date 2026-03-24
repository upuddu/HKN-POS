#!/usr/bin/env python3
"""
Example 3: Async Python client using FastAPI + httpx.

Higher performance than the Flask example — uses async/await for
non-blocking I/O, ideal for servers handling many concurrent requests.

This client:
  1. Runs a FastAPI server that listens for interrupt webhooks
  2. On interrupt → async queries HKN POS API for unread orders
  3. Processes each order concurrently
  4. ACKs the received keys

Usage:
    pip install fastapi uvicorn httpx
    export HKN_API=http://localhost:8042
    export PASSKEY=test123
    python 03_async_client.py

The webhook endpoint will be: http://localhost:9000/webhook/order
"""

import asyncio
import logging
import os

import httpx
import uvicorn
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel

# ── Configuration ─────────────────────────────────────────────────

HKN_API = os.getenv("HKN_API", "http://localhost:8042")
PASSKEY = os.getenv("PASSKEY", "test123")
LISTEN_PORT = int(os.getenv("LISTEN_PORT", "9000"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("hkn_async_client")

app = FastAPI(title="HKN POS Async Client", version="0.1.0")


# ── Models ────────────────────────────────────────────────────────

class InterruptPayload(BaseModel):
    order_ids: list[str] = []


# ── Order processing ──────────────────────────────────────────────

async def process_order(key: str, data: dict) -> bool:
    """Process a single order asynchronously.

    Replace this with your actual business logic:
    save to DB, send notification, update inventory, etc.
    """
    log.info(
        "  📦 Order #%s | %s (%s) | $%s",
        data["order_number"],
        data["customer_name"],
        data["customer_id"],
        data["total"],
    )
    # Simulate some async processing (e.g., DB write)
    await asyncio.sleep(0.01)
    return True


async def fetch_and_ack_orders():
    """Query all unread orders, process them, and ACK — all async."""
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            # ── Step 1: Query ──────────────────────────────────────
            log.info("🔍 Querying orders from %s", HKN_API)
            resp = await client.get(
                f"{HKN_API}/orders",
                params={"passkey": PASSKEY},
            )
            resp.raise_for_status()
            data = resp.json()

            orders = data["orders"]
            if not orders:
                log.info("   No unread orders")
                return

            log.info("📬 Received %d order(s):", len(orders))

            # ── Step 2: Process all orders concurrently ────────────
            results = await asyncio.gather(*[
                process_order(o["key"], o["data"]) for o in orders
            ])

            acked_keys = [
                orders[i]["key"]
                for i, ok in enumerate(results)
                if ok
            ]

            # ── Step 3: ACK ────────────────────────────────────────
            if acked_keys:
                log.info("📤 ACK'ing %d key(s)...", len(acked_keys))
                ack_resp = await client.post(
                    f"{HKN_API}/orders/ack",
                    json={
                        "passkey": PASSKEY,
                        "received_keys": acked_keys,
                    },
                )
                ack_resp.raise_for_status()
                result = ack_resp.json()
                log.info(
                    "✅ ACK result: cleaned=%d remaining=%d",
                    len(result["cleaned"]),
                    result["remaining"],
                )

        except httpx.HTTPError as e:
            log.error("❌ API request failed: %s", e)


# ── Webhook endpoint ──────────────────────────────────────────────

@app.post("/webhook/order")
async def webhook_order(
    payload: InterruptPayload,
    background_tasks: BackgroundTasks,
):
    """Receive interrupt webhook from HKN POS.

    Uses FastAPI's BackgroundTasks to process the orders after
    returning the response — keeping the webhook response fast.
    """
    log.info("🔔 INTERRUPT received with %d order ID(s)", len(payload.order_ids))

    # Schedule the fetch-and-ACK as a background task
    background_tasks.add_task(fetch_and_ack_orders)

    return {"status": "received"}


@app.get("/health")
async def health():
    return {"status": "ok", "client": "fastapi_async"}


# ── Main ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    log.info("╔══════════════════════════════════════╗")
    log.info("║  HKN POS — Async Client Example       ║")
    log.info("╚══════════════════════════════════════╝")
    log.info("  HKN API:  %s", HKN_API)
    log.info("  Passkey:  %s", PASSKEY[:4] + "***")
    log.info("  Webhook:  http://localhost:%d/webhook/order", LISTEN_PORT)
    log.info("")

    uvicorn.run(app, host="0.0.0.0", port=LISTEN_PORT, log_level="warning")
