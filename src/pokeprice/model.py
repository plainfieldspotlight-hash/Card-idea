"""Train and apply the price-movement model.

Primary model: two gradient-boosted trees (return regressor + direction
classifier) over the features in `features.py`, evaluated on a time-ordered
holdout so the metrics reflect genuine forecasting, not interpolation.

When the database doesn't yet hold enough history to build labels (e.g. a
single bulk ingest = one snapshot date), `predict` falls back to a transparent
momentum heuristic so the app still ranks likely movers — clearly tagged
`model_kind="momentum"` everywhere it surfaces.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import (
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
)

from . import config, features

LABEL_CLIP = (-0.9, 3.0)  # tame the fat tails so single spikes don't own the loss
MIN_TRAIN_ROWS = 150


class InsufficientHistory(RuntimeError):
    """Raised when there aren't enough labeled observations to train."""


@dataclass
class Bundle:
    regressor: HistGradientBoostingRegressor
    classifier: HistGradientBoostingClassifier | None
    cat_maps: dict
    horizon_days: int
    metrics: dict
    trained_at: str


def build_training_frame(conn: sqlite3.Connection, horizon_days: int) -> pd.DataFrame:
    df = features.load_frame(conn)
    if df.empty:
        return df
    df = features.add_features(df)
    df = features.add_labels(df, horizon_days)
    df = df[df["price"] >= config.MIN_PRICE]
    return df.dropna(subset=["label"])


def train(
    conn: sqlite3.Connection,
    horizon_days: int = config.DEFAULT_HORIZON_DAYS,
    model_file: Path | None = None,
) -> dict:
    df = build_training_frame(conn, horizon_days)
    if len(df) < MIN_TRAIN_ROWS:
        raise InsufficientHistory(
            f"Only {len(df)} labeled observations (need >= {MIN_TRAIN_ROWS}). "
            f"Labels require two snapshots of the same listing ~{horizon_days} days "
            "apart — keep running `pokeprice fetch` (or ingest dumps from different "
            "dates) and train again. `pokeprice predict` still works meanwhile via "
            "the momentum fallback."
        )

    df = df.sort_values("snapshot_date")
    y = df["label"].clip(*LABEL_CLIP).to_numpy()

    # Time-ordered split: train on the past, validate on the most recent ~20%
    # of observation dates.
    dates = df["snapshot_date"]
    cutoff = dates.quantile(0.8)
    train_mask = (dates <= cutoff).to_numpy()
    if train_mask.all() or not train_mask.any():
        split = int(len(df) * 0.8)
        train_mask = np.arange(len(df)) < split

    X, feature_names, cat_indices, cat_maps = features.build_matrix(df)
    Xtr, ytr = X[train_mask], y[train_mask]
    Xva, yva = X[~train_mask], y[~train_mask]

    reg = HistGradientBoostingRegressor(
        loss="absolute_error",
        max_iter=400,
        learning_rate=0.06,
        max_leaf_nodes=31,
        min_samples_leaf=20,
        l2_regularization=1.0,
        categorical_features=cat_indices,
        early_stopping=True,
        validation_fraction=0.15,
        random_state=7,
    )
    reg.fit(Xtr, ytr)

    up_tr = (ytr > 0).astype(int)
    clf = None
    if len(np.unique(up_tr)) == 2:
        clf = HistGradientBoostingClassifier(
            max_iter=300,
            learning_rate=0.06,
            max_leaf_nodes=31,
            min_samples_leaf=20,
            l2_regularization=1.0,
            categorical_features=cat_indices,
            early_stopping=True,
            validation_fraction=0.15,
            random_state=7,
        )
        clf.fit(Xtr, up_tr)

    pred_va = reg.predict(Xva)
    nonzero = yva != 0
    metrics = {
        "n_train": int(train_mask.sum()),
        "n_valid": int((~train_mask).sum()),
        "valid_from": str(pd.Timestamp(cutoff).date()),
        "mae": float(np.mean(np.abs(pred_va - yva))),
        "baseline_mae": float(np.mean(np.abs(yva))),  # predict-zero baseline
        "direction_accuracy": float(
            np.mean((pred_va[nonzero] > 0) == (yva[nonzero] > 0))
        ) if nonzero.any() else None,
        "spearman_ic": _spearman(pred_va, yva),
        "features": feature_names,
    }
    bundle = Bundle(
        regressor=reg,
        classifier=clf,
        cat_maps=cat_maps,
        horizon_days=horizon_days,
        metrics=metrics,
        trained_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    joblib.dump(bundle, model_file or config.model_path())
    return metrics


def _spearman(a, b) -> float | None:
    s = pd.Series(a).corr(pd.Series(b), method="spearman")
    return None if pd.isna(s) else float(s)


def _momentum_scores(latest: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Heuristic used before a model exists: blended recent momentum, damped."""
    short = latest["ret_7d"].fillna(latest["mom_avg_short"]).fillna(0.0).clip(-1, 1)
    med = latest["ret_30d"].fillna(latest["mom_avg_med"]).fillna(0.0).clip(-1, 1)
    score = 0.6 * short + 0.4 * med
    predicted = np.clip(0.4 * score, -0.3, 0.3)
    prob_up = 0.5 + 0.35 * np.tanh(2.5 * score)
    return predicted.to_numpy(), prob_up.to_numpy()


def predict(
    conn: sqlite3.Connection,
    horizon_days: int | None = None,
    model_file: Path | None = None,
) -> dict:
    """Score the latest snapshot of every listing and persist a prediction run."""
    df = features.load_frame(conn)
    if df.empty:
        raise RuntimeError("No price data. Run `pokeprice ingest` or `pokeprice fetch` first.")
    df = features.add_features(df)
    latest = features.latest_rows(df)
    latest = latest[latest["price"] >= config.MIN_PRICE]
    if latest.empty:
        raise RuntimeError(f"No listings priced >= {config.MIN_PRICE}.")

    bundle: Bundle | None = None
    path = model_file or config.model_path()
    if path.exists():
        bundle = joblib.load(path)

    if bundle is not None:
        horizon = horizon_days or bundle.horizon_days
        X, _, _, _ = features.build_matrix(latest, cat_maps=bundle.cat_maps)
        predicted = bundle.regressor.predict(X)
        if bundle.classifier is not None:
            prob_up = bundle.classifier.predict_proba(X)[:, 1]
        else:
            prob_up = 0.5 + 0.35 * np.tanh(2.5 * predicted)
        model_kind = "gbm"
        metrics = bundle.metrics
    else:
        horizon = horizon_days or config.DEFAULT_HORIZON_DAYS
        predicted, prob_up = _momentum_scores(latest)
        model_kind = "momentum"
        metrics = {"note": "momentum heuristic — train a model once history accumulates"}

    as_of = str(latest["snapshot_date"].max().date())
    created = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cur = conn.execute(
        "INSERT INTO prediction_runs (created_at, model_kind, horizon_days, as_of, metrics) "
        "VALUES (?, ?, ?, ?, ?)",
        (created, model_kind, int(horizon), as_of, json.dumps(metrics)),
    )
    run_id = cur.lastrowid
    rows = [
        (
            run_id,
            r.card_id,
            r.source,
            r.variant,
            float(r.price),
            float(pred),
            float(prob),
        )
        for r, pred, prob in zip(latest.itertuples(), predicted, prob_up)
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO predictions "
        "(run_id, card_id, source, variant, price, predicted_return, prob_up) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return {
        "run_id": run_id,
        "model_kind": model_kind,
        "horizon_days": int(horizon),
        "as_of": as_of,
        "listings_scored": len(rows),
    }
