#!/usr/bin/env python3
"""
Example 2: Synchronous Python client using Flask + requests.

This client:
  1. Runs a Flask server that listens for interrupt webhooks
  2. On interrupt → queries the HKN POS API for unread orders
  3. Processes each order (prints it, but you'd save to your DB)
  4. ACKs the received keys so they're cleaned from HKN POS

Usage:
    pip install flask requests
    export HKN_API=http://localhost:8042
    export PASSKEY=test123
    python 02_flask_client.py

The webhook endpoint will be: http://localhost:9000/webhook/order
Set WEBHOOK_URL=http://localhost:9000/webhook/order in HKN POS .env
"""

import json
import logging
import os
import threading

import requests
from flask import Flask, request, jsonify

# ── Configuration ─────────────────────────────────────────────────

HKN_API = os.getenv("HKN_API", "http://localhost:8042")
PASSKEY = os.getenv("PASSKEY", "test123")
LISTEN_PORT = int(os.getenv("LISTEN_PORT", "9000"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("hkn_client")

app = Flask(__name__)


# ── Order processing ──────────────────────────────────────────────

def process_order(key: str, data: dict) -> bool:
    """Process a single order. Return True if successfully handled.

    This is where you'd save to YOUR database, notify users, etc.
    """
    log.info(
        "  📦 Order #%s | %s (%s) | $%s | Paid: %s",
        data["order_number"],
        data["customer_name"],
        data["customer_id"],
        data["total"],
        data["paid"],
    )
    # Simulate your business logic here
    # e.g., save_to_database(data)
    return True


def fetch_and_ack_orders():
    """Query all unread orders from HKN POS, process them, and ACK."""
    try:
        # ── Step 1: Query ──────────────────────────────────────────
        log.info("🔍 Querying orders from %s", HKN_API)
        resp = requests.get(
            f"{HKN_API}/orders",
            params={"passkey": PASSKEY},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        orders = data["orders"]
        if not orders:
            log.info("   No unread orders")
            return

        log.info("📬 Received %d order(s):", len(orders))

        # ── Step 2: Process each order ─────────────────────────────
        acked_keys = []
        for order in orders:
            key = order["key"]
            success = process_order(key, order["data"])
            if success:
                acked_keys.append(key)

        # ── Step 3: ACK the successfully processed keys ────────────
        if acked_keys:
            log.info("📤 ACK'ing %d key(s)...", len(acked_keys))
            ack_resp = requests.post(
                f"{HKN_API}/orders/ack",
                json={"passkey": PASSKEY, "received_keys": acked_keys},
                timeout=10,
            )
            ack_resp.raise_for_status()
            result = ack_resp.json()
            log.info(
                "✅ ACK result: cleaned=%d remaining=%d",
                len(result["cleaned"]),
                result["remaining"],
            )
        else:
            log.warning("⚠️  No orders processed successfully — not ACK'ing")

    except requests.RequestException as e:
        log.error("❌ API request failed: %s", e)


# ── Webhook endpoint ──────────────────────────────────────────────

@app.route("/webhook/order", methods=["POST"])
def webhook_order():
    """Receive interrupt from HKN POS server.

    The server POSTs {"order_ids": ["key1", ...]} when new orders
    are available. We respond immediately, then fetch and ACK in
    a background thread so we don't block the webhook response.
    """
    payload = request.get_json(silent=True) or {}
    order_ids = payload.get("order_ids", [])
    log.info("🔔 INTERRUPT received with %d order ID(s)", len(order_ids))

    # Process in background — don't block the webhook response
    thread = threading.Thread(target=fetch_and_ack_orders, daemon=True)
    thread.start()

    return jsonify({"status": "received"}), 200


# ── Health endpoint (optional) ────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({"status": "ok", "client": "flask_sync"})


# ── Main ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    log.info("╔══════════════════════════════════════╗")
    log.info("║  HKN POS — Flask Client Example       ║")
    log.info("╚══════════════════════════════════════╝")
    log.info("  HKN API:  %s", HKN_API)
    log.info("  Passkey:  %s", PASSKEY[:4] + "***")
    log.info("  Webhook:  http://localhost:%d/webhook/order", LISTEN_PORT)
    log.info("")

    app.run(host="0.0.0.0", port=LISTEN_PORT, debug=False)
