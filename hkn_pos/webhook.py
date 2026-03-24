"""Webhook client — sends interrupt notifications to an external server."""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from hkn_pos.comm_log import CommLog
    from hkn_pos.config import Config
    from hkn_pos.storage import OrderStore

logger = logging.getLogger(__name__)


class WebhookClient:
    """Fires interrupt POSTs to an external server when new orders arrive.

    If the external server doesn't ACK (or only partially ACKs) within
    ``ack_timeout`` seconds, the interrupt is re-fired with the remaining
    unread order keys.
    """

    def __init__(
        self,
        config: Config,
        store: OrderStore,
        comm_log: CommLog | None = None,
    ) -> None:
        self.url = config.webhook_url
        self.ack_timeout = config.ack_timeout
        self.store = store
        self.comm_log = comm_log
        self._pending_timer: threading.Timer | None = None

    # ── Public API ─────────────────────────────────────────────────────

    def notify(self, order_keys: list[str]) -> None:
        """Send an interrupt POST and schedule an ACK check."""
        if not self.url:
            logger.debug("No WEBHOOK_URL configured — skipping interrupt")
            return

        payload = {"order_ids": order_keys}
        try:
            resp = httpx.post(self.url, json=payload, timeout=10)
            logger.info(
                "Interrupt sent to %s → %s (keys: %s)",
                self.url, resp.status_code, order_keys,
            )
            self._log("OUT", "interrupt", payload, "ok")
        except httpx.HTTPError as exc:
            logger.warning("Failed to send interrupt to %s — will retry", self.url)
            self._log("OUT", "interrupt", payload, f"error: {exc}")

        # Schedule a follow-up: if unread keys remain after ack_timeout,
        # re-fire the interrupt
        self._schedule_retry()

    def on_ack_received(self, acked_keys: list[str]) -> None:
        """Called when the external server ACKs some keys.

        If all unread keys are now ACK'd, cancel the pending retry.
        Otherwise the scheduled retry will re-fire with what's left.
        """
        remaining = self.store.get_unread_keys()
        if not remaining:
            self._cancel_retry()
            logger.info("All orders ACK'd — no retry needed")
            self._log("IN", "ack_complete", {"acked": acked_keys}, "ok")
        else:
            logger.info(
                "%d orders still unread after ACK — retry will fire",
                len(remaining),
            )
            self._log(
                "IN", "ack_partial",
                {"acked": acked_keys, "remaining": remaining},
                "pending_retry",
            )

    # ── Retry logic ────────────────────────────────────────────────────

    def _schedule_retry(self) -> None:
        """Schedule a re-fire if unread orders still exist after timeout."""
        self._cancel_retry()
        self._pending_timer = threading.Timer(
            self.ack_timeout, self._retry_if_unread
        )
        self._pending_timer.daemon = True
        self._pending_timer.start()
        logger.debug("ACK retry scheduled in %ds", self.ack_timeout)

    def _cancel_retry(self) -> None:
        if self._pending_timer is not None:
            self._pending_timer.cancel()
            self._pending_timer = None

    def _retry_if_unread(self) -> None:
        """Re-fire interrupt if there are still unread orders."""
        remaining = self.store.get_unread_keys()
        if remaining:
            logger.warning(
                "ACK timeout — %d orders still unread, re-firing interrupt",
                len(remaining),
            )
            self._log("OUT", "retry_interrupt", {"keys": remaining}, "timeout")
            self.notify(remaining)
        else:
            logger.debug("ACK timeout — all orders already ACK'd, no retry")

    # ── Logging helper ─────────────────────────────────────────────────

    def _log(self, direction: str, event: str, detail, status: str) -> None:
        if self.comm_log:
            self.comm_log.log(direction, event, detail, status)
