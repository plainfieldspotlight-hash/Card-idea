import pytest
from fastapi.testclient import TestClient

from pokeprice import db, demo, model
from pokeprice.web.app import create_app


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "api.db"
    conn = db.connect(db_path)
    demo.seed(conn, n_cards=12, days=40)
    model.predict(conn, model_file=tmp_path / "missing.joblib")  # momentum run
    conn.close()
    return TestClient(create_app(db_path=db_path))


def test_stats_endpoint(client):
    payload = client.get("/api/stats").json()
    assert payload["cards"] == 12
    assert payload["latest_run"]["model_kind"] == "momentum"


def test_cards_list_search_and_pagination(client):
    payload = client.get("/api/cards", params={"limit": 5, "min_price": 0}).json()
    assert payload["total"] > 5
    assert len(payload["items"]) == 5
    item = payload["items"][0]
    for key in ("card_id", "name", "price", "spark", "predicted_return", "change7"):
        assert key in item
    assert len(item["spark"]) >= 2

    q = client.get("/api/cards", params={"q": item["name"], "min_price": 0}).json()
    assert all(item["name"] in row["name"] for row in q["items"])
    assert q["total"] >= 1

    empty = client.get("/api/cards", params={"q": "zzz-no-such-card"}).json()
    assert empty == {"total": 0, "items": []}


def test_card_detail_and_404(client):
    listing = client.get("/api/cards", params={"limit": 1, "min_price": 0}).json()["items"][0]
    detail = client.get(f"/api/cards/{listing['card_id']}").json()
    assert detail["card"]["card_id"] == listing["card_id"]
    assert detail["listings"]
    first = detail["listings"][0]
    assert first["history"]
    assert first["latest_price"] is not None
    assert first["prediction"] is None or "predicted_return" in first["prediction"]

    assert client.get("/api/cards/nope-999").status_code == 404


def test_movers(client):
    payload = client.get("/api/movers", params={"min_price": 0, "limit": 4}).json()
    assert payload["run"]["model_kind"] == "momentum"
    assert len(payload["gainers"]) == 4
    assert len(payload["losers"]) == 4
    top = payload["gainers"][0]["predicted_return"]
    bottom = payload["losers"][0]["predicted_return"]
    assert top >= bottom


def test_index_served(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "pokeprice" in resp.text
