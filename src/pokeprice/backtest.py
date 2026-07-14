"""Honest backtest: would trading the model's picks have made money?

Frozen-model walk-forward: train once on the first `train_frac` of history,
then step through the *held-out* remainder — dates the model never saw —
rebalancing every `horizon` days into the top-K picks and selling at the
realized price, minus marketplace fees. No retraining inside the test window,
no peeking. The benchmark is the fee-free average return of every eligible
listing over the same dates (i.e. "just holding the market").
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import config, db, model

DEFAULT_FEE_RATE = 0.1325  # eBay final-value fee ballpark; override per run


def run_backtest(
    conn: sqlite3.Connection,
    capital: float = 500.0,
    top_k: int = 5,
    horizon_days: int | None = None,
    fee_rate: float = DEFAULT_FEE_RATE,
    min_price: float = 1.0,
    max_price: float | None = None,
    train_frac: float = 0.7,
    rank: str = "worst_case",
) -> dict:
    horizon = horizon_days or config.DEFAULT_HORIZON_DAYS
    df = model.build_training_frame(conn, horizon)
    if df.empty or df["snapshot_date"].nunique() < 6:
        raise model.InsufficientHistory(
            "Backtesting needs labeled history across several dates — "
            "accumulate more snapshots first."
        )
    df = df.sort_values("snapshot_date")
    dates = df["snapshot_date"]
    cutoff = dates.quantile(train_frac)
    train_df = df[dates <= cutoff]
    test_df = df[dates > cutoff]
    if len(train_df) < model.MIN_TRAIN_ROWS or test_df.empty:
        raise model.InsufficientHistory(
            f"Not enough history on both sides of the split "
            f"({len(train_df)} train rows, {len(test_df)} test rows)."
        )

    bundle, _ = model.fit_bundle(train_df, horizon)

    test_dates = sorted(test_df["snapshot_date"].unique())
    equity, bench, gross_equity = capital, capital, capital
    curve = [[str(pd.Timestamp(test_dates[0]).date()), round(equity, 2)]]
    bench_curve = [[str(pd.Timestamp(test_dates[0]).date()), round(bench, 2)]]
    periods, picks_log = [], []

    i = 0
    while i < len(test_dates):
        date = test_dates[i]
        pool = test_df[test_df["snapshot_date"] == date]
        pool = pool[pool["price"] >= min_price]
        if max_price is not None:
            pool = pool[pool["price"] <= max_price]
        if len(pool) >= 2:
            scores = model.apply_bundle(bundle, pool)
            key = scores["low"] if rank == "worst_case" else scores["predicted"]
            order = np.argsort(-key)
            picked = pool.iloc[order[:top_k]]
            picked_scores = key[order[:top_k]]
            gross = picked["label"].clip(*model.LABEL_CLIP).to_numpy()
            # buy at market, sell at realized market price minus seller fees
            net = (1.0 + gross) * (1.0 - fee_rate) - 1.0
            period_ret = float(np.mean(net))
            bench_ret = float(pool["label"].clip(*model.LABEL_CLIP).mean())
            equity *= 1.0 + period_ret
            gross_equity *= 1.0 + float(np.mean(gross))
            bench *= 1.0 + bench_ret
            date_str = str(pd.Timestamp(date).date())
            periods.append({"date": date_str, "return": period_ret, "benchmark": bench_ret})
            curve.append([date_str, round(equity, 2)])
            bench_curve.append([date_str, round(bench, 2)])
            picks_log.append({
                "date": date_str,
                "picks": [
                    {"name": r.name_, "card_id": r.card_id, "price": round(float(r.price), 2),
                     "score": round(float(s), 4),
                     "realized": round(float(np.clip(r.label, *model.LABEL_CLIP)), 4)}
                    for r, s in zip(
                        picked.rename(columns={"name": "name_"}).itertuples(), picked_scores
                    )
                ],
            })
        # jump forward one holding period
        target = pd.Timestamp(date) + pd.Timedelta(days=horizon)
        j = i + 1
        while j < len(test_dates) and pd.Timestamp(test_dates[j]) < target:
            j += 1
        i = j

    rets = np.array([p["return"] for p in periods]) if periods else np.array([])
    peak = np.maximum.accumulate([v for _, v in curve])
    drawdowns = 1.0 - np.array([v for _, v in curve]) / peak
    result = {
        "params": {
            "capital": capital, "top_k": top_k, "horizon_days": horizon,
            "fee_rate": fee_rate, "min_price": min_price, "max_price": max_price,
            "train_frac": train_frac, "rank": rank,
        },
        "test_from": str(pd.Timestamp(cutoff).date()),
        "n_periods": len(periods),
        "final_equity": round(equity, 2),
        "total_return": equity / capital - 1.0,
        "gross_return": gross_equity / capital - 1.0,  # picks before fees: is the signal real?
        "benchmark_return": bench / capital - 1.0,
        "win_rate": float(np.mean(rets > 0)) if len(rets) else None,
        "avg_period_return": float(np.mean(rets)) if len(rets) else None,
        "max_drawdown": float(np.max(drawdowns)) if len(drawdowns) else None,
        "equity": curve,
        "benchmark_equity": bench_curve,
        "recent_picks": picks_log[-4:],
        "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": "Frozen-model walk-forward on held-out dates; fees on sells only; "
                "benchmark is the fee-free average of all eligible listings.",
    }
    db.set_meta(conn, "backtest_last", result)
    return result
