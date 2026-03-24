"""Entry point for the HKN POS email monitor & API server."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
from decimal import Decimal
from pathlib import Path

from hkn_pos.config import Config
from hkn_pos.comm_log import CommLog
from hkn_pos.events import EventBus
from hkn_pos.models import OrderData
from hkn_pos.pdf_parser import PDFParser
from hkn_pos.storage import OrderStore
from hkn_pos.webhook import WebhookClient


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


# ── Default event handlers ─────────────────────────────────────────────

def _log_order(order: OrderData) -> None:
    logging.getLogger("hkn_pos").info("✅  %s", order.summary())


def _json_order(order: OrderData) -> None:
    data = {
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
    print(json.dumps(data, indent=2))


# ── CLI ─────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="hkn-pos",
        description="HKN POS — Monitor emails, parse TooCOOL PDFs, and serve an API",
    )
    p.add_argument(
        "--parse-pdf", type=Path, metavar="FILE",
        help="Parse a single PDF and store (or print) the result",
    )
    p.add_argument(
        "--json", action="store_true",
        help="Output parsed data as JSON (for --parse-pdf)",
    )
    p.add_argument(
        "--serve", action="store_true",
        help="Start the API server (also starts email monitor if credentials exist)",
    )
    p.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable debug logging",
    )
    p.add_argument(
        "--env", type=Path, default=None,
        help="Path to .env file (default: .env in current directory)",
    )
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    _setup_logging(args.verbose)

    config = Config.from_env(args.env)
    store = OrderStore(config.db_path)
    comm_log = CommLog(config.db_path)
    webhook = WebhookClient(config, store, comm_log)
    bus = EventBus()

    # ── Handler: store order + fire webhook interrupt ──────────────
    def _store_and_notify(order: OrderData) -> None:
        key = store.insert(order)
        webhook.notify([key])

    bus.subscribe("order_received", _log_order)
    bus.subscribe("order_received", _store_and_notify)

    if args.json:
        bus.subscribe("order_received", _json_order)

    # ── Mode 1: Parse a single PDF ─────────────────────────────────
    if args.parse_pdf:
        parser = PDFParser()
        order = parser.parse(args.parse_pdf)
        bus.emit("order_received", order)
        if not args.serve:
            return

    # ── Mode 2: Serve API (+ optionally monitor email) ─────────────
    if args.serve:
        _run_server(config, store, webhook, bus, comm_log)
        return

    # ── Mode 3 (legacy): Monitor email only ────────────────────────
    if config.email_address and config.email_password:
        from hkn_pos.email_monitor import EmailMonitor

        bus.subscribe(
            "email_error",
            lambda msg: logging.getLogger("hkn_pos").error("❌  %s", msg),
        )
        monitor = EmailMonitor(config, bus)
        try:
            monitor.start()
        except KeyboardInterrupt:
            monitor.stop()
            print("\nStopped.")
        return

    # No mode selected — show help
    print(
        "Usage:\n"
        "  hkn-pos --parse-pdf <file>        Parse a single PDF\n"
        "  hkn-pos --serve                    Start API server + email monitor\n"
        "  hkn-pos --parse-pdf <f> --serve    Parse PDF, store, then start server\n"
        "\nSet EMAIL_ADDRESS + EMAIL_PASSWORD in .env for email monitoring.",
        file=sys.stderr,
    )


def _run_server(config, store, webhook, bus, comm_log) -> None:
    """Start the FastAPI server with optional email monitor in background."""
    import uvicorn
    from hkn_pos.api import create_app

    app = create_app(config, store, webhook, comm_log)
    logger = logging.getLogger("hkn_pos")

    # Start email monitor in a background thread if credentials exist
    if config.email_address and config.email_password:
        from hkn_pos.email_monitor import EmailMonitor

        bus.subscribe(
            "email_error",
            lambda msg: logger.error("❌  %s", msg),
        )
        monitor = EmailMonitor(config, bus)
        monitor_thread = threading.Thread(
            target=monitor.start, name="email-monitor", daemon=True
        )
        monitor_thread.start()
        logger.info("Email monitor started in background thread")
    else:
        logger.warning(
            "No email credentials — API server only (no email monitoring)"
        )

    logger.info("Starting API server on port %d", config.api_port)
    uvicorn.run(app, host="0.0.0.0", port=config.api_port, log_level="info")


if __name__ == "__main__":
    main()
