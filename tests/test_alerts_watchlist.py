import json

from fastapi.testclient import TestClient

from pokeprice import alerts, db, demo, model
from pokeprice.web.app import create_app


def _plant_bullish_prediction(conn, card_id, source, variant, price=50.0):
    cur = conn.execute(
        "INSERT INTO prediction_runs (created_at, model_kind, horizon_days, as_of, metrics) "
        "VALUES ('2026-07-14T00:00:00', 'gbm', 7, '2026-07-14', ?)", (json.dumps({}),),
    )
    conn.execute(
        "INSERT INTO predictions (run_id, card_id, source, variant, price, "
        "predicted_return, prob_up, predicted_low, predicted_high, prob_gain) "
        "VALUES (?, ?, ?, ?, ?, 0.12, 0.95, 0.02, 0.30, 0.6)",
        (cur.lastrowid, card_id, source, variant, price),
    )
    conn.commit()


def test_alert_settings_roundtrip(conn):
    settings = alerts.get_settings(conn)
    assert settings["min_prob"] == 0.80
    saved = alerts.save_settings(conn, {"min_prob": 0.9, "junk": 123})
    assert saved["min_prob"] == 0.9
    assert "junk" not in saved
    assert alerts.get_settings(conn)["min_prob"] == 0.9


def test_signal_alert_fires_once_for_watched_card(conn):
    demo.seed(conn, n_cards=8, days=20)
    listing = conn.execute(
        "SELECT card_id, source, variant FROM price_snapshots LIMIT 1").fetchone()
    conn.execute(
        "INSERT INTO watchlist (card_id, source, variant, added_at) VALUES (?, ?, ?, 'now')",
        (listing["card_id"], listing["source"], listing["variant"]),
    )
    _plant_bullish_prediction(conn, listing["card_id"], listing["source"], listing["variant"])

    new = alerts.evaluate(conn)
    signals = [a for a in new if a["kind"] == "signal"]
    assert len(signals) == 1
    assert listing["card_id"] in signals[0]["message"] or signals[0]["card_id"] == listing["card_id"]
    # dedup: same run, same as-of -> nothing new
    assert not [a for a in alerts.evaluate(conn) if a["kind"] == "signal"]


def test_untracked_cards_never_alert(conn):
    demo.seed(conn, n_cards=8, days=20)
    listing = conn.execute(
        "SELECT card_id, source, variant FROM price_snapshots LIMIT 1").fetchone()
    _plant_bullish_prediction(conn, listing["card_id"], listing["source"], listing["variant"])
    assert [a for a in alerts.evaluate(conn) if a["kind"] == "signal"] == []


def test_discord_delivery(conn, monkeypatch):
    demo.seed(conn, n_cards=6, days=15)
    listing = conn.execute(
        "SELECT card_id, source, variant FROM price_snapshots LIMIT 1").fetchone()
    conn.execute(
        "INSERT INTO watchlist (card_id, source, variant, added_at) VALUES (?, ?, ?, 'now')",
        (listing["card_id"], listing["source"], listing["variant"]),
    )
    _plant_bullish_prediction(conn, listing["card_id"], listing["source"], listing["variant"])

    posts = []

    class FakeResp:
        def raise_for_status(self):
            return None

    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/hook")
    monkeypatch.setattr(alerts.requests, "post",
                        lambda url, json=None, timeout=None: posts.append((url, json)) or FakeResp())
    result = alerts.run(conn, log=lambda *_: None)
    assert result["new_alerts"] >= 1
    assert "discord" in result["channels"]
    assert posts and "pokeprice alerts" in posts[0][1]["content"]
    delivered = conn.execute(
        "SELECT delivered FROM alerts_log WHERE delivered IS NOT NULL").fetchall()
    assert delivered


def test_watchlist_api(tmp_path):
    db_path = tmp_path / "watch.db"
    c = db.connect(db_path)
    demo.seed(c, n_cards=8, days=20)
    model.predict(c, model_file=tmp_path / "none.joblib")
    c.close()
    client = TestClient(create_app(db_path=db_path))

    listing = client.get("/api/cards", params={"limit": 1, "min_price": 0}).json()["items"][0]
    assert listing["watched"] in (0, False)

    created = client.post("/api/watchlist", json={
        "card_id": listing["card_id"], "source": listing["source"],
        "variant": listing["variant"]})
    assert created.status_code == 201

    items = client.get("/api/watchlist").json()["items"]
    assert len(items) == 1
    assert items[0]["price"] is not None
    assert items[0]["predicted_return"] is not None

    again = client.get("/api/cards", params={"limit": 1, "min_price": 0}).json()["items"][0]
    assert again["watched"] in (1, True)

    removed = client.delete("/api/watchlist", params={
        "card_id": listing["card_id"], "source": listing["source"],
        "variant": listing["variant"]})
    assert removed.status_code == 200
    assert client.get("/api/watchlist").json()["items"] == []

    # alerts endpoints
    settings = client.get("/api/alerts").json()["settings"]
    assert settings["min_prob"] == 0.80
    updated = client.put("/api/alerts/settings", json={"min_return": 0.08}).json()
    assert updated["min_return"] == 0.08
    run = client.post("/api/alerts/run").json()
    assert "new_alerts" in run
