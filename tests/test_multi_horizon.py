"""Multi-horizon predictions: one run per horizon (7/30/60d), with the
dashboard's action screens pinned to the default horizon."""
import pytest
from fastapi.testclient import TestClient

from pokeprice import cli, config, db, demo, model
from pokeprice.web.app import create_app


def test_model_path_per_horizon(tmp_path, monkeypatch):
    monkeypatch.setenv("POKEPRICE_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("POKEPRICE_MODEL", raising=False)
    assert config.model_path().name == "model.joblib"
    assert config.model_path(config.DEFAULT_HORIZON_DAYS).name == "model.joblib"
    assert config.model_path(30).name == "model-30d.joblib"
    assert config.model_path(60).name == "model-60d.joblib"
    # an explicit override names the default-horizon file; others derive
    monkeypatch.setenv("POKEPRICE_MODEL", str(tmp_path / "custom.joblib"))
    assert config.model_path().name == "custom.joblib"
    assert config.model_path(60).name == "custom-60d.joblib"


def test_predict_multi_creates_one_run_per_horizon(conn):
    demo.seed(conn, n_cards=8, days=30)
    result = model.predict(conn)  # no horizon, no model file -> all horizons
    assert {r["horizon_days"] for r in result["runs"]} == set(config.HORIZONS)
    rows = conn.execute(
        "SELECT r.horizon_days, COUNT(*) AS n FROM prediction_runs r "
        "JOIN predictions p USING (run_id) GROUP BY r.horizon_days"
    ).fetchall()
    assert {r["horizon_days"] for r in rows} == set(config.HORIZONS)
    assert all(r["n"] > 0 for r in rows)
    # longer momentum horizons scale the estimate up, never down
    preds = {r["horizon_days"]: conn.execute(
        "SELECT AVG(ABS(predicted_return)) FROM predictions WHERE run_id = ?",
        (r["run_id"],)).fetchone()[0] for r in result["runs"]}
    assert preds[60] >= preds[7]


def test_single_horizon_calls_stay_single(conn, tmp_path):
    demo.seed(conn, n_cards=6, days=20)
    by_file = model.predict(conn, model_file=tmp_path / "missing.joblib")
    assert by_file["horizon_days"] == config.DEFAULT_HORIZON_DAYS
    by_horizon = model.predict(conn, horizon_days=30)
    assert by_horizon["horizon_days"] == 30
    assert "runs" not in by_file and "runs" not in by_horizon


@pytest.fixture
def multi_client(tmp_path):
    db_path = tmp_path / "multi.db"
    c = db.connect(db_path)
    demo.seed(c, n_cards=10, days=40)
    model.predict(c)  # momentum runs for every configured horizon
    c.close()
    return TestClient(create_app(db_path=db_path))


def test_cards_expose_extra_horizon_columns(multi_client):
    items = multi_client.get(
        "/api/cards", params={"min_price": 0, "limit": 20}).json()["items"]
    assert items
    assert all("predicted_30d" in i and "predicted_60d" in i for i in items)
    assert any(i["predicted_30d"] is not None for i in items)
    assert any(i["predicted_60d"] is not None for i in items)
    by30 = multi_client.get("/api/cards", params={
        "min_price": 0, "limit": 100, "sort": "pred30"}).json()["items"]
    vals = [i["predicted_30d"] for i in by30 if i["predicted_30d"] is not None]
    assert vals == sorted(vals, reverse=True)


def test_action_screens_pinned_to_default_horizon(multi_client):
    # the 60d run has the highest run_id (inserted last) — the action screens
    # must stay on the default horizon rather than silently switching
    movers = multi_client.get("/api/movers", params={"min_price": 0}).json()
    assert movers["run"]["horizon_days"] == config.DEFAULT_HORIZON_DAYS
    buys = multi_client.get("/api/buys").json()
    assert buys["run"]["horizon_days"] == config.DEFAULT_HORIZON_DAYS
    stats = multi_client.get("/api/stats").json()
    assert stats["latest_run"]["horizon_days"] == config.DEFAULT_HORIZON_DAYS
    # an explicit horizon switches the ranking run
    movers60 = multi_client.get(
        "/api/movers", params={"min_price": 0, "horizon": 60}).json()
    assert movers60["run"]["horizon_days"] == 60
    buys60 = multi_client.get("/api/buys", params={
        "min_prob": 0.0, "min_return": -1.0, "horizon": 60}).json()
    assert buys60["run"]["horizon_days"] == 60
    # unknown horizon falls back to the newest run instead of going empty
    movers99 = multi_client.get(
        "/api/movers", params={"min_price": 0, "horizon": 99}).json()
    assert movers99["run"] is not None


def test_detail_lists_every_horizon(multi_client):
    item = multi_client.get(
        "/api/cards", params={"min_price": 0, "limit": 1}).json()["items"][0]
    detail = multi_client.get(f"/api/cards/{item['card_id']}").json()
    listing = next(l for l in detail["listings"] if l["predictions"])
    horizons = [p["horizon_days"] for p in listing["predictions"]]
    assert horizons == sorted(horizons)
    assert set(horizons) == set(config.HORIZONS)
    # `prediction` (max-bid calculator etc.) stays the default horizon
    assert listing["prediction"]["horizon_days"] == config.DEFAULT_HORIZON_DAYS


def test_cli_train_covers_all_horizons(tmp_path, monkeypatch):
    monkeypatch.setenv("POKEPRICE_DATA_DIR", str(tmp_path))
    calls = []

    def fake_train(conn, horizon_days=7, tune=False, min_activity=None,
                   chase=False, log=print):
        calls.append(horizon_days)
        if horizon_days == 60:
            raise model.InsufficientHistory("not enough 60d pairs")
        return {"n_train": 10, "n_valid": 5}

    monkeypatch.setattr(cli.model, "train", fake_train)
    assert cli.main(["train"]) == 0  # one horizon failing is not fatal
    assert calls == list(config.HORIZONS)

    calls.clear()
    assert cli.main(["train", "--horizon", "30"]) == 0
    assert calls == [30]

    def always_fail(conn, **kwargs):
        raise model.InsufficientHistory("nope")

    monkeypatch.setattr(cli.model, "train", always_fail)
    assert cli.main(["train"]) == 1  # every horizon failing is fatal


def test_cli_predict_reports_every_horizon(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("POKEPRICE_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("POKEPRICE_MODEL", raising=False)
    c = db.connect()
    demo.seed(c, n_cards=5, days=15)
    c.close()
    assert cli.main(["predict"]) == 0
    out = capsys.readouterr().out
    for horizon in config.HORIZONS:
        assert f"({horizon}-day horizon" in out
    assert f"Top predicted gainers ({config.DEFAULT_HORIZON_DAYS}d)" in out


def test_one_broken_horizon_does_not_kill_the_others(conn, tmp_path, monkeypatch):
    """A corrupt/unloadable model for one horizon must still leave the other
    horizons' runs in place (and report the failure) — otherwise the dashboard
    silently loses whole horizons and the 'Looking ahead' switch goes dead."""
    monkeypatch.setenv("POKEPRICE_DATA_DIR", str(tmp_path))
    demo.seed(conn, n_cards=8, days=30)
    # a truncated joblib file for the default horizon: load explodes
    config.model_path(config.DEFAULT_HORIZON_DAYS).write_bytes(b"not a model")

    result = model.predict(conn)
    assert {r["horizon_days"] for r in result["runs"]} == {30, 60}
    assert len(result["errors"]) == 1
    assert result["errors"][0]["horizon_days"] == config.DEFAULT_HORIZON_DAYS
    # no half-written run rows for the failed horizon
    assert conn.execute(
        "SELECT COUNT(*) FROM prediction_runs WHERE horizon_days = ?",
        (config.DEFAULT_HORIZON_DAYS,)).fetchone()[0] == 0

    # and everything failing raises with the reasons in the message
    for h in (30, 60):
        config.model_path(h).write_bytes(b"also not a model")
    import pytest as _pytest
    with _pytest.raises(RuntimeError, match="Every horizon failed"):
        model.predict(conn)
