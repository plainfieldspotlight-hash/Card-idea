"""Currency unification: EUR -> USD at the ECB daily reference rate.

Cardmarket prices are EUR while TCGplayer is USD; price tiers, portfolio
totals, and cross-source comparisons convert to USD. Rates come from
frankfurter.app (free, keyless, ECB data), are cached in the meta table for a
day, and fall back to the last known (or a static) rate when offline — the
dashboard should degrade, never break, without network.
"""
from __future__ import annotations

import sqlite3
from datetime import date

import requests

from . import db

RATES_URL = "https://api.frankfurter.app/latest"
STATIC_FALLBACK = {"EUR": 1.08}  # ballpark; only used before any live fetch


def eur_usd(conn: sqlite3.Connection) -> float:
    """Current EUR->USD rate, cached per day in meta."""
    cached = db.get_meta(conn, "fx_eur_usd")
    today = date.today().isoformat()
    if cached and cached.get("date") == today:
        return cached["rate"]
    try:
        resp = requests.get(RATES_URL, params={"from": "EUR", "to": "USD"}, timeout=10)
        resp.raise_for_status()
        rate = float(resp.json()["rates"]["USD"])
        db.set_meta(conn, "fx_eur_usd", {"date": today, "rate": rate, "source": "ecb"})
        return rate
    except Exception:
        if cached:
            return cached["rate"]  # stale beats broken
        return STATIC_FALLBACK["EUR"]


def to_usd(conn: sqlite3.Connection, amount: float | None, currency: str | None) -> float | None:
    if amount is None:
        return None
    if currency == "EUR":
        return amount * eur_usd(conn)
    return amount  # USD or unknown: treat at face value
