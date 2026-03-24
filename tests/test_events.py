"""Tests for the EventBus."""

from hkn_pos.events import EventBus


def test_subscribe_and_emit():
    bus = EventBus()
    received = []

    @bus.on("test_event")
    def handler(data):
        received.append(data)

    bus.emit("test_event", "hello")
    assert received == ["hello"]


def test_multiple_handlers():
    bus = EventBus()
    log1, log2 = [], []

    bus.subscribe("ev", lambda d: log1.append(d))
    bus.subscribe("ev", lambda d: log2.append(d))

    bus.emit("ev", 42)
    assert log1 == [42]
    assert log2 == [42]


def test_unsubscribe():
    bus = EventBus()
    calls = []

    def handler(d):
        calls.append(d)

    bus.subscribe("ev", handler)
    bus.emit("ev", 1)
    bus.unsubscribe("ev", handler)
    bus.emit("ev", 2)

    assert calls == [1]


def test_handler_error_does_not_block_others():
    bus = EventBus()
    results = []

    def bad_handler(_):
        raise RuntimeError("boom")

    def good_handler(d):
        results.append(d)

    bus.subscribe("ev", bad_handler)
    bus.subscribe("ev", good_handler)

    bus.emit("ev", "ok")
    assert results == ["ok"]


def test_emit_with_no_handlers():
    bus = EventBus()
    bus.emit("nonexistent", "data")  # should not raise
