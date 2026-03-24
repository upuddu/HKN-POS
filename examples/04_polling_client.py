#!/usr/bin/env python3
"""
Example 4: Polling client — no webhook required.

Use this when your client can't receive inbound connections
(e.g., behind a NAT/firewall, serverless functions, cron jobs).

Instead of waiting for an interrupt, it periodically polls the
HKN POS API for unread orders and ACKs them.

Usage:
    pip install requests
    export HKN_API=http://localhost:8042
    export PASSKEY=test123
    python 04_polling_client.py

Optional env:
    POLL_INTERVAL=10    Seconds between polls (default: 10)
"""

import logging
import os
import time

import requests

# ── Configuration ─────────────────────────────────────────────────

HKN_API = os.getenv("HKN_API", "http://localhost:8042")
PASSKEY = os.getenv("PASSKEY", "test123")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "10"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("hkn_poller")


# ── Order processing ──────────────────────────────────────────────

def process_order(key: str, data: dict) -> bool:
    """Process a single order. Return True if successfully handled."""
    log.info(
        "  📦 Order #%s | %s (%s) | $%s | Paid: %s",
        data["order_number"],
        data["customer_name"],
        data["customer_id"],
        data["total"],
        data["paid"],
    )
    return True


# ── Poll loop ─────────────────────────────────────────────────────

def poll_once() -> int:
    """Query the API once, process orders, and ACK.

    Returns the number of orders processed.
    """
    try:
        # Step 1: Query
        resp = requests.get(
            f"{HKN_API}/orders",
            params={"passkey": PASSKEY},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        orders = data["orders"]
        if not orders:
            return 0

        log.info("📬 Found %d unread order(s):", len(orders))

        # Step 2: Process
        acked_keys = []
        for order in orders:
            if process_order(order["key"], order["data"]):
                acked_keys.append(order["key"])

        # Step 3: ACK
        if acked_keys:
            ack_resp = requests.post(
                f"{HKN_API}/orders/ack",
                json={"passkey": PASSKEY, "received_keys": acked_keys},
                timeout=10,
            )
            ack_resp.raise_for_status()
            result = ack_resp.json()
            log.info(
                "✅ ACK'd: cleaned=%d remaining=%d",
                len(result["cleaned"]),
                result["remaining"],
            )

        return len(acked_keys)

    except requests.RequestException as e:
        log.error("❌ Request failed: %s", e)
        return 0


def main():
    log.info("╔══════════════════════════════════════╗")
    log.info("║  HKN POS — Polling Client Example     ║")
    log.info("╚══════════════════════════════════════╝")
    log.info("  HKN API:       %s", HKN_API)
    log.info("  Passkey:       %s", PASSKEY[:4] + "***")
    log.info("  Poll interval: %ds", POLL_INTERVAL)
    log.info("")
    log.info("🔄 Polling started (Ctrl+C to stop)...")
    log.info("")

    total_processed = 0
    try:
        while True:
            count = poll_once()
            total_processed += count
            if count:
                log.info("📊 Session total: %d orders processed", total_processed)
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        log.info("\nStopped. Total orders processed: %d", total_processed)


if __name__ == "__main__":
    main()
