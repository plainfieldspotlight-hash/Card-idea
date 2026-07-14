"""Model report card: score stored predictions against what actually happened.

Every `predict` run is persisted, so once newer snapshots arrive we can join
each prediction to the realized price ~horizon days after its as-of date and
measure live accuracy — overall, by price tier, by rarity, and by model kind.
This is the "when should I trust it" page.
"""
from __future__ import annotations

import sqlite3

import numpy as np
import pandas as pd

TIERS = [
    ("over-1000", "Over $1,000", 1000.0, None),
    ("500-1000", "$500 – $1,000", 500.0, 1000.0),
    ("100-500", "$100 – $500", 100.0, 500.0),
    ("under-100", "$100 or less", None, 100.0),
]

RESOLVED_SQL = """
SELECT p.run_id, p.card_id, p.source, p.variant, p.price,
       p.predicted_return, p.prob_up, p.predicted_low, p.predicted_high, p.prob_gain,
       r.as_of, r.horizon_days, r.model_kind,
       c.name, c.set_name, c.rarity,
       (SELECT price FROM (
            -- SQLite disallows outer refs in a subquery's ORDER BY, so the
            -- distance-to-target is computed as an inner column instead
            SELECT COALESCE(s.market, s.mid, (s.low + s.high) / 2.0, s.low) AS price,
                   ABS(julianday(s.snapshot_date)
                       - (julianday(r.as_of) + r.horizon_days)) AS dist
            FROM price_snapshots s
            WHERE s.card_id = p.card_id AND s.source = p.source AND s.variant = p.variant
              AND julianday(s.snapshot_date) > julianday(r.as_of)
              AND ABS(julianday(s.snapshot_date)
                      - (julianday(r.as_of) + r.horizon_days)) <= r.horizon_days * 0.5
        ) ORDER BY dist LIMIT 1) AS realized_price
FROM predictions p
JOIN prediction_runs r USING (run_id)
JOIN cards c USING (card_id)
"""


def _segment(df: pd.DataFrame) -> dict:
    resolved = df.dropna(subset=["realized_return"])
    if resolved.empty:
        return {"n": int(len(df)), "n_resolved": 0}
    pred = resolved["predicted_return"].to_numpy()
    real = resolved["realized_return"].to_numpy()
    nonzero = real != 0
    out = {
        "n": int(len(df)),
        "n_resolved": int(len(resolved)),
        "hit_rate": float(np.mean((pred[nonzero] > 0) == (real[nonzero] > 0)))
        if nonzero.any() else None,
        "mae": float(np.mean(np.abs(pred - real))),
        "baseline_mae": float(np.mean(np.abs(real))),
        "mean_realized": float(np.mean(real)),
        "spearman_ic": None,
    }
    ic = pd.Series(pred).corr(pd.Series(real), method="spearman")
    out["spearman_ic"] = None if pd.isna(ic) else float(ic)
    if resolved["predicted_low"].notna().any():
        low = resolved["predicted_low"].to_numpy()
        high = resolved["predicted_high"].to_numpy()
        ok = ~np.isnan(low) & ~np.isnan(high)
        if ok.any():
            out["interval_coverage"] = float(
                np.mean((real[ok] >= low[ok]) & (real[ok] <= high[ok]))
            )
    return out


def prediction_report(conn: sqlite3.Connection, recent_limit: int = 15) -> dict:
    df = pd.read_sql_query(RESOLVED_SQL, conn)
    if df.empty:
        return {"overall": {"n": 0, "n_resolved": 0}, "by_tier": [], "by_rarity": [],
                "by_model": [], "recent": []}
    # If the same listing was scored by several runs with the same as-of and
    # horizon, keep the newest run only.
    df = (
        df.sort_values("run_id")
        .drop_duplicates(subset=["card_id", "source", "variant", "as_of", "horizon_days"],
                         keep="last")
        .reset_index(drop=True)
    )
    df["realized_return"] = df["realized_price"] / df["price"] - 1.0

    by_tier = []
    for key, label, lo, hi in TIERS:
        mask = pd.Series(True, index=df.index)
        if lo is not None:
            mask &= df["price"] > lo
        if hi is not None:
            mask &= df["price"] <= hi
        seg = _segment(df[mask])
        seg.update({"key": key, "label": label})
        by_tier.append(seg)

    by_rarity = []
    for rarity, group in df.groupby(df["rarity"].fillna("Unknown")):
        if len(group) < 5:
            continue
        seg = _segment(group)
        seg["label"] = rarity
        by_rarity.append(seg)
    by_rarity.sort(key=lambda s: -(s.get("n_resolved") or 0))

    by_model = []
    for kind, group in df.groupby("model_kind"):
        seg = _segment(group)
        seg["label"] = kind
        by_model.append(seg)

    resolved = df.dropna(subset=["realized_return"]).sort_values("as_of", ascending=False)
    recent = [
        {
            "name": r["name"], "set_name": r["set_name"], "card_id": r["card_id"],
            "source": r["source"], "variant": r["variant"], "as_of": r["as_of"],
            "horizon_days": int(r["horizon_days"]), "price": r["price"],
            "predicted_return": r["predicted_return"],
            "realized_return": r["realized_return"],
            "model_kind": r["model_kind"],
        }
        for _, r in resolved.head(recent_limit).iterrows()
    ]
    return {
        "overall": _segment(df),
        "by_tier": by_tier,
        "by_rarity": by_rarity[:8],
        "by_model": by_model,
        "recent": recent,
    }
