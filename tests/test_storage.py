"""Tests for the SQLite storage layer."""

import json

import pytest

from hkn_pos.models import OrderData
from hkn_pos.storage import OrderStore


@pytest.fixture
def store(tmp_path):
    return OrderStore(tmp_path / "test.db")


@pytest.fixture
def sample_order():
    return OrderData(
        order_number="131376",
        order_date="15 Sep 2025",
        customer_id="jorgenel",
        customer_name="Elijah Luke Jorgensen",
        store_code="02207",
        store_name="ETA KAPPA NU LOUNGE SALES",
    )


class TestOrderStore:
    def test_insert_returns_key(self, store, sample_order):
        key = store.insert(sample_order)
        assert isinstance(key, str)
        assert len(key) == 32  # UUID hex

    def test_get_unread(self, store, sample_order):
        key = store.insert(sample_order)
        unread = store.get_unread()
        assert len(unread) == 1
        assert unread[0]["key"] == key
        assert unread[0]["data"]["order_number"] == "131376"
        assert unread[0]["data"]["customer_id"] == "jorgenel"

    def test_count(self, store, sample_order):
        assert store.count() == 0
        store.insert(sample_order)
        assert store.count() == 1
        store.insert(sample_order)
        assert store.count() == 2

    def test_ack_deletes_matched(self, store, sample_order):
        k1 = store.insert(sample_order)
        k2 = store.insert(sample_order)
        cleaned = store.ack([k1])
        assert cleaned == [k1]
        assert store.count() == 1

    def test_ack_all(self, store, sample_order):
        k1 = store.insert(sample_order)
        k2 = store.insert(sample_order)
        cleaned = store.ack([k1, k2])
        assert set(cleaned) == {k1, k2}
        assert store.count() == 0

    def test_ack_nonexistent_key(self, store, sample_order):
        store.insert(sample_order)
        cleaned = store.ack(["nonexistent"])
        assert cleaned == []
        assert store.count() == 1

    def test_ack_empty_list(self, store):
        assert store.ack([]) == []

    def test_get_unread_keys(self, store, sample_order):
        k1 = store.insert(sample_order)
        k2 = store.insert(sample_order)
        assert set(store.get_unread_keys()) == {k1, k2}

    def test_clear(self, store, sample_order):
        store.insert(sample_order)
        store.insert(sample_order)
        deleted = store.clear()
        assert deleted == 2
        assert store.count() == 0
