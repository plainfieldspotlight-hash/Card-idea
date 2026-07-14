import pytest

from pokeprice import db, demo, model


def test_train_and_predict_gbm(conn, tmp_path):
    demo.seed(conn, n_cards=24, days=90)
    model_file = tmp_path / "model.joblib"
    metrics = model.train(conn, horizon_days=7, model_file=model_file)
    assert model_file.exists()
    assert metrics["n_train"] > 0 and metrics["n_valid"] > 0
    assert 0.0 <= metrics["direction_accuracy"] <= 1.0
    assert metrics["spearman_ic"] is not None

    result = model.predict(conn, model_file=model_file)
    assert result["model_kind"] == "gbm"
    assert result["listings_scored"] > 0
    n = conn.execute(
        "SELECT COUNT(*) FROM predictions WHERE run_id = ?", (result["run_id"],)
    ).fetchone()[0]
    assert n == result["listings_scored"]
    run = conn.execute("SELECT * FROM prediction_runs WHERE run_id = ?",
                       (result["run_id"],)).fetchone()
    assert run["model_kind"] == "gbm"
    assert run["horizon_days"] == 7


def test_insufficient_history_raises(conn, tmp_path):
    demo.seed(conn, n_cards=6, days=4)  # too short for 7-day labels
    with pytest.raises(model.InsufficientHistory):
        model.train(conn, horizon_days=7, model_file=tmp_path / "m.joblib")


def test_momentum_fallback_without_model(conn, tmp_path):
    demo.seed(conn, n_cards=10, days=30)
    result = model.predict(conn, model_file=tmp_path / "missing.joblib")
    assert result["model_kind"] == "momentum"
    assert result["listings_scored"] > 0
    row = conn.execute("SELECT predicted_return, prob_up FROM predictions LIMIT 1").fetchone()
    assert -0.5 <= row["predicted_return"] <= 0.5
    assert 0.0 < row["prob_up"] < 1.0


def test_predict_on_empty_db_errors(conn, tmp_path):
    with pytest.raises(RuntimeError):
        model.predict(conn, model_file=tmp_path / "missing.joblib")


def test_stats(conn):
    demo.seed(conn, n_cards=5, days=10)
    s = db.stats(conn)
    assert s["cards"] == 5
    assert s["snapshots"] > 0
    assert s["latest_run"] is None
