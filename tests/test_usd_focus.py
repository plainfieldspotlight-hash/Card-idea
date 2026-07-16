"""USD-only + $30 focus floor: parsing, purge migration, and prediction gate."""
from fastapi.testclient import TestClient

from pokeprice import config, db, demo, model
from pokeprice.ingest import tcg_json
from pokeprice.web.app import create_app


def test_snapshot_rows_ignore_cardmarket_block():
    card = {
        "id": "x-1",
        "name": "X",
        "tcgplayer": {"updatedAt": "2026/07/01",
                      "prices": {"normal": {"market": 12.0, "low": 10.0}}},
        "cardmarket": {"updatedAt": "2026/07/01",
                       "prices": {"trendPrice": 11.0, "lowPrice": 9.0,
                                  "avg7": 10.5, "reverseHoloTrend": 14.0}},
    }
    rows = tcg_json.snapshot_rows(card)
    assert {r["source"] for r in rows} == {"tcgplayer"}
    assert all(r["currency"] == "USD" for r in rows)


def test_demo_market_is_usd_only(conn):
    demo.seed(conn, n_cards=15, days=10)
    currencies = {r[0] for r in conn.execute(
        "SELECT DISTINCT currency FROM price_snapshots")}
    assert currencies == {"USD"}


def test_connect_purges_legacy_eur_rows(tmp_path):
    db_path = tmp_path / "legacy.db"
    conn = db.connect(db_path)
    demo.seed(conn, n_cards=4, days=5)
    # recreate what an old install held: EUR listings plus a prediction on one
    db.insert_snapshots(conn, [{
        "card_id": "demo1-1", "source": "cardmarket", "variant": "normal",
        "snapshot_date": f"2026-07-{d:02d}", "currency": "EUR", "market": 40.0,
    } for d in (1, 2, 3)])
    cur = conn.execute(
        "INSERT INTO prediction_runs (created_at, model_kind, horizon_days, as_of) "
        "VALUES ('t', 'momentum', 7, '2026-07-03')")
    conn.execute(
        "INSERT INTO predictions (run_id, card_id, source, variant, price, "
        "predicted_return, prob_up) VALUES (?, 'demo1-1', 'cardmarket', 'normal', "
        "40.0, 0.1, 0.6)", (cur.lastrowid,))
    conn.execute("DELETE FROM meta WHERE key = 'usd_only_purge'")
    conn.commit()
    conn.close()

    conn = db.connect(db_path)  # purge runs here
    assert conn.execute("SELECT COUNT(*) FROM price_snapshots "
                        "WHERE currency != 'USD'").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM predictions "
                        "WHERE source = 'cardmarket'").fetchone()[0] == 0
    # USD data untouched
    assert conn.execute("SELECT COUNT(*) FROM price_snapshots").fetchone()[0] > 0
    stamp = db.get_meta(conn, "usd_only_purge")
    assert stamp["snapshots_removed"] == 3
    assert stamp["predictions_removed"] == 1
    conn.close()


def test_predictions_respect_focus_floor(conn, tmp_path):
    demo.seed(conn, n_cards=20, days=20)
    result = model.predict(conn, model_file=tmp_path / "missing.joblib")
    assert result["listings_scored"] > 0
    floor = conn.execute("SELECT MIN(price) FROM predictions").fetchone()[0]
    assert floor >= config.MIN_PRICE
    # cheap listings exist in the DB but never get predictions
    cheap = conn.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT card_id, MAX(COALESCE(market, mid, low)) AS p
            FROM price_snapshots GROUP BY card_id, source, variant
        ) WHERE p < ?
        """, (config.MIN_PRICE,)).fetchone()[0]
    assert cheap > 0


def test_buys_bottom_tier_carries_floor_label(tmp_path):
    db_path = tmp_path / "tiers.db"
    c = db.connect(db_path)
    demo.seed(c, n_cards=10, days=30)
    model.predict(c, model_file=tmp_path / "none.joblib")
    c.close()
    client = TestClient(create_app(db_path=db_path))
    tiers = client.get("/api/buys", params={"min_prob": 0, "min_return": -1}).json()["tiers"]
    assert tiers[-1]["key"] == "under-100"
    assert tiers[-1]["label"] == f"${config.MIN_PRICE:g} – $100"
    for tier in tiers:
        for item in tier["items"]:
            assert item["price"] >= config.MIN_PRICE


def test_lopsided_classifier_labels_fall_back_instead_of_crashing(conn):
    # One big-gain row used to crash HGB's stratified early-stopping split
    # ("least populated classes ... too few"); now the classifier is skipped
    # and probabilities derive from the regressor.
    demo.seed(conn, n_cards=16, days=60)
    df = model.build_training_frame(conn, horizon_days=7)
    df = df.copy()
    df["label"] = 0.01                     # everything drifts up a little...
    df.iloc[0, df.columns.get_loc("label")] = 0.5   # ...except one moonshot
    bundle, _ = model.fit_bundle(df, horizon_days=7)
    assert bundle.clf_gain is None         # 1 positive: not fittable
    assert bundle.classifier is None       # single class: not fittable
    scores = model.apply_bundle(bundle, df.head(10))
    assert ((scores["prob_up"] > 0) & (scores["prob_up"] < 1)).all()
    assert ((scores["prob_gain"] > 0) & (scores["prob_gain"] < 1)).all()


def test_thin_history_listings_are_never_scored(conn, tmp_path):
    demo.seed(conn, n_cards=8, days=20)
    # a listing seen only once — like a set fetched for the first time today
    cid = conn.execute("SELECT card_id FROM cards LIMIT 1").fetchone()[0]
    db.insert_snapshots(conn, [{
        "card_id": cid, "source": "tcgplayer", "variant": "1stEditionHolofoil",
        "snapshot_date": "2026-07-15", "currency": "USD", "market": 150.0,
    }])
    result = model.predict(conn, model_file=tmp_path / "missing.joblib")
    assert result["listings_skipped_thin"] >= 1
    scored = conn.execute(
        "SELECT COUNT(*) FROM predictions WHERE variant = '1stEditionHolofoil'"
    ).fetchone()[0]
    assert scored == 0
    # and training rows respect the same depth gate
    frame = model.build_training_frame(conn, horizon_days=7)
    assert (frame["n_hist"] >= config.MIN_HIST - 1).all()


def test_predict_errors_clearly_when_no_history_anywhere(conn, tmp_path):
    db.upsert_cards(conn, [{"card_id": "solo-1", "name": "Solo", "rarity": "Rare Holo"}])
    db.insert_snapshots(conn, [{
        "card_id": "solo-1", "source": "tcgplayer", "variant": "normal",
        "snapshot_date": "2026-07-15", "currency": "USD", "market": 99.0,
    }])
    import pytest as _pytest
    with _pytest.raises(RuntimeError, match="price snapshots"):
        model.predict(conn, model_file=tmp_path / "missing.joblib")
