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
    "set_mom_7d",       # same-day 7d momentum of the rest of the set (leave-one-out)
    "char_mom_7d",      # ... of other cards of the same character (all Charizards move together)
    "event_recency",    # days since the latest matching hype event (reprints, tournaments)
    "market_mom_7d",    # same-day 7d momentum of the whole tracked market (leave-one-out)
    "ret_7d_rank",      # cross-sectional percentile of ret_7d on this date (relative momentum)
    "ret_30d_rank",
    "mom_vol_adj",      # risk-adjusted momentum: ret_7d / volatility
    "range_pos",        # where price sits in its recent min..max range (0 = low, 1 = high)
]
CAT_FEATURES = ["rarity", "supertype", "source", "variant"]
ALL_FEATURES = NUM_FEATURES + CAT_FEATURES


def load_frame(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query(
        """
        SELECT s.card_id, s.source, s.variant, s.snapshot_date, s.currency,
               s.market, s.low, s.mid, s.high, s.avg1, s.avg7, s.avg30,
               c.name, c.set_id, c.set_name, c.rarity, c.supertype, c.set_release_date
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


def load_events(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT event_date, note, match FROM events ORDER BY event_date")]


def _loo_mean(df: pd.DataFrame, key: pd.Series, values: pd.Series) -> np.ndarray:
    """Same-date mean of `values` over the key group, excluding the row itself."""
    grp = values.groupby([key, df["snapshot_date"]], sort=False)
    total = grp.transform("sum")
    count = grp.transform("count")
    own = values.fillna(0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        loo = np.where(
            values.notna(),
            np.where(count > 1, (total - own) / (count - 1), np.nan),
            np.where(count > 0, total / count, np.nan),
        )
    return loo


def add_features(df: pd.DataFrame, events: list[dict] | None = None) -> pd.DataFrame:
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

    # Cross-card momentum: how the rest of the set / character / market moved.
    set_key = df["set_id"].fillna(df["set_name"]).fillna("?").astype(str)
    character = (
        df["name"].fillna("?").astype(str).str.split().str[0].str.lower()
    )
    df["set_mom_7d"] = _loo_mean(df, set_key, df["ret_7d"])
    df["char_mom_7d"] = _loo_mean(df, character, df["ret_7d"])
    df["market_mom_7d"] = _loo_mean(
        df, pd.Series("all", index=df.index), df["ret_7d"])

    # Relative momentum: a +5% week means something different when everything
    # rallied vs when the market was flat — ranks capture that directly.
    df["ret_7d_rank"] = df.groupby("snapshot_date")["ret_7d"].rank(pct=True)
    df["ret_30d_rank"] = df.groupby("snapshot_date")["ret_30d"].rank(pct=True)
    df["mom_vol_adj"] = df["ret_7d"] / (df["vol"] + 0.01)

    # Position inside the recent trading range (rolling last ~30 snapshots).
    grouped_price = df.groupby(GROUP_KEYS, sort=False)["price"]
    rmin = grouped_price.transform(lambda s: s.rolling(30, min_periods=5).min())
    rmax = grouped_price.transform(lambda s: s.rolling(30, min_periods=5).max())
    span = rmax - rmin
    df["range_pos"] = np.where(span > 0, (df["price"] - rmin) / span, np.nan)

    # Hype events (reprint news, tournament results, ...): days since the most
    # recent event whose match string appears in the card name, capped at 90.
    df["event_recency"] = np.nan
    for ev in events or []:
        ev_date = pd.to_datetime(ev.get("event_date"), errors="coerce")
        match = str(ev.get("match") or "").strip().lower()
        if pd.isna(ev_date) or not match:
            continue
        hits = df["name"].str.lower().str.contains(match, regex=False, na=False)
        delta = (df["snapshot_date"] - ev_date).dt.days.astype("float64")
        applicable = hits & (delta >= 0) & (delta <= 90)
        df.loc[applicable, "event_recency"] = np.fmin(
            df.loc[applicable, "event_recency"], delta[applicable]
        )

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
