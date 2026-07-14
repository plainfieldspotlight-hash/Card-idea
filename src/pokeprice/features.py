"""Feature engineering over irregular price-snapshot series.

Each row of the model frame is one observation of one listing — a
(card, source, variant) series — on one snapshot date. Trailing features only
use data at or before that date; the label is the forward return to the
snapshot nearest `horizon` days later. Lookups tolerate irregular spacing
(snapshots rarely land exactly N days apart) via nearest-match windows that
can never touch the current row, so there is no look-ahead leakage.
"""
from __future__ import annotations

import sqlite3

import numpy as np
import pandas as pd

GROUP_KEYS = ["card_id", "source", "variant"]

NUM_FEATURES = [
    "log_price",        # price level (log)
    "ret_1d",           # trailing returns over ~1/7/30 days
    "ret_7d",
    "ret_30d",
    "vol",              # std of log-return over recent snapshots
    "spread",           # (high - low) / price, a liquidity/uncertainty proxy
    "mom_avg_short",    # cardmarket avg1/avg7 - 1 (embedded short momentum)
    "mom_avg_med",      # cardmarket avg7/avg30 - 1
    "price_vs_avg30",   # price relative to its 30-day average
    "set_age_days",     # how old the card's set is at observation time
    "n_hist",           # how many prior snapshots this listing has
]
CAT_FEATURES = ["rarity", "supertype", "source", "variant"]
ALL_FEATURES = NUM_FEATURES + CAT_FEATURES


def load_frame(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query(
        """
        SELECT s.card_id, s.source, s.variant, s.snapshot_date, s.currency,
               s.market, s.low, s.mid, s.high, s.avg1, s.avg7, s.avg30,
               c.name, c.set_name, c.rarity, c.supertype, c.set_release_date
        FROM price_snapshots s JOIN cards c USING (card_id)
        """,
        conn,
    )
    if df.empty:
        return df
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"], errors="coerce")
    df = df.dropna(subset=["snapshot_date"])
    price = df["market"].fillna(df["mid"])
    price = price.fillna((df["low"] + df["high"]) / 2).fillna(df["low"])
    df["price"] = pd.to_numeric(price, errors="coerce")
    df = df[df["price"] > 0]
    df = df.sort_values("snapshot_date").reset_index(drop=True)
    return df


def _asof_price(df: pd.DataFrame, offset_days: float, tolerance_days: float,
                out_col: str) -> pd.Series:
    """Price of the same listing ~offset_days away (negative = past), aligned to df."""
    left = df[GROUP_KEYS + ["snapshot_date"]].copy()
    left["row_id"] = np.arange(len(df))
    left["target_date"] = left["snapshot_date"] + pd.Timedelta(days=offset_days)
    right = df[GROUP_KEYS + ["snapshot_date", "price"]].rename(
        columns={"snapshot_date": "match_date", "price": out_col}
    )
    merged = pd.merge_asof(
        left.sort_values("target_date"),
        right.sort_values("match_date"),
        left_on="target_date",
        right_on="match_date",
        by=GROUP_KEYS,
        direction="nearest",
        tolerance=pd.Timedelta(days=tolerance_days),
    )
    return merged.set_index("row_id")[out_col].reindex(np.arange(len(df)))


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("snapshot_date").reset_index(drop=True)
    df["log_price"] = np.log1p(df["price"])

    # Trailing returns. tolerance < 0.5 * window keeps the match strictly in the
    # past (can never resolve to the row's own date).
    for days, col in ((1, "ret_1d"), (7, "ret_7d"), (30, "ret_30d")):
        past = _asof_price(df, -days, tolerance_days=max(0.45, days * 0.45), out_col="p")
        df[col] = df["price"] / past.to_numpy() - 1.0

    grouped = df.groupby(GROUP_KEYS, sort=False)
    dlog = grouped["log_price"].diff()
    df["vol"] = (
        dlog.groupby([df[k] for k in GROUP_KEYS], sort=False)
        .transform(lambda s: s.rolling(8, min_periods=3).std())
    )
    df["n_hist"] = grouped.cumcount()

    df["spread"] = np.where(
        df["price"] > 0, (df["high"] - df["low"]) / df["price"], np.nan
    )
    df["mom_avg_short"] = df["avg1"] / df["avg7"] - 1.0
    df["mom_avg_med"] = df["avg7"] / df["avg30"] - 1.0
    df["price_vs_avg30"] = df["price"] / df["avg30"] - 1.0

    release = pd.to_datetime(df["set_release_date"], errors="coerce")
    df["set_age_days"] = (df["snapshot_date"] - release).dt.days.astype("float64")

    for col in CAT_FEATURES:
        df[col] = df[col].fillna("Unknown").astype(str)
    return df


def add_labels(df: pd.DataFrame, horizon_days: int) -> pd.DataFrame:
    """Forward return over ~horizon_days; NaN when no later snapshot lands in window."""
    fwd = _asof_price(df, horizon_days, tolerance_days=horizon_days * 0.5, out_col="fwd")
    df = df.copy()
    df["label"] = fwd.to_numpy() / df["price"] - 1.0
    return df


def latest_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Most recent observation per listing — the rows predictions are made for."""
    return df.loc[df.groupby(GROUP_KEYS, sort=False)["snapshot_date"].idxmax()]


def build_matrix(
    df: pd.DataFrame, cat_maps: dict[str, list] | None = None
) -> tuple[np.ndarray, list[str], list[int], dict[str, list]]:
    """DataFrame -> float matrix for HistGradientBoosting.

    Categorical columns become integer codes (NaN for unseen values at predict
    time). `cat_maps` fixes the category vocabulary from training.
    """
    fitted = cat_maps is None
    cat_maps = dict(cat_maps or {})
    cols: list[np.ndarray] = []
    for col in NUM_FEATURES:
        arr = pd.to_numeric(df[col], errors="coerce").to_numpy(dtype="float64", copy=True)
        arr[~np.isfinite(arr)] = np.nan
        if np.isnan(arr).all():
            # sklearn's HGB binner crashes on fully-NaN columns; a constant
            # column is safely ignored by the trees instead.
            arr = np.zeros(len(arr))
        cols.append(arr)
    for col in CAT_FEATURES:
        values = df[col].astype(str)
        if fitted:
            cat_maps[col] = sorted(values.unique().tolist())
        code_map = {c: float(i) for i, c in enumerate(cat_maps[col])}
        codes = values.map(code_map).to_numpy(dtype="float64", na_value=np.nan)
        cols.append(codes)
    X = np.column_stack(cols) if cols else np.empty((len(df), 0))
    cat_indices = list(range(len(NUM_FEATURES), len(NUM_FEATURES) + len(CAT_FEATURES)))
    return X, ALL_FEATURES, cat_indices, cat_maps
