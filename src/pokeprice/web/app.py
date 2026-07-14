"""Dashboard web app: JSON API + static frontend."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import config, db, ebay


class HoldingIn(BaseModel):
    card_id: str
    source: str
    variant: str = "normal"
    quantity: float = Field(1, gt=0)
    cost_basis: float | None = Field(None, ge=0, description="paid per card")

STATIC_DIR = Path(__file__).parent / "static"

SORTS = {
    "predicted": "p.predicted_return",
    "prob": "p.prob_up",
    "price": "l.price",
    "change7": "change7",
    "name": "c.name",
    "date": "l.snapshot_date",
}

# High-confidence buy tiers: (key, label, min_exclusive, max_inclusive)
BUY_TIERS = [
    ("over-1000", "Over $1,000", 1000.0, None),
    ("500-1000", "$500 – $1,000", 500.0, 1000.0),
    ("100-500", "$100 – $500", 100.0, 500.0),
    ("under-100", "$100 or less", None, 100.0),
]

LATEST_LISTINGS_CTE = """
WITH latest AS (
    SELECT s.*, ROW_NUMBER() OVER (
        PARTITION BY s.card_id, s.source, s.variant
        ORDER BY s.snapshot_date DESC
    ) AS rn,
    COALESCE(s.market, s.mid, (s.low + s.high) / 2.0, s.low) AS price
    FROM price_snapshots s
),
run AS (SELECT run_id FROM prediction_runs ORDER BY run_id DESC LIMIT 1)
"""


def _downsample(points: list, limit: int = 40) -> list:
    if len(points) <= limit:
        return points
    step = (len(points) - 1) / (limit - 1)
    return [points[round(i * step)] for i in range(limit)]


def create_app(db_path: Path | str | None = None) -> FastAPI:
    app = FastAPI(title="pokeprice", version="0.1.0")
    resolved_db = Path(db_path) if db_path else config.db_path()

    def conn() -> sqlite3.Connection:
        return db.connect(resolved_db)

    @app.get("/api/stats")
    def api_stats():
        c = conn()
        try:
            payload = db.stats(c)
            if payload["latest_run"] and payload["latest_run"].get("metrics"):
                payload["latest_run"]["metrics"] = json.loads(payload["latest_run"]["metrics"])
            payload["min_price"] = config.MIN_PRICE
            payload["auto_fetch"] = db.get_meta(c, "auto_fetch")
            payload["auto_fetch_last"] = db.get_meta(c, "auto_fetch_last")
            payload["ebay_live"] = ebay.credentials() is not None
            return payload
        finally:
            c.close()

    @app.get("/api/cards")
    def api_cards(
        q: str = "",
        source: str = "",
        sort: str = "predicted",
        direction: str = "desc",
        min_price: float = 0.0,
        limit: int = Query(25, le=200),
        offset: int = 0,
    ):
        order_expr = SORTS.get(sort, SORTS["predicted"])
        order_dir = "ASC" if direction.lower() == "asc" else "DESC"
        where, params = ["l.rn = 1", "l.price >= :min_price"], {
            "min_price": min_price, "limit": limit, "offset": offset,
        }
        if q:
            where.append("(c.name LIKE :q OR c.set_name LIKE :q OR c.card_id LIKE :q)")
            params["q"] = f"%{q}%"
        if source:
            where.append("l.source = :source")
            params["source"] = source
        sql = f"""
        {LATEST_LISTINGS_CTE}
        SELECT c.card_id, c.name, c.set_name, c.rarity, c.image_small,
               l.source, l.variant, l.currency, l.snapshot_date, l.price,
               (SELECT COALESCE(p2.market, p2.mid, p2.low) FROM price_snapshots p2
                WHERE p2.card_id = l.card_id AND p2.source = l.source
                  AND p2.variant = l.variant
                  AND p2.snapshot_date <= date(l.snapshot_date, '-6 day')
                ORDER BY p2.snapshot_date DESC LIMIT 1) AS past7,
               l.avg7,
               p.predicted_return, p.prob_up,
               COUNT(*) OVER () AS total
        FROM latest l
        JOIN cards c USING (card_id)
        LEFT JOIN predictions p
               ON p.run_id = (SELECT run_id FROM run)
              AND p.card_id = l.card_id AND p.source = l.source AND p.variant = l.variant
        WHERE {' AND '.join(where)}
        ORDER BY ({order_expr}) IS NULL, {order_expr} {order_dir}, c.name ASC
        LIMIT :limit OFFSET :offset
        """
        c = conn()
        try:
            rows = [dict(r) for r in c.execute(sql, params).fetchall()]
            total = rows[0]["total"] if rows else 0
            keys = [f"{r['card_id']}|{r['source']}|{r['variant']}" for r in rows]
            sparks: dict[str, list] = {k: [] for k in keys}
            if keys:
                placeholders = ",".join("?" for _ in keys)
                hist = c.execute(
                    f"""
                    SELECT card_id || '|' || source || '|' || variant AS key,
                           snapshot_date,
                           COALESCE(market, mid, (low + high) / 2.0, low) AS price
                    FROM price_snapshots
                    WHERE card_id || '|' || source || '|' || variant IN ({placeholders})
                    ORDER BY snapshot_date
                    """,
                    keys,
                ).fetchall()
                for h in hist:
                    if h["price"] is not None:
                        sparks[h["key"]].append([h["snapshot_date"], round(h["price"], 4)])
            items = []
            for r, key in zip(rows, keys):
                r.pop("total", None)
                past = r.pop("past7", None)
                avg7 = r.pop("avg7", None)
                base = past if past else avg7
                r["change7"] = (r["price"] / base - 1.0) if base else None
                r["spark"] = _downsample(sparks[key], 40)
                items.append(r)
            return {"total": total, "items": items}
        finally:
            c.close()

    @app.get("/api/cards/{card_id}")
    def api_card(card_id: str):
        c = conn()
        try:
            card = c.execute("SELECT * FROM cards WHERE card_id = ?", (card_id,)).fetchone()
            if card is None:
                raise HTTPException(404, f"unknown card {card_id}")
            history = c.execute(
                """
                SELECT source, variant, currency, snapshot_date,
                       COALESCE(market, mid, (low + high) / 2.0, low) AS price,
                       low, high, avg7, avg30
                FROM price_snapshots WHERE card_id = ? ORDER BY snapshot_date
                """,
                (card_id,),
            ).fetchall()
            listings: dict[tuple, dict] = {}
            for h in history:
                key = (h["source"], h["variant"])
                entry = listings.setdefault(key, {
                    "source": h["source"], "variant": h["variant"],
                    "currency": h["currency"], "history": [],
                })
                if h["price"] is not None:
                    entry["history"].append([h["snapshot_date"], round(h["price"], 4)])
            preds = c.execute(
                """
                SELECT p.*, r.model_kind, r.horizon_days, r.as_of, r.created_at
                FROM predictions p JOIN prediction_runs r USING (run_id)
                WHERE p.card_id = ?
                  AND p.run_id = (SELECT MAX(run_id) FROM prediction_runs)
                """,
                (card_id,),
            ).fetchall()
            pred_map = {(p["source"], p["variant"]): dict(p) for p in preds}
            out = []
            for key, entry in sorted(listings.items()):
                entry["latest_date"], entry["latest_price"] = (
                    entry["history"][-1] if entry["history"] else (None, None)
                )
                entry["prediction"] = pred_map.get(key)
                entry["ebay_url"] = ebay.search_url(dict(card), entry["variant"])
                out.append(entry)
            return {"card": dict(card), "listings": out}
        finally:
            c.close()

    @app.get("/api/cards/{card_id}/ebay")
    def api_card_ebay(card_id: str, variant: str = "normal", limit: int = Query(5, le=10)):
        """eBay purchase options: always a search link; live listings when
        EBAY_CLIENT_ID/EBAY_CLIENT_SECRET are configured."""
        c = conn()
        try:
            card = c.execute("SELECT * FROM cards WHERE card_id = ?", (card_id,)).fetchone()
            if card is None:
                raise HTTPException(404, f"unknown card {card_id}")
            market = c.execute(
                """
                SELECT COALESCE(market, mid, (low + high) / 2.0, low) AS price, currency
                FROM price_snapshots
                WHERE card_id = ? AND variant = ?
                ORDER BY snapshot_date DESC LIMIT 1
                """,
                (card_id, variant),
            ).fetchone()
        finally:
            c.close()
        payload = {
            "mode": "live" if ebay.credentials() else "link",
            "search_url": ebay.search_url(dict(card), variant),
            "market_price": market["price"] if market else None,
            "market_currency": market["currency"] if market else None,
            "items": [],
        }
        if payload["mode"] == "live":
            try:
                items = ebay.fetch_listings(dict(card), variant, limit=limit)
                payload["items"] = ebay.annotate_vs_market(
                    items, payload["market_price"], payload["market_currency"])
            except Exception as exc:  # eBay hiccups shouldn't break the panel
                payload["mode"] = "link"
                payload["error"] = f"{type(exc).__name__}: {exc}"
        return payload

    @app.get("/api/collection")
    def api_collection():
        c = conn()
        try:
            rows = [dict(r) for r in c.execute(
                f"""
                {LATEST_LISTINGS_CTE}
                SELECT h.holding_id, h.card_id, h.source, h.variant, h.quantity,
                       h.cost_basis, h.added_at,
                       c.name, c.set_name, c.rarity, c.image_small,
                       l.price, l.currency, l.snapshot_date,
                       p.predicted_return, p.prob_up
                FROM holdings h
                JOIN cards c USING (card_id)
                LEFT JOIN latest l ON l.card_id = h.card_id AND l.source = h.source
                     AND l.variant = h.variant AND l.rn = 1
                LEFT JOIN predictions p ON p.run_id = (SELECT run_id FROM run)
                     AND p.card_id = h.card_id AND p.source = h.source
                     AND p.variant = h.variant
                ORDER BY COALESCE(l.price, 0) * h.quantity DESC
                """
            ).fetchall()]
            value = cost = pred_delta = gain = 0.0
            for r in rows:
                r["value"] = r["price"] * r["quantity"] if r["price"] else None
                r["gain"] = (
                    (r["price"] - r["cost_basis"]) * r["quantity"]
                    if r["price"] is not None and r["cost_basis"] is not None else None
                )
                value += r["value"] or 0.0
                cost += (r["cost_basis"] or 0.0) * r["quantity"] if r["cost_basis"] else 0.0
                gain += r["gain"] or 0.0
                if r["value"] and r["predicted_return"] is not None:
                    pred_delta += r["value"] * r["predicted_return"]
            return {
                "holdings": rows,
                "totals": {
                    "value": value,
                    "cost": cost,
                    "gain": gain,
                    "predicted_delta": pred_delta,
                    "count": len(rows),
                },
            }
        finally:
            c.close()

    @app.post("/api/collection", status_code=201)
    def api_collection_add(holding: HoldingIn):
        c = conn()
        try:
            listing = c.execute(
                "SELECT 1 FROM price_snapshots WHERE card_id = ? AND source = ? AND variant = ? LIMIT 1",
                (holding.card_id, holding.source, holding.variant),
            ).fetchone()
            if listing is None:
                raise HTTPException(
                    404,
                    f"no tracked listing {holding.card_id}/{holding.source}/{holding.variant}",
                )
            cur = c.execute(
                "INSERT INTO holdings (card_id, source, variant, quantity, cost_basis, added_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (holding.card_id, holding.source, holding.variant, holding.quantity,
                 holding.cost_basis,
                 datetime.now(timezone.utc).isoformat(timespec="seconds")),
            )
            c.commit()
            return {"holding_id": cur.lastrowid, **holding.model_dump()}
        finally:
            c.close()

    @app.delete("/api/collection/{holding_id}")
    def api_collection_delete(holding_id: int):
        c = conn()
        try:
            cur = c.execute("DELETE FROM holdings WHERE holding_id = ?", (holding_id,))
            c.commit()
            if cur.rowcount == 0:
                raise HTTPException(404, f"no holding {holding_id}")
            return {"deleted": holding_id}
        finally:
            c.close()

    @app.get("/api/movers")
    def api_movers(limit: int = Query(8, le=50), min_price: float = 1.0):
        c = conn()
        try:
            run = c.execute(
                "SELECT * FROM prediction_runs ORDER BY run_id DESC LIMIT 1"
            ).fetchone()
            if run is None:
                return {"run": None, "gainers": [], "losers": []}
            def side(order: str):
                return [
                    dict(r) for r in c.execute(
                        f"""
                        SELECT p.card_id, c.name, c.set_name, c.rarity, c.image_small,
                               p.source, p.variant, p.price, p.predicted_return, p.prob_up
                        FROM predictions p JOIN cards c USING (card_id)
                        WHERE p.run_id = ? AND p.price >= ?
                        ORDER BY p.predicted_return {order} LIMIT ?
                        """,
                        (run["run_id"], min_price, limit),
                    ).fetchall()
                ]
            run_info = dict(run)
            if run_info.get("metrics"):
                run_info["metrics"] = json.loads(run_info["metrics"])
            return {"run": run_info, "gainers": side("DESC"), "losers": side("ASC")}
        finally:
            c.close()

    @app.get("/api/buys")
    def api_buys(
        min_prob: float = 0.7,
        min_return: float = 0.02,
        per_tier: int = Query(5, le=20),
    ):
        """Highest-conviction upside picks, bucketed into price tiers.

        A listing qualifies when the latest run gives it P(up) >= min_prob AND
        predicted return >= min_return; within each tier the biggest predicted
        gainers rank first. Tiers compare the listed price at face value
        (USD for TCGplayer, EUR for Cardmarket).
        """
        c = conn()
        try:
            run = c.execute(
                "SELECT * FROM prediction_runs ORDER BY run_id DESC LIMIT 1"
            ).fetchone()
            criteria = {"min_prob": min_prob, "min_return": min_return,
                        "per_tier": per_tier}
            tiers = [
                {"key": key, "label": label, "min": lo, "max": hi, "items": []}
                for key, label, lo, hi in BUY_TIERS
            ]
            if run is None:
                return {"run": None, "criteria": criteria, "tiers": tiers}
            rows = c.execute(
                """
                SELECT p.card_id, c.name, c.set_name, c.number, c.rarity, c.image_small,
                       p.source, p.variant, p.price, p.predicted_return, p.prob_up
                FROM predictions p JOIN cards c USING (card_id)
                WHERE p.run_id = ? AND p.prob_up >= ? AND p.predicted_return >= ?
                ORDER BY p.predicted_return DESC, p.prob_up DESC
                """,
                (run["run_id"], min_prob, min_return),
            ).fetchall()
            for r in rows:
                price = r["price"]
                for tier, (_, _, lo, hi) in zip(tiers, BUY_TIERS):
                    if (lo is None or price > lo) and (hi is None or price <= hi):
                        if len(tier["items"]) < per_tier:
                            item = dict(r)
                            item["ebay_url"] = ebay.search_url(item, item["variant"])
                            tier["items"].append(item)
                        break
            run_info = dict(run)
            if run_info.get("metrics"):
                run_info["metrics"] = json.loads(run_info["metrics"])
            return {"run": run_info, "criteria": criteria, "tiers": tiers}
        finally:
            c.close()

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    return app
