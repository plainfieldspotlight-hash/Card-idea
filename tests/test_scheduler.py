import pytest

from pokeprice import db, demo, scheduler


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

    def fake_dump(conn, progress=print):
        result = demo.seed(conn, n_cards=20, days=90)

        class Report:
            cards = result["cards"]
            snapshots = result["snapshots"]

        return Report()

    monkeypatch.setattr(scheduler.fetch, "fetch_github_dump", fake_dump)
    monkeypatch.setenv("POKEPRICE_MODEL", str(tmp_path / "model.joblib"))

    status = scheduler.run_cycle(db_path, log=lambda *_: None)
    assert status["ok"] is True
    assert status["steps"]["fetch"]["snapshots"] > 0
    assert status["steps"]["train"]["ok"] is True
    assert status["steps"]["predict"]["model_kind"] == "gbm"

    conn = db.connect(db_path)
    persisted = db.get_meta(conn, "auto_fetch_last")
    assert persisted["ok"] is True
    assert conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0] > 0


def test_run_cycle_survives_fetch_failure(tmp_path, monkeypatch):
    def broken_dump(conn, progress=print):
        raise ConnectionError("network down")

    monkeypatch.setattr(scheduler.fetch, "fetch_github_dump", broken_dump)
    status = scheduler.run_cycle(tmp_path / "sched.db", log=lambda *_: None)
    assert status["ok"] is False
    assert "network down" in status["error"]
