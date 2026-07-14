"""Train and apply the price-movement model.

The trained bundle holds four gradient-boosted models over the features in
`features.py`, all evaluated on a time-ordered holdout so metrics reflect
genuine forecasting:

* median return regressor (the headline "predicted move")
* 10th / 90th percentile quantile regressors (the uncertainty range —
  "worst case still positive" is a rankable, honest buy signal)
* direction classifier P(up), plus a big-move classifier P(gain >= +10%)

When the database doesn't yet hold enough history to build labels, `predict`
falls back to a transparent momentum heuristic tagged `model_kind="momentum"`.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
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
QUANTILES = (0.1, 0.9)


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
    reg_low: HistGradientBoostingRegressor | None = None
    reg_high: HistGradientBoostingRegressor | None = None
    clf_gain: HistGradientBoostingClassifier | None = None
    feature_names: list = field(default_factory=list)


ENSEMBLE_SEEDS = (7, 17, 27)

DEFAULT_PARAMS = dict(learning_rate=0.06, max_leaf_nodes=31,
                      min_samples_leaf=20, l2_regularization=1.0)

# small, sane grid for --tune; evaluated by rank IC on an inner time split
TUNE_GRID = [
    DEFAULT_PARAMS,
    dict(learning_rate=0.10, max_leaf_nodes=31, min_samples_leaf=20, l2_regularization=1.0),
    dict(learning_rate=0.03, max_leaf_nodes=31, min_samples_leaf=20, l2_regularization=1.0),
    dict(learning_rate=0.06, max_leaf_nodes=63, min_samples_leaf=10, l2_regularization=1.0),
    dict(learning_rate=0.06, max_leaf_nodes=31, min_samples_leaf=40, l2_regularization=3.0),
    dict(learning_rate=0.10, max_leaf_nodes=15, min_samples_leaf=20, l2_regularization=1.0),
]


class _AvgReg:
    """Average of same-model fits over different seeds (variance reduction)."""

    def __init__(self, models):
        self.models = models

    def predict(self, X):
        return np.mean([m.predict(X) for m in self.models], axis=0)


class _AvgClf:
    def __init__(self, models):
        self.models = models

    def predict_proba(self, X):
        return np.mean([m.predict_proba(X) for m in self.models], axis=0)


def _hgb(kind: str, params: dict | None = None, seed: int = 7, **kw):
    cls = HistGradientBoostingRegressor if kind == "reg" else HistGradientBoostingClassifier
    return cls(
        max_iter=kw.pop("max_iter", 300),
        early_stopping=True,
        validation_fraction=0.15,
        random_state=seed,
        **{**DEFAULT_PARAMS, **(params or {})},
        **kw,
    )


def build_training_frame(conn: sqlite3.Connection, horizon_days: int) -> pd.DataFrame:
    df = features.load_frame(conn)
    if df.empty:
        return df
    df = features.add_features(df, events=features.load_events(conn))
    df = features.add_labels(df, horizon_days)
    df = df[df["price"] >= config.MIN_PRICE]
    return df.dropna(subset=["label"])


def fit_bundle(df_train: pd.DataFrame, horizon_days: int,
               params: dict | None = None,
               seeds: tuple = ENSEMBLE_SEEDS) -> tuple[Bundle, tuple]:
    """Fit all models on an already-labeled frame; returns (bundle, matrix builder state).

    The point-estimate models are seed-ensembles (averaged); the quantile
    models are single fits — their job is the range, not the ranking.
    """
    y = df_train["label"].clip(*LABEL_CLIP).to_numpy()
    X, feature_names, cat_indices, cat_maps = features.build_matrix(df_train)

    regs = []
    for seed in seeds:
        r = _hgb("reg", params, seed, loss="absolute_error", max_iter=400,
                 categorical_features=cat_indices)
        r.fit(X, y)
        regs.append(r)
    reg = _AvgReg(regs) if len(regs) > 1 else regs[0]

    reg_low = _hgb("reg", params, seeds[0], loss="quantile", quantile=QUANTILES[0],
                   categorical_features=cat_indices)
    reg_low.fit(X, y)
    reg_high = _hgb("reg", params, seeds[0], loss="quantile", quantile=QUANTILES[1],
                    categorical_features=cat_indices)
    reg_high.fit(X, y)

    clf = clf_gain = None
    up = (y > 0).astype(int)
    if len(np.unique(up)) == 2:
        members = []
        for seed in seeds:
            c = _hgb("clf", params, seed, categorical_features=cat_indices)
            c.fit(X, up)
            members.append(c)
        clf = _AvgClf(members) if len(members) > 1 else members[0]
    big = (y >= config.BIG_GAIN).astype(int)
    if len(np.unique(big)) == 2:
        members = []
        for seed in seeds:
            c = _hgb("clf", params, seed, categorical_features=cat_indices)
            c.fit(X, big)
            members.append(c)
        clf_gain = _AvgClf(members) if len(members) > 1 else members[0]

    bundle = Bundle(
        regressor=reg, classifier=clf, cat_maps=cat_maps,
        horizon_days=horizon_days, metrics={}, trained_at=_now(),
        reg_low=reg_low, reg_high=reg_high, clf_gain=clf_gain,
        feature_names=list(feature_names),
    )
    return bundle, (feature_names, cat_indices)


def tune_params(df_train: pd.DataFrame, horizon_days: int, log=print) -> tuple[dict, list]:
    """Pick TUNE_GRID params by rank IC on an inner time split of the train set."""
    dates = df_train["snapshot_date"]
    inner_cutoff = dates.quantile(0.8)
    inner_train = df_train[dates <= inner_cutoff]
    inner_valid = df_train[dates > inner_cutoff]
    if len(inner_train) < MIN_TRAIN_ROWS or len(inner_valid) < 30:
        return dict(DEFAULT_PARAMS), []
    y_valid = inner_valid["label"].clip(*LABEL_CLIP).to_numpy()
    results = []
    for params in TUNE_GRID:
        bundle, _ = fit_bundle(inner_train, horizon_days, params=params,
                               seeds=(ENSEMBLE_SEEDS[0],))
        pred = apply_bundle(bundle, inner_valid)["predicted"]
        ic = _spearman(pred, y_valid) or -1.0
        results.append({"params": params, "ic": round(ic, 4)})
        log(f"  tune {params}: IC {ic:.4f}")
    best = max(results, key=lambda r: r["ic"])
    return dict(best["params"]), results


def apply_bundle(bundle: Bundle, df: pd.DataFrame) -> dict[str, np.ndarray]:
    X, _, _, _ = features.build_matrix(df, cat_maps=bundle.cat_maps)
    predicted = bundle.regressor.predict(X)
    out = {"predicted": predicted}
    out["low"] = bundle.reg_low.predict(X) if bundle.reg_low is not None else predicted - 0.08
    out["high"] = bundle.reg_high.predict(X) if bundle.reg_high is not None else predicted + 0.08
    # quantile models are fit independently; enforce low <= median <= high
    out["low"] = np.minimum(out["low"], predicted)
    out["high"] = np.maximum(out["high"], predicted)
    if bundle.classifier is not None:
        out["prob_up"] = bundle.classifier.predict_proba(X)[:, 1]
    else:
        out["prob_up"] = 0.5 + 0.35 * np.tanh(2.5 * predicted)
    if bundle.clf_gain is not None:
        out["prob_gain"] = bundle.clf_gain.predict_proba(X)[:, 1]
    else:
        out["prob_gain"] = np.clip(out["prob_up"] - 0.3, 0.02, 0.9)
    return out


def train(
    conn: sqlite3.Connection,
    horizon_days: int = config.DEFAULT_HORIZON_DAYS,
    model_file: Path | None = None,
    tune: bool = False,
    log=print,
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
    dates = df["snapshot_date"]
    cutoff = dates.quantile(0.8)
    train_mask = (dates <= cutoff).to_numpy()
    if train_mask.all() or not train_mask.any():
        split = int(len(df) * 0.8)
        train_mask = np.arange(len(df)) < split

    params, tune_results = (tune_params(df[train_mask], horizon_days, log=log)
                            if tune else (None, []))
    bundle, _ = fit_bundle(df[train_mask], horizon_days, params=params)
    valid = df[~train_mask]
    yva = valid["label"].clip(*LABEL_CLIP).to_numpy()
    preds = apply_bundle(bundle, valid)
    pred_va = preds["predicted"]
    nonzero = yva != 0
    covered = (yva >= preds["low"]) & (yva <= preds["high"])
    big_actual = (yva >= config.BIG_GAIN).astype(int)
    metrics = {
        "n_train": int(train_mask.sum()),
        "n_valid": int((~train_mask).sum()),
        "valid_from": str(pd.Timestamp(cutoff).date()),
        "mae": float(np.mean(np.abs(pred_va - yva))),
        "baseline_mae": float(np.mean(np.abs(yva))),
        "direction_accuracy": float(
            np.mean((pred_va[nonzero] > 0) == (yva[nonzero] > 0))
        ) if nonzero.any() else None,
        "spearman_ic": _spearman(pred_va, yva),
        "interval_coverage": float(np.mean(covered)),  # target ~0.8 for q10-q90
        "big_gain_threshold": config.BIG_GAIN,
        "big_gain_base_rate": float(np.mean(big_actual)),
        "big_gain_auc": _auc(preds["prob_gain"], big_actual),
        "features": bundle.feature_names,
        "params": params or dict(DEFAULT_PARAMS),
        "tune_results": tune_results,
    }
    bundle.metrics = metrics
    joblib.dump(bundle, model_file or config.model_path())
    return metrics


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _spearman(a, b) -> float | None:
    s = pd.Series(a).corr(pd.Series(b), method="spearman")
    return None if pd.isna(s) else float(s)


def _auc(scores, labels) -> float | None:
    if len(np.unique(labels)) < 2:
        return None
    from sklearn.metrics import roc_auc_score

    return float(roc_auc_score(labels, scores))


def _momentum_scores(latest: pd.DataFrame) -> dict[str, np.ndarray]:
    """Heuristic used before a model exists: blended recent momentum, damped."""
    short = latest["ret_7d"].fillna(latest["mom_avg_short"]).fillna(0.0).clip(-1, 1)
    med = latest["ret_30d"].fillna(latest["mom_avg_med"]).fillna(0.0).clip(-1, 1)
    score = 0.6 * short + 0.4 * med
    predicted = np.clip(0.4 * score, -0.3, 0.3).to_numpy()
    prob_up = (0.5 + 0.35 * np.tanh(2.5 * score)).to_numpy()
    return {
        "predicted": predicted,
        "low": predicted - 0.08,
        "high": predicted + 0.08,
        "prob_up": prob_up,
        "prob_gain": np.clip(prob_up - 0.3, 0.02, 0.9),
    }


def load_bundle(path: Path | None = None) -> Bundle | None:
    p = path or config.model_path()
    if not p.exists():
        return None
    bundle = joblib.load(p)
    # A bundle trained before a feature-set change can't score today's matrix.
    current = features.NUM_FEATURES + features.CAT_FEATURES
    if getattr(bundle, "feature_names", None) and bundle.feature_names != current:
        return None
    return bundle


def predict(
    conn: sqlite3.Connection,
    horizon_days: int | None = None,
    model_file: Path | None = None,
) -> dict:
    """Score the latest snapshot of every listing and persist a prediction run."""
    df = features.load_frame(conn)
    if df.empty:
        raise RuntimeError("No price data. Run `pokeprice ingest` or `pokeprice fetch` first.")
    df = features.add_features(df, events=features.load_events(conn))
    latest = features.latest_rows(df)
    latest = latest[latest["price"] >= config.MIN_PRICE]
    if latest.empty:
        raise RuntimeError(f"No listings priced >= {config.MIN_PRICE}.")

    bundle = load_bundle(model_file)
    if bundle is not None:
        horizon = horizon_days or bundle.horizon_days
        scores = apply_bundle(bundle, latest)
        model_kind = "gbm"
        metrics = bundle.metrics
    else:
        horizon = horizon_days or config.DEFAULT_HORIZON_DAYS
        scores = _momentum_scores(latest)
        model_kind = "momentum"
        metrics = {"note": "momentum heuristic — train a model once history accumulates"}

    as_of = str(latest["snapshot_date"].max().date())
    cur = conn.execute(
        "INSERT INTO prediction_runs (created_at, model_kind, horizon_days, as_of, metrics) "
        "VALUES (?, ?, ?, ?, ?)",
        (_now(), model_kind, int(horizon), as_of, json.dumps(metrics)),
    )
    run_id = cur.lastrowid
    rows = [
        (
            run_id, r.card_id, r.source, r.variant, float(r.price),
            float(scores["predicted"][i]), float(scores["prob_up"][i]),
            float(scores["low"][i]), float(scores["high"][i]),
            float(scores["prob_gain"][i]),
        )
        for i, r in enumerate(latest.itertuples())
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO predictions "
        "(run_id, card_id, source, variant, price, predicted_return, prob_up, "
        " predicted_low, predicted_high, prob_gain) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
