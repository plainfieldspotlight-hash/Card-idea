"""Dashboard web app: JSON API + static frontend."""
from __future__ import annotations

import base64
import json
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import alerts, backtest, config, db, ebay, rates, report
from ..ingest import csv_ingest


class HoldingIn(BaseModel):
    card_id: str
    source: str
    variant: str = "normal"
    quantity: float = Field(1, gt=0)
    cost_basis: float | None = Field(None, ge=0, description="paid per card")


class WatchIn(BaseModel):
    card_id: str
    source: str
    variant: str = "normal"

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

def chase_clause(alias: str = "c") -> str:
    """SQL twin of config.is_chase — money-maker rarities only."""
    ors = " OR ".join(
        f"lower({alias}.rarity) LIKE '%{term}%'" for term in config.CHASE_TERMS)
    return f"({ors})"


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

    @app.middleware("http")
    async def basic_auth(request: Request, call_next):
        """Single-user HTTP Basic auth, enabled by setting POKEPRICE_PASSWORD.

        Meant for hosted deployments; local use stays zero-config."""
        password = os.environ.get("POKEPRICE_PASSWORD")
        if password:
            header = request.headers.get("authorization", "")
            ok = False
            if header.lower().startswith("basic "):
                try:
                    decoded = base64.b64decode(header[6:]).decode()
                    supplied = decoded.split(":", 1)[1] if ":" in decoded else decoded
                    ok = secrets.compare_digest(supplied, password)
                except Exception:
                    ok = False
            if not ok:
                return Response(status_code=401, headers={
                    "WWW-Authenticate": 'Basic realm="pokeprice"'})
        return await call_next(request)

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
        set_id: str = "",
        rarity: str = "",
        chase: int = 0,
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
        # every word in the query must match somewhere: name, set, rarity,
        # finish/variant, marketplace, collector number, or id — so
        # "charizard holo 4" or "pikachu reverse" narrows as you type
        for i, token in enumerate(q.split()[:6]):
            where.append(
                f"(c.name LIKE :q{i} OR c.set_name LIKE :q{i} OR c.rarity LIKE :q{i} "
                f"OR l.variant LIKE :q{i} OR l.source LIKE :q{i} "
                f"OR c.number = :qn{i} OR c.card_id LIKE :q{i})"
            )
            params[f"q{i}"] = f"%{token}%"
            params[f"qn{i}"] = token
        if source:
            where.append("l.source = :source")
            params["source"] = source
        if set_id:
            where.append("c.set_id = :set_id")
            params["set_id"] = set_id
        if rarity:
            where.append("c.rarity = :rarity")
            params["rarity"] = rarity
        if chase:
            where.append(chase_clause("c"))
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
               p.predicted_return, p.prob_up, p.predicted_low, p.predicted_high,
               (w.watch_id IS NOT NULL) AS watched,
               COUNT(*) OVER () AS total
        FROM latest l
        JOIN cards c USING (card_id)
        LEFT JOIN predictions p
               ON p.run_id = (SELECT run_id FROM run)
              AND p.card_id = l.card_id AND p.source = l.source AND p.variant = l.variant
        LEFT JOIN watchlist w
               ON w.card_id = l.card_id AND w.source = l.source AND w.variant = l.variant
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

    @app.get("/api/sets")
    def api_sets():
        """Filter options: every set (newest first) and every rarity in the catalog."""
        c = conn()
        try:
            sets = [dict(r) for r in c.execute(
                """
                SELECT set_id, set_name, COUNT(*) AS cards,
                       MAX(set_release_date) AS release_date
                FROM cards WHERE set_id IS NOT NULL
                GROUP BY set_id, set_name
                ORDER BY release_date DESC, set_name
                """
            ).fetchall()]
            rarities = [r["rarity"] for r in c.execute(
                "SELECT DISTINCT rarity FROM cards WHERE rarity IS NOT NULL ORDER BY rarity"
            ).fetchall()]
            return {"sets": sets, "rarities": rarities}
        finally:
            c.close()

    @app.get("/api/suggest")
    def api_suggest(q: str = "", limit: int = Query(8, le=20)):
        """Autocomplete for the search box (prefix matches first)."""
        if len(q.strip()) < 2:
            return {"suggestions": []}
        c = conn()
        try:
            rows = c.execute(
                """
                SELECT DISTINCT name FROM cards
                WHERE name LIKE :any
                ORDER BY CASE WHEN name LIKE :prefix THEN 0 ELSE 1 END, name
                LIMIT :lim
                """,
                {"any": f"%{q.strip()}%", "prefix": f"{q.strip()}%", "lim": limit},
            ).fetchall()
            return {"suggestions": [r["name"] for r in rows]}
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
            try:
                payload["sold"] = ebay.fetch_sold(dict(card), variant)
            except Exception:
                payload["sold"] = []  # Insights API is approval-gated; degrade quietly
        return payload

    @app.get("/api/report")
    def api_report():
        c = conn()
        try:
            payload = report.prediction_report(c)
            payload["backtest"] = db.get_meta(c, "backtest_last")
            return payload
        finally:
            c.close()

    @app.post("/api/backtest")
    def api_backtest(
        capital: float = 500.0,
        top_k: int = Query(5, ge=1, le=25),
        fee_rate: float = Query(backtest.DEFAULT_FEE_RATE, ge=0, le=0.5),
        min_price: float = 1.0,
        max_price: float | None = None,
        rank: str = "worst_case",
        chase: int = 0,
    ):
        c = conn()
        try:
            return backtest.run_backtest(
                c, capital=capital, top_k=top_k, fee_rate=fee_rate,
                min_price=min_price, max_price=max_price, rank=rank,
                chase=bool(chase),
            )
        except Exception as exc:
            raise HTTPException(400, str(exc))
        finally:
            c.close()

    @app.get("/api/deals")
    def api_deals(
        min_prob: float = 0.7,
        min_return: float = 0.02,
        max_above_market: float = -0.05,
        limit: int = Query(10, le=25),
        chase: int = 0,
    ):
        """Deal radar: model-liked cards crossed with live eBay prices.

        In live mode each candidate's cheapest comparable eBay listing is
        attached when it sits at least |max_above_market| below our tracked
        price. In link mode candidates carry search links only.
        """
        c = conn()
        try:
            run = c.execute(
                "SELECT * FROM prediction_runs ORDER BY run_id DESC LIMIT 1"
            ).fetchone()
            if run is None:
                return {"mode": "none", "deals": []}
            candidates = [dict(r) for r in c.execute(
                """
                SELECT p.card_id, c.name, c.set_name, c.number, c.rarity, c.image_small,
                       p.source, p.variant, p.price, p.predicted_return,
                       p.predicted_low, p.prob_up, s.currency
                FROM predictions p
                JOIN cards c USING (card_id)
                LEFT JOIN (SELECT DISTINCT card_id, source, variant, currency
                           FROM price_snapshots) s
                     ON s.card_id = p.card_id AND s.source = p.source
                    AND s.variant = p.variant
                WHERE p.run_id = ? AND p.prob_up >= ? AND p.predicted_return >= ?
                      AND p.price >= 1.0{chase_sql}
                ORDER BY p.predicted_return DESC LIMIT ?
                """.format(chase_sql=f" AND {chase_clause('c')}" if chase else ""),
                (run["run_id"], min_prob, min_return, limit),
            ).fetchall()]
        finally:
            c.close()
        live = ebay.credentials() is not None
        deals = []
        for cand in candidates:
            cand["ebay_url"] = ebay.search_url(cand, cand["variant"])
            cand["best_listing"] = None
            if live:
                try:
                    items = ebay.annotate_vs_market(
                        ebay.fetch_listings(cand, cand["variant"], limit=5),
                        cand["price"], cand.get("currency"),
                    )
                    comparable = [i for i in items
                                  if i["vs_market"] is not None
                                  and i["vs_market"] <= max_above_market]
                    if comparable:
                        cand["best_listing"] = min(comparable, key=lambda i: i["vs_market"])
                except Exception:
                    pass  # radar stays useful without eBay
            deals.append(cand)
        if live:
            # in live mode the radar only shows actual below-market listings
            deals = [d for d in deals if d["best_listing"]]
        return {"mode": "live" if live else "link", "deals": deals,
                "criteria": {"min_prob": min_prob, "min_return": min_return,
                             "max_above_market": max_above_market}}

    @app.get("/api/watchlist")
    def api_watchlist():
        c = conn()
        try:
            rows = [dict(r) for r in c.execute(
                f"""
                {LATEST_LISTINGS_CTE}
                SELECT w.watch_id, w.card_id, w.source, w.variant, w.added_at,
                       c.name, c.set_name, c.rarity, c.image_small,
                       l.price, l.currency,
                       p.predicted_return, p.predicted_low, p.predicted_high, p.prob_up
                FROM watchlist w
                JOIN cards c USING (card_id)
                LEFT JOIN latest l ON l.card_id = w.card_id AND l.source = w.source
                     AND l.variant = w.variant AND l.rn = 1
                LEFT JOIN predictions p ON p.run_id = (SELECT run_id FROM run)
                     AND p.card_id = w.card_id AND p.source = w.source
                     AND p.variant = w.variant
                ORDER BY p.predicted_return DESC
                """
            ).fetchall()]
            return {"items": rows}
        finally:
            c.close()

    @app.post("/api/watchlist", status_code=201)
    def api_watchlist_add(item: WatchIn):
        c = conn()
        try:
            if c.execute("SELECT 1 FROM cards WHERE card_id = ?",
                         (item.card_id,)).fetchone() is None:
                raise HTTPException(404, f"unknown card {item.card_id}")
            c.execute(
                "INSERT OR IGNORE INTO watchlist (card_id, source, variant, added_at) "
                "VALUES (?, ?, ?, ?)",
                (item.card_id, item.source, item.variant,
                 datetime.now(timezone.utc).isoformat(timespec="seconds")),
            )
            c.commit()
            return {"watching": True, **item.model_dump()}
        finally:
            c.close()

    @app.delete("/api/watchlist")
    def api_watchlist_remove(card_id: str, source: str, variant: str = "normal"):
        c = conn()
        try:
            cur = c.execute(
                "DELETE FROM watchlist WHERE card_id = ? AND source = ? AND variant = ?",
                (card_id, source, variant),
            )
            c.commit()
            if cur.rowcount == 0:
                raise HTTPException(404, "not on the watchlist")
            return {"watching": False}
        finally:
            c.close()

    @app.get("/api/alerts")
    def api_alerts(limit: int = Query(30, le=200)):
        c = conn()
        try:
            rows = [dict(r) for r in c.execute(
                "SELECT * FROM alerts_log ORDER BY alert_id DESC LIMIT ?", (limit,)
            ).fetchall()]
            return {"alerts": rows, "settings": alerts.get_settings(c)}
        finally:
            c.close()

    @app.put("/api/alerts/settings")
    def api_alerts_settings(settings: dict = Body(...)):
        c = conn()
        try:
            return alerts.save_settings(c, settings)
        finally:
            c.close()

    @app.post("/api/alerts/run")
    def api_alerts_run():
        c = conn()
        try:
            return alerts.run(c, log=lambda *_: None)
        finally:
            c.close()

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
            fx = rates.eur_usd(c)
            for r in rows:
                r["value"] = r["price"] * r["quantity"] if r["price"] else None
                r["gain"] = (
                    (r["price"] - r["cost_basis"]) * r["quantity"]
                    if r["price"] is not None and r["cost_basis"] is not None else None
                )
                # totals are strict USD; EUR rows convert at the ECB daily rate
                mult = fx if r["currency"] == "EUR" else 1.0
                value += (r["value"] or 0.0) * mult
                cost += (r["cost_basis"] or 0.0) * r["quantity"] * mult if r["cost_basis"] else 0.0
                gain += (r["gain"] or 0.0) * mult
                if r["value"] and r["predicted_return"] is not None:
                    pred_delta += r["value"] * mult * r["predicted_return"]
            return {
                "holdings": rows,
                "totals": {
                    "value": value,
                    "cost": cost,
                    "gain": gain,
                    "predicted_delta": pred_delta,
                    "count": len(rows),
                    "currency": "USD",
                    "eur_usd": fx,
                },
            }
        finally:
            c.close()

    @app.post("/api/collection/import")
    def api_collection_import(csv_text: str = Body(..., media_type="text/csv")):
        """Bulk import holdings from a CSV export (TCGplayer collection export,
        spreadsheet, ...). Columns are fuzzy-matched (name/set/quantity/paid);
        rows match tracked cards by name (+ set when present), attaching each
        to that card's primary listing."""
        import csv as _csv
        import io as _io

        reader = list(_csv.DictReader(_io.StringIO(csv_text)))
        if not reader:
            raise HTTPException(400, "CSV has no data rows")
        headers = list(reader[0].keys())
        mapping = csv_ingest.map_columns(headers)
        if "name" not in mapping:
            raise HTTPException(400, f"no card-name column among {headers[:12]}")
        extra = {csv_ingest._norm(h): h for h in headers if h}
        qty_col = next((extra[a] for a in ("qty", "quantity", "count", "amount")
                        if a in extra), None)
        paid_col = next((extra[a] for a in
                         ("paid", "pricepaid", "costbasis", "cost", "purchaseprice",
                          "buyprice", "paidea", "paideach", "totalpaid")
                         if a in extra), None)

        def _num(raw, default=None):
            try:
                return float(str(raw).replace("$", "").replace("€", "").replace(",", "").strip())
            except (ValueError, TypeError):
                return default

        c = conn()
        imported, unmatched = 0, []
        try:
            for idx, raw in enumerate(reader):
                name = (raw.get(mapping["name"]) or "").strip()
                set_name = (raw.get(mapping.get("set_name", ""), "") or "").strip()
                if not name:
                    unmatched.append(f"row {idx + 2}: empty name")
                    continue
                row = None
                if set_name:
                    row = c.execute(
                        "SELECT card_id FROM cards WHERE name = ? COLLATE NOCASE "
                        "AND set_name = ? COLLATE NOCASE", (name, set_name)).fetchone()
                if row is None:
                    row = c.execute(
                        "SELECT card_id FROM cards WHERE name = ? COLLATE NOCASE "
                        "ORDER BY card_id LIMIT 1", (name,)).fetchone()
                if row is None:
                    unmatched.append(name)
                    continue
                listing = c.execute(
                    """
                    SELECT source, variant FROM price_snapshots WHERE card_id = ?
                    ORDER BY CASE source WHEN 'tcgplayer' THEN 0 ELSE 1 END,
                             CASE variant WHEN 'normal' THEN 0 ELSE 1 END
                    LIMIT 1
                    """, (row["card_id"],)).fetchone()
                if listing is None:
                    unmatched.append(f"{name} (no price data)")
                    continue
                qty = max(_num(raw.get(qty_col), 1.0) or 1.0, 1.0) if qty_col else 1.0
                paid = _num(raw.get(paid_col)) if paid_col else None
                c.execute(
                    "INSERT INTO holdings (card_id, source, variant, quantity, "
                    "cost_basis, added_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (row["card_id"], listing["source"], listing["variant"], qty, paid,
                     datetime.now(timezone.utc).isoformat(timespec="seconds")),
                )
                imported += 1
            c.commit()
            return {"imported": imported, "unmatched": unmatched,
                    "columns_used": {**mapping,
                                     **({"quantity": qty_col} if qty_col else {}),
                                     **({"paid": paid_col} if paid_col else {})}}
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
    def api_movers(limit: int = Query(8, le=50), min_price: float = 1.0,
                   chase: int = 0):
        c = conn()
        try:
            run = c.execute(
                "SELECT * FROM prediction_runs ORDER BY run_id DESC LIMIT 1"
            ).fetchone()
            if run is None:
                return {"run": None, "gainers": [], "losers": []}
            chase_sql = f" AND {chase_clause('c')}" if chase else ""
            def side(order: str):
                return [
                    dict(r) for r in c.execute(
                        f"""
                        SELECT p.card_id, c.name, c.set_name, c.rarity, c.image_small,
                               p.source, p.variant, p.price, p.predicted_return, p.prob_up
                        FROM predictions p JOIN cards c USING (card_id)
                        WHERE p.run_id = ? AND p.price >= ?{chase_sql}
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
        rank: str = "worst_case",
        chase: int = 0,
    ):
        """Highest-conviction upside picks, bucketed into USD price tiers.

        A listing qualifies when the latest run gives it P(up) >= min_prob AND
        predicted return >= min_return. Ranking defaults to worst_case (the
        10th-percentile predicted return — conservative first); rank=expected
        uses the median prediction. EUR prices convert at the ECB daily rate
        for tier bucketing.
        """
        c = conn()
        try:
            run = c.execute(
                "SELECT * FROM prediction_runs ORDER BY run_id DESC LIMIT 1"
            ).fetchone()
            criteria = {"min_prob": min_prob, "min_return": min_return,
                        "per_tier": per_tier, "rank": rank}
            tiers = [
                {"key": key, "label": label, "min": lo, "max": hi, "items": []}
                for key, label, lo, hi in BUY_TIERS
            ]
            if run is None:
                return {"run": None, "criteria": criteria, "tiers": tiers}
            rows = [dict(r) for r in c.execute(
                """
                SELECT p.card_id, c.name, c.set_name, c.number, c.rarity, c.image_small,
                       p.source, p.variant, p.price, p.predicted_return, p.prob_up,
                       p.predicted_low, p.predicted_high, p.prob_gain,
                       s.currency
                FROM predictions p
                JOIN cards c USING (card_id)
                LEFT JOIN (SELECT DISTINCT card_id, source, variant, currency
                           FROM price_snapshots) s
                     ON s.card_id = p.card_id AND s.source = p.source
                    AND s.variant = p.variant
                WHERE p.run_id = ? AND p.prob_up >= ? AND p.predicted_return >= ?
                """ + (f" AND {chase_clause('c')}" if chase else ""),
                (run["run_id"], min_prob, min_return),
            ).fetchall()]
            rank_key = (lambda r: r["predicted_low"]
                        if rank == "worst_case" and r["predicted_low"] is not None
                        else r["predicted_return"])
            rows.sort(key=rank_key, reverse=True)
            for r in rows:
                r["price_usd"] = rates.to_usd(c, r["price"], r.get("currency"))
                r["ebay_url"] = ebay.search_url(r, r["variant"])
                for tier, (_, _, lo, hi) in zip(tiers, BUY_TIERS):
                    price = r["price_usd"]
                    if (lo is None or price > lo) and (hi is None or price <= hi):
                        if len(tier["items"]) < per_tier:
                            tier["items"].append(r)
                        break
            run_info = dict(run)
            if run_info.get("metrics"):
                run_info["metrics"] = json.loads(run_info["metrics"])
            return {"run": run_info, "criteria": criteria, "tiers": tiers,
                    "eur_usd": rates.eur_usd(c)}
        finally:
            c.close()

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    return app
