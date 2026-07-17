import pytest

from pokeprice import config, db, demo, scheduler


def test_parse_interval():
    assert scheduler.parse_interval("daily") == 86400
    assert scheduler.parse_interval("weekly") == 7 * 86400
    assert scheduler.parse_interval("12h") == 12 * 3600
    assert scheduler.parse_interval("2d") == 2 * 86400
    assert scheduler.parse_interval("1h") == 3600
    with pytest.raises(ValueError):
        scheduler.parse_interval("every so often")


def test_run_cycle_fetch_train_predict(tmp_path, monkeypatch):
    db_path = tmp_path / "sched.db"

    def fake_api(conn, sets=None, progress=print):
        result = demo.seed(conn, n_cards=20, days=90)
        return result["cards"], result["snapshots"]

    monkeypatch.setattr(scheduler.fetch, "fetch_api", fake_api)
    monkeypatch.setenv("POKEPRICE_MODEL", str(tmp_path / "model.joblib"))

    status = scheduler.run_cycle(db_path, log=lambda *_: None)
    assert status["ok"] is True
    assert status["steps"]["fetch"]["snapshots"] > 0
    trained = {t["horizon_days"]: t for t in status["steps"]["train"]}
    assert set(trained) == set(config.HORIZONS)
    assert trained[config.DEFAULT_HORIZON_DAYS]["ok"] is True
    predicted = {r["horizon_days"]: r["model_kind"]
                 for r in status["steps"]["predict"]["runs"]}
    assert set(predicted) == set(config.HORIZONS)
    assert predicted[config.DEFAULT_HORIZON_DAYS] == "gbm"
    # every horizon that trained successfully predicts with its own model
    for horizon, t in trained.items():
        if t["ok"]:
            assert predicted[horizon] == "gbm"

    conn = db.connect(db_path)
    persisted = db.get_meta(conn, "auto_fetch_last")
    assert persisted["ok"] is True
    assert conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0] > 0


def test_run_cycle_survives_fetch_failure(tmp_path, monkeypatch):
    def broken_api(conn, sets=None, progress=print):
        raise ConnectionError("network down")

    monkeypatch.setattr(scheduler.fetch, "fetch_api", broken_api)
    status = scheduler.run_cycle(tmp_path / "sched.db", log=lambda *_: None)
    assert status["ok"] is False
    assert "network down" in status["error"]


def test_run_cycle_auto_backfill(tmp_path, monkeypatch):
    from pokeprice import backfill as backfill_mod

    def fake_api(conn, sets=None, progress=print):
        result = demo.seed(conn, n_cards=12, days=40)
        return result["cards"], result["snapshots"]

    calls = []

    def fake_backfill(conn, days=120, every=2, set_ids=None, end=None,
                      progress=print):
        calls.append(days)
        return {"snapshots_added": 42, "days_processed": 7,
                "groups_matched": 3, "products_matched": 100}

    monkeypatch.setattr(scheduler.fetch, "fetch_api", fake_api)
    monkeypatch.setattr(backfill_mod, "backfill", fake_backfill)
    monkeypatch.setenv("POKEPRICE_MODEL", str(tmp_path / "m.joblib"))

    # off by default: no backfill step
    monkeypatch.setattr(config, "AUTO_BACKFILL_DAYS", 0)
    status = scheduler.run_cycle(tmp_path / "a.db", log=lambda *_: None)
    assert "backfill" not in status["steps"]
    assert calls == []

    monkeypatch.setattr(config, "AUTO_BACKFILL_DAYS", 365)
    status = scheduler.run_cycle(tmp_path / "b.db", log=lambda *_: None)
    assert status["steps"]["backfill"] == {
        "ok": True, "snapshots_added": 42, "days_processed": 7}
    assert calls == [365]

    # a backfill hiccup must not sink the cycle
    def broken(conn, **kw):
        raise RuntimeError("tcgcsv down")

    monkeypatch.setattr(backfill_mod, "backfill", broken)
    status = scheduler.run_cycle(tmp_path / "c.db", log=lambda *_: None)
    assert status["ok"] is True
    assert status["steps"]["backfill"]["ok"] is False
