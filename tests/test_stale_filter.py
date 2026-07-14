from datetime import date, timedelta

import numpy as np

from pokeprice import db, features, model


def _seed_listing(conn, card_id, prices, name="Card"):
    db.upsert_cards(conn, [{
        "card_id": card_id, "name": f"{name} {card_id}", "rarity": "Rare",
        "set_id": "s1", "set_name": "Set One", "set_release_date": "2024-01-01",
    }])
    base = date(2026, 5, 1)
    db.insert_snapshots(conn, [{
        "card_id": card_id, "source": "tcgplayer", "variant": "normal",
        "snapshot_date": (base + timedelta(days=i)).isoformat(),
        "currency": "USD", "market": p,
    } for i, p in enumerate(prices)])


def test_activity_feature(conn):
    _seed_listing(conn, "stale-1", [5.0] * 20)                     # never moves
    _seed_listing(conn, "live-1", [5.0 + 0.1 * i for i in range(20)])  # always moves
    df = features.add_features(features.load_frame(conn))
    stale = df[df["card_id"] == "stale-1"]
    live = df[df["card_id"] == "live-1"]
    assert stale[stale["n_hist"] >= 5]["activity"].max() == 0.0
    assert live[live["n_hist"] >= 5]["activity"].min() == 1.0
    # first observation has no transitions to judge
    assert np.isnan(df[df["n_hist"] == 0]["activity"]).all()


def test_training_frame_drops_stale_listings(conn):
    _seed_listing(conn, "stale-1", [5.0] * 30)
    _seed_listing(conn, "live-1", [5.0 * (1.01 ** i) for i in range(30)])
    df_filtered = model.build_training_frame(conn, horizon_days=7, min_activity=0.2)
    stale_rows = df_filtered[df_filtered["card_id"] == "stale-1"]
    # only the unjudgeable early observations survive (no look-ahead selection);
    # everything after the listing proves itself stale is dropped
    assert (stale_rows["n_hist"] < 5).all()
    assert len(stale_rows) <= 5
    assert (df_filtered["card_id"] == "live-1").sum() > 15
    assert df_filtered.attrs["stale_rows_dropped"] > 0

    df_off = model.build_training_frame(conn, horizon_days=7, min_activity=0)
    assert set(df_off["card_id"]) == {"stale-1", "live-1"}

    # young listings (not enough transitions to judge) are kept, not pre-judged
    _seed_listing(conn, "young-1", [3.0, 3.0, 3.0])
    df2 = model.build_training_frame(conn, horizon_days=1, min_activity=0.2)
    assert "young-1" in set(df2["card_id"])


def test_train_reports_stale_drop(conn, tmp_path):
    for i in range(6):
        _seed_listing(conn, f"live-{i}", [4.0 + 0.05 * ((j + i) % 9) for j in range(70)])
    for i in range(3):
        _seed_listing(conn, f"stale-{i}", [7.0] * 70)
    metrics = model.train(conn, horizon_days=7, model_file=tmp_path / "m.joblib",
                          min_activity=0.2)
    assert metrics["min_activity"] == 0.2
    assert metrics["stale_rows_dropped"] > 100  # ~3 listings x ~60 eligible rows
