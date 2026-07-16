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
    _seed_listing(conn, "stale-1", [50.0] * 20)                     # never moves
    _seed_listing(conn, "live-1", [50.0 + 1.0 * i for i in range(20)])  # always moves
    df = features.add_features(features.load_frame(conn))
    stale = df[df["card_id"] == "stale-1"]
    live = df[df["card_id"] == "live-1"]
    assert stale[stale["n_hist"] >= 5]["activity"].max() == 0.0
    assert live[live["n_hist"] >= 5]["activity"].min() == 1.0
    # first observation has no transitions to judge
    assert np.isnan(df[df["n_hist"] == 0]["activity"]).all()


def test_training_frame_drops_stale_listings(conn):
    _seed_listing(conn, "stale-1", [50.0] * 30)
    _seed_listing(conn, "live-1", [50.0 * (1.01 ** i) for i in range(30)])
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

    # young listings (not enough transitions to judge staleness) are kept, not
    # pre-judged — 5 snapshots clears the separate MIN_HIST=3 depth gate while
    # staying below the 5-transition activity threshold
    _seed_listing(conn, "young-1", [33.0] * 5)
    df2 = model.build_training_frame(conn, horizon_days=1, min_activity=0.2)
    assert "young-1" in set(df2["card_id"])


def test_train_reports_stale_drop(conn, tmp_path):
    for i in range(6):
        _seed_listing(conn, f"live-{i}", [40.0 + 0.5 * ((j + i) % 9) for j in range(70)])
    for i in range(3):
        _seed_listing(conn, f"stale-{i}", [70.0] * 70)
    metrics = model.train(conn, horizon_days=7, model_file=tmp_path / "m.joblib",
                          min_activity=0.2)
    assert metrics["min_activity"] == 0.2
    assert metrics["stale_rows_dropped"] > 100  # ~3 listings x ~60 eligible rows


def test_demo_remove_keeps_real_data(tmp_path, monkeypatch):
    from pokeprice import cli, demo as demo_mod

    monkeypatch.setenv("POKEPRICE_DATA_DIR", str(tmp_path))
    conn = db.connect(tmp_path / "pokeprice.db")
    demo_mod.seed(conn, n_cards=10, days=10)
    _seed_listing(conn, "real-1", [5.0 + 0.1 * i for i in range(10)])
    conn.close()

    assert cli.main(["demo", "--remove"]) == 0
    conn = db.connect(tmp_path / "pokeprice.db")
    remaining = {r[0] for r in conn.execute("SELECT card_id FROM cards")}
    assert remaining == {"real-1"}
    assert conn.execute(
        "SELECT COUNT(*) FROM price_snapshots WHERE card_id LIKE 'demo%'"
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM price_snapshots WHERE card_id = 'real-1'"
    ).fetchone()[0] == 10


def test_is_chase_matcher():
    from pokeprice import config

    assert config.is_chase("Special Illustration Rare")
    assert config.is_chase("Illustration Rare")
    assert config.is_chase("Hyper Rare")
    assert config.is_chase("Rare Ultra")
    assert config.is_chase("Rare Holo VMAX")
    assert config.is_chase("Rare Secret")
    assert not config.is_chase("Common")
    assert not config.is_chase("Uncommon")
    assert not config.is_chase("Rare")
    assert not config.is_chase("Double Rare".replace("Double ", ""))  # plain Rare
    assert not config.is_chase(None)


def test_chase_scoped_training_and_prediction(conn, tmp_path):
    from pokeprice import demo as demo_mod

    demo_mod.seed(conn, n_cards=24, days=90)
    model_file = tmp_path / "chase.joblib"
    metrics = model.train(conn, horizon_days=7, model_file=model_file, chase=True)
    assert metrics["scope"] == "chase"

    frame = model.build_training_frame(conn, 7, chase=True)
    from pokeprice import config
    assert frame["rarity"].map(config.is_chase).all()
    assert len(frame) < len(model.build_training_frame(conn, 7, chase=False))

    result = model.predict(conn, model_file=model_file)
    rows = conn.execute(
        "SELECT DISTINCT c.rarity FROM predictions p JOIN cards c USING (card_id) "
        "WHERE p.run_id = ?", (result["run_id"],)).fetchall()
    assert rows
    assert all(config.is_chase(r["rarity"]) for r in rows)


def test_general_train_reports_chase_subset(conn, tmp_path):
    from pokeprice import demo as demo_mod

    demo_mod.seed(conn, n_cards=24, days=90)
    metrics = model.train(conn, horizon_days=7, model_file=tmp_path / "m.joblib")
    assert metrics["scope"] == "all"
    assert "chase_subset" in metrics
    assert metrics["chase_subset"]["n"] >= 30


def test_chase_buckets():
    from pokeprice import config

    assert config.in_bucket("Illustration Rare", "ir")
    assert not config.in_bucket("Special Illustration Rare", "ir")  # IR excludes SIR
    assert config.in_bucket("Special Illustration Rare", "sir")
    assert config.in_bucket("Rare Ultra", "full-art")
    assert config.in_bucket("Ultra Rare", "full-art")
    assert config.in_bucket("Hyper Rare", "secret")
    assert config.in_bucket("Rare Secret", "secret")
    assert config.in_bucket("Rare Holo VMAX", "holo")
    assert config.in_bucket("Radiant Rare", "shiny")
    assert not config.in_bucket("Common", "holo")
    assert config.in_bucket("Common", "")  # no bucket = no filter
