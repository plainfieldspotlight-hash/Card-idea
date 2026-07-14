"""Tests for the trust layer: report card, backtest, quantiles, events."""
import json
from datetime import date, timedelta

import numpy as np
import pytest

from pokeprice import backtest, db, demo, features, model, report


@pytest.fixture
def trained(conn, tmp_path):
    demo.seed(conn, n_cards=24, days=90)
    model_file = tmp_path / "model.joblib"
    metrics = model.train(conn, horizon_days=7, model_file=model_file)
    return conn, model_file, metrics


def test_quantile_outputs(trained):
    conn, model_file, metrics = trained
    assert 0.0 <= metrics["interval_coverage"] <= 1.0
    assert metrics["big_gain_threshold"] == 0.10
    result = model.predict(conn, model_file=model_file)
    assert result["model_kind"] == "gbm"
    rows = conn.execute(
        "SELECT predicted_return, predicted_low, predicted_high, prob_gain "
        "FROM predictions WHERE run_id = ?", (result["run_id"],)
    ).fetchall()
    assert rows
    for r in rows:
        assert r["predicted_low"] <= r["predicted_return"] <= r["predicted_high"]
        assert 0.0 <= r["prob_gain"] <= 1.0


def test_stale_model_falls_back(trained, monkeypatch):
    conn, model_file, _ = trained
    # simulate a feature-set change since training
    monkeypatch.setattr(model.features, "NUM_FEATURES",
                        model.features.NUM_FEATURES + ["brand_new_feature"])
    assert model.load_bundle(model_file) is None
    result = model.predict(conn, model_file=model_file)
    assert result["model_kind"] == "momentum"


def test_report_card_scores_resolved_predictions(trained):
    conn, _, _ = trained
    # plant a prediction run dated 10 days before the newest snapshot, so a
    # realized price ~7d later already exists in the data
    last = conn.execute("SELECT MAX(snapshot_date) d FROM price_snapshots").fetchone()["d"]
    as_of = (date.fromisoformat(last) - timedelta(days=10)).isoformat()
    listings = conn.execute(
        """
        SELECT card_id, source, variant,
               COALESCE(market, mid, low) AS price
        FROM price_snapshots WHERE snapshot_date = ?
        LIMIT 20
        """, (as_of,)
    ).fetchall()
    assert listings, "demo data should have snapshots on the planted as-of date"
    cur = conn.execute(
        "INSERT INTO prediction_runs (created_at, model_kind, horizon_days, as_of, metrics) "
        "VALUES (?, 'gbm', 7, ?, ?)", ("2026-01-01T00:00:00", as_of, json.dumps({})),
    )
    run_id = cur.lastrowid
    conn.executemany(
        "INSERT INTO predictions (run_id, card_id, source, variant, price, "
        "predicted_return, prob_up, predicted_low, predicted_high, prob_gain) "
        "VALUES (?, ?, ?, ?, ?, 0.05, 0.8, -0.02, 0.15, 0.3)",
        [(run_id, l["card_id"], l["source"], l["variant"], l["price"]) for l in listings],
    )
    conn.commit()

    payload = report.prediction_report(conn)
    assert payload["overall"]["n_resolved"] >= len(listings) * 0.8
    assert payload["overall"]["hit_rate"] is not None
    assert 0.0 <= payload["overall"]["hit_rate"] <= 1.0
    assert payload["overall"]["interval_coverage"] is not None
    assert [t["key"] for t in payload["by_tier"]] == [
        "over-1000", "500-1000", "100-500", "under-100"]
    assert payload["recent"]
    assert "realized_return" in payload["recent"][0]


def test_backtest_runs_and_persists(trained):
    conn, _, _ = trained
    result = backtest.run_backtest(conn, capital=500, top_k=3, fee_rate=0.13)
    assert result["n_periods"] >= 2
    assert len(result["equity"]) == result["n_periods"] + 1
    assert result["final_equity"] == result["equity"][-1][1]
    assert 0 <= result["win_rate"] <= 1
    assert result["max_drawdown"] >= 0
    assert db.get_meta(conn, "backtest_last")["final_equity"] == result["final_equity"]


def test_backtest_insufficient_history(conn):
    demo.seed(conn, n_cards=4, days=6)
    with pytest.raises(model.InsufficientHistory):
        backtest.run_backtest(conn)


def test_event_recency_feature(conn):
    demo.seed(conn, n_cards=6, days=20)
    conn.execute("INSERT INTO events (event_date, note, match) VALUES (?, ?, ?)",
                 ("2026-06-30", "reprint news", "charizard"))
    conn.commit()
    df = features.load_frame(conn)
    df = features.add_features(df, events=features.load_events(conn))
    hits = df[df["name"].str.lower().str.contains("charizard")]
    misses = df[~df["name"].str.lower().str.contains("charizard")]
    assert misses["event_recency"].isna().all()
    after = hits[hits["snapshot_date"] >= "2026-06-30"]
    if len(after):
        assert after["event_recency"].notna().any()
        assert (after["event_recency"].dropna() >= 0).all()


def test_cross_card_features_leave_one_out(conn):
    demo.seed(conn, n_cards=12, days=30)
    df = features.load_frame(conn)
    df = features.add_features(df)
    # every listing with same-set peers on the same date gets a set momentum
    with_ret = df[df["ret_7d"].notna()]
    assert with_ret["set_mom_7d"].notna().sum() > 0
    assert with_ret["char_mom_7d"].notna().sum() > 0
    # leave-one-out: a card's own return must not equal the group mean when
    # the group has >1 member (they'd only coincide by construction error)
    sample = with_ret.dropna(subset=["set_mom_7d"])
    assert not np.allclose(sample["ret_7d"], sample["set_mom_7d"])
