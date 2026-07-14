from datetime import date, timedelta

import numpy as np

from pokeprice import db, features


def seed_series(conn, card_id="g-1", days=30, daily_growth=0.01, start=100.0):
    db.upsert_cards(conn, [{
        "card_id": card_id, "name": f"Grower {card_id}", "rarity": "Rare",
        "set_id": "g", "set_name": "Growth", "set_release_date": "2024-01-01",
    }])
    base = date(2025, 6, 1)
    snaps = []
    for i in range(days):
        price = start * (1 + daily_growth) ** i
        snaps.append({
            "card_id": card_id, "source": "tcgplayer", "variant": "normal",
            "snapshot_date": (base + timedelta(days=i)).isoformat(),
            "currency": "USD", "market": price,
            "low": price * 0.9, "high": price * 1.1,
        })
    db.insert_snapshots(conn, snaps)


def test_trailing_returns_and_labels(conn):
    seed_series(conn, days=30, daily_growth=0.01)
    df = features.load_frame(conn)
    df = features.add_features(df)
    df = features.add_labels(df, horizon_days=7)

    mid = df[df["n_hist"] == 15].iloc[0]
    expected_7d = 1.01**7 - 1
    assert np.isclose(mid["ret_7d"], expected_7d, rtol=1e-6)
    assert np.isclose(mid["ret_1d"], 0.01, rtol=1e-6)
    assert np.isclose(mid["label"], expected_7d, rtol=1e-6)
    assert mid["set_age_days"] > 500

    # the last row has no forward snapshot -> no label
    last = df[df["n_hist"] == 29].iloc[0]
    assert np.isnan(last["label"])
    # and the first row has no trailing history -> no returns
    first = df[df["n_hist"] == 0].iloc[0]
    assert np.isnan(first["ret_7d"])


def test_no_lookahead_in_trailing_features(conn):
    # Sparse series: snapshots every 3 days; ret_1d must never match the row itself.
    db.upsert_cards(conn, [{"card_id": "s-1", "name": "Sparse"}])
    base = date(2025, 6, 1)
    db.insert_snapshots(conn, [{
        "card_id": "s-1", "source": "tcgplayer", "variant": "normal",
        "snapshot_date": (base + timedelta(days=i * 3)).isoformat(),
        "currency": "USD", "market": 10.0 + i,
    } for i in range(10)])
    df = features.add_features(features.load_frame(conn))
    assert df["ret_1d"].isna().all()  # nothing ~1 day back exists
    assert df["ret_7d"].notna().sum() > 0  # but ~7d lookups tolerate 6/9-day gaps


def test_latest_rows_picks_newest_per_listing(conn):
    seed_series(conn, card_id="g-1")
    seed_series(conn, card_id="g-2")
    df = features.add_features(features.load_frame(conn))
    latest = features.latest_rows(df)
    assert len(latest) == 2
    assert set(latest["snapshot_date"].dt.date) == {date(2025, 6, 30)}


def test_build_matrix_handles_all_nan_and_unseen_categories(conn):
    seed_series(conn)
    df = features.add_features(features.load_frame(conn))
    df["spread"] = np.nan  # simulate a feature with no data at all
    X, names, cat_idx, cat_maps = features.build_matrix(df)
    assert X.shape == (len(df), len(names))
    spread_col = X[:, names.index("spread")]
    assert np.isfinite(spread_col).all()  # neutralized, not NaN

    # apply-time: unseen category becomes NaN code, not a crash
    df2 = df.copy()
    df2["rarity"] = "Never Seen Before"
    X2, _, _, _ = features.build_matrix(df2, cat_maps=cat_maps)
    assert np.isnan(X2[:, names.index("rarity")]).all()
