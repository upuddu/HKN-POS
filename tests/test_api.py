"""Tests for the FastAPI endpoints."""

import pytest
from fastapi.testclient import TestClient

from hkn_pos.api import create_app
from hkn_pos.config import Config
from hkn_pos.models import OrderData
from hkn_pos.storage import OrderStore
from hkn_pos.webhook import WebhookClient


@pytest.fixture
def config(tmp_path):
    return Config(
        api_passkey="test-secret",
        db_path=tmp_path / "test.db",
    )


@pytest.fixture
def store(config):
    return OrderStore(config.db_path)


@pytest.fixture
def webhook(config, store):
    # No webhook URL → won't fire outbound requests
    return WebhookClient(config, store)


@pytest.fixture
def client(config, store, webhook):
    app = create_app(config, store, webhook)
    return TestClient(app)


@pytest.fixture
def sample_order():
    return OrderData(
        order_number="131376",
        customer_id="jorgenel",
        customer_name="Elijah Luke Jorgensen",
        store_code="02207",
        store_name="ETA KAPPA NU LOUNGE SALES",
    )


class TestHealth:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestGetOrders:
    def test_returns_empty_when_no_orders(self, client):
        resp = client.get("/orders", params={"passkey": "test-secret"})
        assert resp.status_code == 200
        assert resp.json()["orders"] == []
        assert resp.json()["count"] == 0

    def test_returns_orders(self, client, store, sample_order):
        key = store.insert(sample_order)
        resp = client.get("/orders", params={"passkey": "test-secret"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["orders"][0]["key"] == key
        assert data["orders"][0]["data"]["customer_id"] == "jorgenel"

    def test_rejects_bad_passkey(self, client):
        resp = client.get("/orders", params={"passkey": "wrong"})
        assert resp.status_code == 403

    def test_rejects_missing_passkey(self, client):
        resp = client.get("/orders")
        assert resp.status_code == 422  # missing required param


class TestAckOrders:
    def test_ack_cleans_orders(self, client, store, sample_order):
        k1 = store.insert(sample_order)
        k2 = store.insert(sample_order)

        resp = client.post("/orders/ack", json={
            "passkey": "test-secret",
            "received_keys": [k1, k2],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert set(data["cleaned"]) == {k1, k2}
        assert data["remaining"] == 0

    def test_partial_ack(self, client, store, sample_order):
        k1 = store.insert(sample_order)
        k2 = store.insert(sample_order)

        resp = client.post("/orders/ack", json={
            "passkey": "test-secret",
            "received_keys": [k1],
        })
        data = resp.json()
        assert data["cleaned"] == [k1]
        assert data["remaining"] == 1

    def test_ack_rejects_bad_passkey(self, client):
        resp = client.post("/orders/ack", json={
            "passkey": "wrong",
            "received_keys": [],
        })
        assert resp.status_code == 403
