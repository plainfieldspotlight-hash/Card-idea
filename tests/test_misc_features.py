"""Rates, auth, collection import, deals, report endpoint, pricecharting."""
import base64

import pytest
from fastapi.testclient import TestClient

from pokeprice import db, demo, model, pricecharting, rates
from pokeprice.web.app import create_app


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "misc.db"
    c = db.connect(db_path)
    demo.seed(c, n_cards=10, days=30)
    model.predict(c, model_file=tmp_path / "none.joblib")
    c.close()
    return TestClient(create_app(db_path=db_path))


def test_rates_cached_and_offline_fallback(conn, monkeypatch):
    calls = []

    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"rates": {"USD": 1.10}}

    monkeypatch.setattr(rates.requests, "get",
                        lambda *a, **k: calls.append(1) or FakeResp())
    assert rates.eur_usd(conn) == 1.10
    assert rates.eur_usd(conn) == 1.10
    assert len(calls) == 1  # second call served from meta cache
    assert rates.to_usd(conn, 100.0, "EUR") == pytest.approx(110.0)
    assert rates.to_usd(conn, 100.0, "USD") == 100.0
    assert rates.to_usd(conn, None, "EUR") is None


def test_rates_offline_without_cache(tmp_path, monkeypatch):
    fresh = db.connect(tmp_path / "fx.db")

    def boom(*a, **k):
        raise OSError("offline")

    monkeypatch.setattr(rates.requests, "get", boom)
    assert rates.eur_usd(fresh) == rates.STATIC_FALLBACK["EUR"]


def test_basic_auth(client, monkeypatch):
    monkeypatch.setenv("POKEPRICE_PASSWORD", "sekrit")
    assert client.get("/api/stats").status_code == 401
    header = "Basic " + base64.b64encode(b"user:sekrit").decode()
    assert client.get("/api/stats", headers={"Authorization": header}).status_code == 200
    bad = "Basic " + base64.b64encode(b"user:wrong").decode()
    assert client.get("/api/stats", headers={"Authorization": bad}).status_code == 401
    monkeypatch.delenv("POKEPRICE_PASSWORD")
    assert client.get("/api/stats").status_code == 200


def test_collection_import(client):
    items = client.get("/api/cards", params={"limit": 20, "min_price": 0}).json()["items"]
    by_name = {}
    for item in items:  # the same card can appear as several listings; dedupe
        by_name.setdefault(item["name"], item)
    known = list(by_name.values())[:2]
    csv_text = (
        "Card Name,Set,Quantity,Price Paid\n"
        f"{known[0]['name']},{known[0]['set_name']},3,$2.50\n"
        f"{known[1]['name']},{known[1]['set_name']},1,\n"
        "Totally Fake Card,Nowhere Set,1,9.99\n"
    )
    resp = client.post("/api/collection/import", content=csv_text,
                       headers={"Content-Type": "text/csv"})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["imported"] == 2
    assert payload["unmatched"] == ["Totally Fake Card"]
    holdings = client.get("/api/collection").json()["holdings"]
    assert len(holdings) == 2
    imported = {h["name"]: h for h in holdings}
    assert imported[known[0]["name"]]["quantity"] == 3
    assert imported[known[0]["name"]]["cost_basis"] == 2.50


def test_report_endpoint_shape(client):
    payload = client.get("/api/report").json()
    assert "overall" in payload and "by_tier" in payload
    assert payload["overall"]["n"] >= 0
    assert "backtest" in payload  # None until a backtest runs


def test_deals_link_mode(client, monkeypatch):
    monkeypatch.delenv("EBAY_CLIENT_ID", raising=False)
    payload = client.get("/api/deals", params={"min_prob": 0.0, "min_return": -1.0}).json()
    assert payload["mode"] == "link"
    assert payload["deals"]
    for deal in payload["deals"]:
        assert deal["ebay_url"].startswith("https://www.ebay.com/sch/")
        assert deal["best_listing"] is None


def test_pricecharting_fetch(conn, monkeypatch):
    demo.seed(conn, n_cards=3, days=5)
    card = conn.execute("SELECT card_id FROM cards LIMIT 1").fetchone()

    class FakeResp:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class FakeSession:
        def get(self, url, params=None, timeout=None):
            if url.endswith("/products"):
                return FakeResp({"products": [
                    {"id": 999, "product-name": "Charizard #4",
                     "console-name": "Pokemon Base Set"},
                ]})
            return FakeResp({"product-name": "Charizard #4",
                             "loose-price": 25000, "graded-price": 90000,
                             "manual-only-price": 420000})

    monkeypatch.setenv("PRICECHARTING_TOKEN", "tok")
    result = pricecharting.fetch_graded(conn, card["card_id"], query="charizard",
                                        session=FakeSession())
    assert result["matched"] == "Charizard #4"
    assert result["snapshots"] == 3
    rows = {r["variant"]: r["market"] for r in conn.execute(
        "SELECT variant, market FROM price_snapshots WHERE source = 'pricecharting'")}
    assert rows == {"ungraded": 250.0, "grade9": 900.0, "psa10": 4200.0}


def test_pricecharting_requires_token(conn, monkeypatch):
    demo.seed(conn, n_cards=2, days=3)
    card = conn.execute("SELECT card_id FROM cards LIMIT 1").fetchone()
    monkeypatch.delenv("PRICECHARTING_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="PRICECHARTING_TOKEN"):
        pricecharting.fetch_graded(conn, card["card_id"])
