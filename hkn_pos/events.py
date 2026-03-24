"""Lightweight event bus for decoupled order processing."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Type alias for event handler callbacks
Handler = Callable[..., Any]


class EventBus:
    """
    Simple publish/subscribe event system.

    Usage::

        bus = EventBus()

        @bus.on("order_received")
        def handle_order(order_data):
            print(order_data.summary())

        bus.emit("order_received", order_data)
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)

    # -- Registration ---------------------------------------------------

    def on(self, event: str) -> Callable[[Handler], Handler]:
        """Decorator to subscribe a handler to an event.

        Can also be used as a plain method::

            bus.on("order_received")(my_handler)
        """

        def decorator(fn: Handler) -> Handler:
            self.subscribe(event, fn)
            return fn

        return decorator

    def subscribe(self, event: str, handler: Handler) -> None:
        """Register *handler* for *event*."""
        self._handlers[event].append(handler)
        logger.debug("Subscribed %s to '%s'", handler.__name__, event)

    def unsubscribe(self, event: str, handler: Handler) -> None:
        """Remove *handler* from *event*."""
        try:
            self._handlers[event].remove(handler)
        except ValueError:
            pass

    # -- Emission -------------------------------------------------------

    def emit(self, event: str, *args: Any, **kwargs: Any) -> None:
        """Fire *event*, calling every registered handler in order.

        If a handler raises, the exception is logged but remaining
        handlers still execute (fail-open).
        """
        handlers = self._handlers.get(event, [])
        if not handlers:
            logger.debug("Event '%s' emitted with no handlers", event)
            return

        for handler in handlers:
            try:
                handler(*args, **kwargs)
            except Exception:
                logger.exception(
                    "Handler %s raised on event '%s'",
                    handler.__name__,
                    event,
                )
