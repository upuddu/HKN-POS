"""IMAP email monitor using IDLE for event-driven email detection."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

from imap_tools import MailBox, AND

if TYPE_CHECKING:
    from hkn_pos.config import Config
    from hkn_pos.events import EventBus

from hkn_pos.pdf_parser import PDFParser

logger = logging.getLogger(__name__)


class EmailMonitor:
    """Watches an IMAP mailbox for TooCOOL order confirmation emails.

    Uses IMAP IDLE for near-real-time, event-based detection — no polling.

    Usage::

        monitor = EmailMonitor(config, event_bus)
        monitor.start()  # blocks, fires 'order_received' events
    """

    def __init__(self, config: Config, event_bus: EventBus) -> None:
        self.config = config
        self.bus = event_bus
        self.parser = PDFParser()
        self._running = False

    # ── Public API ─────────────────────────────────────────────────────

    def start(self) -> None:
        """Connect and begin monitoring. Blocks until `stop()` is called."""
        self._running = True
        logger.info(
            "Starting email monitor for %s on %s",
            self.config.email_address,
            self.config.imap_host,
        )

        while self._running:
            try:
                self._monitor_loop()
            except Exception:
                logger.exception("Monitor loop error — reconnecting in 30s")
                self.bus.emit("email_error", "Connection lost, reconnecting…")
                time.sleep(30)

    def stop(self) -> None:
        """Signal the monitor to stop after the current IDLE cycle."""
        self._running = False
        logger.info("Monitor stop requested")

    # ── Internals ──────────────────────────────────────────────────────

    def _monitor_loop(self) -> None:
        """Single connection session with IDLE loop."""
        with MailBox(self.config.imap_host, self.config.imap_port).login(
            self.config.email_address,
            self.config.email_password,
        ) as mailbox:
            logger.info("Connected to %s", self.config.imap_host)

            # Process any existing matching emails first
            self._scan_existing(mailbox)

            # Enter IDLE loop
            while self._running:
                logger.debug("Entering IDLE (timeout=%ds)", self.config.idle_timeout)
                responses = mailbox.idle.wait(timeout=self.config.idle_timeout)

                if responses:
                    logger.debug("IDLE responses: %s", responses)
                    self._scan_new(mailbox)

        logger.info("Disconnected from %s", self.config.imap_host)

    def _scan_existing(self, mailbox: MailBox) -> None:
        """Process already-received matching emails (UNSEEN only)."""
        self._fetch_and_process(mailbox)

    def _scan_new(self, mailbox: MailBox) -> None:
        """Process newly arrived emails after an IDLE notification."""
        self._fetch_and_process(mailbox)

    def _fetch_and_process(self, mailbox: MailBox) -> None:
        """Fetch emails matching our criteria and process them."""
        criteria = AND(
            from_=self.config.target_sender,
            subject=self.config.target_subject,
            seen=False,
        )

        for msg in mailbox.fetch(criteria, mark_seen=True):
            logger.info(
                "Matched email: uid=%s subject='%s' from='%s'",
                msg.uid,
                msg.subject,
                msg.from_,
            )
            self._process_email(msg)

    def _process_email(self, msg) -> None:
        """Check for PDF attachment, download, parse, and emit event."""
        pdf_attachments = [
            att for att in msg.attachments
            if att.content_type == "application/pdf"
            or (att.filename and att.filename.lower().endswith(".pdf"))
        ]

        if not pdf_attachments:
            logger.warning(
                "Email uid=%s matched filters but has no PDF attachment — skipping",
                msg.uid,
            )
            return

        for att in pdf_attachments:
            # Save the PDF
            filename = att.filename or f"order_{msg.uid}.pdf"
            save_path = self.config.download_dir / filename
            save_path.write_bytes(att.payload)
            logger.info("Saved PDF: %s (%d bytes)", save_path, len(att.payload))

            # Parse
            try:
                order = self.parser.parse(save_path)
                self.bus.emit("order_received", order)
            except ValueError as exc:
                logger.warning("PDF didn't match HKN order format: %s", exc)
                self.bus.emit("email_error", str(exc))
            except Exception:
                logger.exception("Failed to parse PDF %s", save_path)
                self.bus.emit("email_error", f"Parse failure: {save_path}")
