"""Graded-card prices via the PriceCharting API (premium token required).

PriceCharting tracks ungraded AND graded (PSA/BGS/CGC) prices for Pokemon
cards. With PRICECHARTING_TOKEN set, `pokeprice graded <card_id>` finds the
matching product and stores its price points as snapshots under
source='pricecharting', one variant per grade — so graded copies get their own
price series, movers, and predictions, separate from raw copies.

Field mapping follows PriceCharting's documented trading-card semantics
(prices arrive in integer cents):
  loose-price   -> ungraded        graded-price   -> grade9
  cib-price     -> grade7          box-only-price -> grade95
  new-price     -> grade8          manual-only-price -> psa10
  bgs-10-price  -> bgs10
"""
from __future__ import annotations

import os
import sqlite3
from datetime import date

import requests

from . import db

BASE = "https://www.pricecharting.com/api"

GRADE_FIELDS = {
    "loose-price": "ungraded",
    "cib-price": "grade7",
    "new-price": "grade8",
    "graded-price": "grade9",
    "box-only-price": "grade95",
    "manual-only-price": "psa10",
    "bgs-10-price": "bgs10",
    "condition-17-price": "cgc10",
    "condition-18-price": "sgc10",
}


def token() -> str | None:
    return os.environ.get("PRICECHARTING_TOKEN")


def search_products(query: str, session: requests.Session | None = None) -> list[dict]:
    session = session or requests.Session()
    resp = session.get(f"{BASE}/products",
                       params={"t": token(), "q": query}, timeout=30)
    resp.raise_for_status()
    products = resp.json().get("products", []) or []
    return [p for p in products if "pokemon" in (p.get("console-name") or "").lower()]


def get_product(product_id: str, session: requests.Session | None = None) -> dict:
    session = session or requests.Session()
    resp = session.get(f"{BASE}/product",
                       params={"t": token(), "id": product_id}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_graded(conn: sqlite3.Connection, card_id: str,
                 query: str | None = None,
                 session: requests.Session | None = None) -> dict:
    """Store today's graded price points for a card. Returns a small report."""
    if not token():
        raise RuntimeError(
            "PRICECHARTING_TOKEN not set — graded prices need a PriceCharting "
            "API token (pricecharting.com/api-documentation)."
        )
    card = conn.execute("SELECT * FROM cards WHERE card_id = ?", (card_id,)).fetchone()
    if card is None:
        raise RuntimeError(f"unknown card {card_id}")
    query = query or " ".join(
        str(part) for part in (card["name"], card["set_name"], card["number"]) if part
    )
    products = search_products(query, session=session)
    if not products:
        return {"card_id": card_id, "query": query, "matched": None, "snapshots": 0}
    product = products[0]
    detail = get_product(str(product["id"]), session=session)
    today = date.today().isoformat()
    snaps = []
    for field, variant in GRADE_FIELDS.items():
        cents = detail.get(field)
        if not cents:
            continue
        snaps.append({
            "card_id": card_id,
            "source": "pricecharting",
            "variant": variant,
            "snapshot_date": today,
            "currency": "USD",
            "market": cents / 100.0,
        })
    inserted = db.insert_snapshots(conn, snaps)
    return {
        "card_id": card_id,
        "query": query,
        "matched": detail.get("product-name") or product.get("product-name"),
        "snapshots": inserted,
    }
