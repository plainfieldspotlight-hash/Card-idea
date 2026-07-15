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


def test_search_multi_word_and_filters(client):
    listing = client.get("/api/cards", params={"limit": 1, "min_price": 0}).json()["items"][0]
    name_word = listing["name"].split()[0]

    # multi-word: name word + rarity word must both match the same card
    both = client.get("/api/cards", params={
        "q": f"{name_word} {listing['rarity'].split()[0]}", "min_price": 0}).json()
    assert both["total"] >= 1
    assert all(name_word.lower() in i["name"].lower() for i in both["items"])

    # a nonsense second word kills the match
    none = client.get("/api/cards", params={
        "q": f"{name_word} zzzznope", "min_price": 0}).json()
    assert none["total"] == 0

    # rarity filter
    rare = client.get("/api/cards", params={
        "rarity": listing["rarity"], "min_price": 0}).json()
    assert rare["total"] >= 1
    assert all(i["rarity"] == listing["rarity"] for i in rare["items"])

    # sets endpoint feeds the set filter, and filtering by set works
    sets = client.get("/api/sets").json()
    assert sets["sets"] and sets["rarities"]
    set_id = sets["sets"][0]["set_id"]
    in_set = client.get("/api/cards", params={"set_id": set_id, "min_price": 0}).json()
    assert in_set["total"] >= 1

    # autocomplete: prefix match first, short queries return nothing
    sug = client.get("/api/suggest", params={"q": name_word[:4]}).json()["suggestions"]
    assert any(s.lower().startswith(name_word[:4].lower()) for s in sug)
    assert client.get("/api/suggest", params={"q": "x"}).json()["suggestions"] == []


def test_chase_filter_money_makers_only(client):
    all_cards = client.get("/api/cards", params={"min_price": 0, "limit": 200}).json()
    chase = client.get("/api/cards", params={"min_price": 0, "limit": 200, "chase": 1}).json()
    assert 0 < chase["total"] < all_cards["total"]
    # demo rarities: Rare Holo / Ultra Rare / Secret Rare qualify; bulk doesn't
    bulk = {"Common", "Uncommon", "Rare"}
    assert all(item["rarity"] not in bulk for item in chase["items"])
    assert any(item["rarity"] in bulk for item in all_cards["items"])

    movers = client.get("/api/movers", params={"min_price": 0, "chase": 1}).json()
    for side in ("gainers", "losers"):
        assert all(m["rarity"] not in bulk for m in movers[side])

    buys = client.get("/api/buys", params={"min_prob": 0, "min_return": -1,
                                           "chase": 1}).json()
    for tier in buys["tiers"]:
        assert all(i["rarity"] not in bulk for i in tier["items"])

    deals = client.get("/api/deals", params={"min_prob": 0, "min_return": -1,
                                             "chase": 1}).json()
    assert all(d["rarity"] not in bulk for d in deals["deals"])


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


def test_buys_tiers(client):
    payload = client.get(
        "/api/buys", params={"min_prob": 0.0, "min_return": -1.0, "per_tier": 4}
    ).json()
    assert [t["key"] for t in payload["tiers"]] == [
        "over-1000", "500-1000", "100-500", "under-100",
    ]
    seen_any = False
    for tier in payload["tiers"]:
        assert len(tier["items"]) <= 4
        for item in tier["items"]:
            seen_any = True
            price = item["price"]
            assert tier["min"] is None or price > tier["min"]
            assert tier["max"] is None or price <= tier["max"]
        returns = [i["predicted_return"] for i in tier["items"]]
        assert returns == sorted(returns, reverse=True)
    assert seen_any  # demo market always has cheap listings at minimum

    strict = client.get(
        "/api/buys", params={"min_prob": 0.999, "min_return": 5.0}
    ).json()
    assert all(not t["items"] for t in strict["tiers"])
    # thresholds actually gate: every default-criteria item clears the bar
    default = client.get("/api/buys").json()
    for tier in default["tiers"]:
        for item in tier["items"]:
            assert item["prob_up"] >= 0.7
            assert item["predicted_return"] >= 0.02


def test_buys_without_predictions(tmp_path):
    db_path = tmp_path / "empty.db"
    conn = db.connect(db_path)
    demo.seed(conn, n_cards=4, days=5)
    conn.close()
    empty_client = TestClient(create_app(db_path=db_path))
    payload = empty_client.get("/api/buys").json()
    assert payload["run"] is None
    assert all(not t["items"] for t in payload["tiers"])


def test_collection_lifecycle(client):
    listing = client.get("/api/cards", params={"limit": 1, "min_price": 0}).json()["items"][0]

    empty = client.get("/api/collection").json()
    assert empty["holdings"] == []
    assert empty["totals"]["count"] == 0

    created = client.post("/api/collection", json={
        "card_id": listing["card_id"], "source": listing["source"],
        "variant": listing["variant"], "quantity": 3, "cost_basis": 1.50,
    })
    assert created.status_code == 201
    holding_id = created.json()["holding_id"]

    payload = client.get("/api/collection").json()
    assert payload["totals"]["count"] == 1
    h = payload["holdings"][0]
    assert h["quantity"] == 3
    assert h["price"] == listing["price"]
    assert h["value"] == listing["price"] * 3
    expected_gain = (listing["price"] - 1.50) * 3
    assert abs(h["gain"] - expected_gain) < 1e-9
    # totals are USD; EUR holdings convert at the rate echoed in the payload
    mult = payload["totals"]["eur_usd"] if h["currency"] == "EUR" else 1.0
    assert abs(payload["totals"]["value"] - h["value"] * mult) < 1e-6

    # unknown listing rejected
    bad = client.post("/api/collection", json={
        "card_id": "nope-1", "source": "tcgplayer", "variant": "normal",
    })
    assert bad.status_code == 404

    assert client.delete(f"/api/collection/{holding_id}").status_code == 200
    assert client.delete(f"/api/collection/{holding_id}").status_code == 404
    assert client.get("/api/collection").json()["totals"]["count"] == 0


def test_card_ebay_link_mode(client, monkeypatch):
    monkeypatch.delenv("EBAY_CLIENT_ID", raising=False)
    monkeypatch.delenv("EBAY_CLIENT_SECRET", raising=False)
    listing = client.get("/api/cards", params={"limit": 1, "min_price": 0}).json()["items"][0]
    payload = client.get(f"/api/cards/{listing['card_id']}/ebay",
                         params={"variant": listing["variant"]}).json()
    assert payload["mode"] == "link"
    assert payload["search_url"].startswith("https://www.ebay.com/sch/")
    assert payload["market_price"] is not None
    assert payload["items"] == []

    detail = client.get(f"/api/cards/{listing['card_id']}").json()
    assert all(l["ebay_url"].startswith("https://www.ebay.com/sch/") for l in detail["listings"])


def test_index_served(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "pokeprice" in resp.text
