"""Watchlist/collection alerts.

Rules run over everything you track (watchlist ∪ holdings):

* signal   — the model turns bullish: P(up) and predicted move clear your bars
* move     — a tracked card actually moved hard over ~7 days
* portfolio — your collection's total value dropped more than X% since the
  previous snapshot date

Alerts are deduplicated (a rule fires once per card per as-of date), always
logged in-app, and best-effort delivered to a Discord webhook
(DISCORD_WEBHOOK_URL) and/or SMTP email (SMTP_HOST/PORT/USER/PASSWORD,
ALERT_EMAIL_FROM/TO) when configured. The scheduler runs this after every
auto-fetch cycle; `pokeprice alerts` runs it on demand.
"""
from __future__ import annotations

import json
import os
import smtplib
import sqlite3
from datetime import datetime, timezone
from email.message import EmailMessage

import requests

from . import config, db

DEFAULT_SETTINGS = {
    "enabled": True,
    "min_prob": 0.80,        # signal: P(up) at least this
    "min_return": 0.05,      # signal: predicted move at least this
    "move_threshold": 0.15,  # move: |7d change| at least this
    "collection_drop": 0.05, # portfolio: value down this fraction vs previous date
}


def get_settings(conn: sqlite3.Connection) -> dict:
    stored = db.get_meta(conn, "alert_settings") or {}
    return {**DEFAULT_SETTINGS, **stored}


def save_settings(conn: sqlite3.Connection, settings: dict) -> dict:
    clean = {}
    for key, default in DEFAULT_SETTINGS.items():
        if key in settings and settings[key] is not None:
            clean[key] = bool(settings[key]) if key == "enabled" else float(settings[key])
    merged = {**get_settings(conn), **clean}
    db.set_meta(conn, "alert_settings", merged)
    return merged


TRACKED_SQL = """
SELECT card_id, source, variant FROM watchlist
UNION
SELECT card_id, source, variant FROM holdings
"""


def _insert(conn, kind, card_id, source, variant, message, dedup_key) -> dict | None:
    cur = conn.execute(
        "INSERT OR IGNORE INTO alerts_log "
        "(created_at, kind, card_id, source, variant, message, dedup_key) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (datetime.now(timezone.utc).isoformat(timespec="seconds"),
         kind, card_id, source, variant, message, dedup_key),
    )
    if cur.rowcount == 0:
        return None
    return {"alert_id": cur.lastrowid, "kind": kind, "card_id": card_id,
            "source": source, "variant": variant, "message": message}


def evaluate(conn: sqlite3.Connection) -> list[dict]:
    """Apply all rules; returns only alerts that are new (not previously fired)."""
    settings = get_settings(conn)
    if not settings.get("enabled", True):
        return []
    new: list[dict] = []
    tracked = {(r["card_id"], r["source"], r["variant"])
               for r in conn.execute(TRACKED_SQL)}
    if tracked:
        # signal thresholds are calibrated for the default (7d) horizon, so
        # alerts read that run — not whichever horizon predicted last
        rows = conn.execute(
            """
            SELECT p.*, r.as_of, r.horizon_days, c.name
            FROM predictions p
            JOIN prediction_runs r USING (run_id)
            JOIN cards c USING (card_id)
            WHERE p.run_id = (SELECT run_id FROM prediction_runs
                              ORDER BY (horizon_days = ?) DESC, run_id DESC
                              LIMIT 1)
            """,
            (config.DEFAULT_HORIZON_DAYS,),
        ).fetchall()
        for p in rows:
            key = (p["card_id"], p["source"], p["variant"])
            if key not in tracked:
                continue
            if (p["prob_up"] or 0) >= settings["min_prob"] and \
               (p["predicted_return"] or 0) >= settings["min_return"]:
                alert = _insert(
                    conn, "signal", *key,
                    f"{p['name']} ({p['source']} · {p['variant']}): model says "
                    f"{p['predicted_return']:+.1%} over {p['horizon_days']}d, "
                    f"P(up) {p['prob_up']:.0%}, at {p['price']:.2f}",
                    f"signal|{p['card_id']}|{p['source']}|{p['variant']}|{p['as_of']}",
                )
                if alert:
                    new.append(alert)

        moves = conn.execute(
            """
            WITH latest AS (
                SELECT s.*, COALESCE(s.market, s.mid, (s.low+s.high)/2.0, s.low) AS price,
                       ROW_NUMBER() OVER (PARTITION BY s.card_id, s.source, s.variant
                                          ORDER BY s.snapshot_date DESC) AS rn
                FROM price_snapshots s
            )
            SELECT l.card_id, l.source, l.variant, l.snapshot_date, l.price, c.name,
                   (SELECT COALESCE(p2.market, p2.mid, p2.low) FROM price_snapshots p2
                    WHERE p2.card_id = l.card_id AND p2.source = l.source
                      AND p2.variant = l.variant
                      AND p2.snapshot_date <= date(l.snapshot_date, '-6 day')
                    ORDER BY p2.snapshot_date DESC LIMIT 1) AS past7
            FROM latest l JOIN cards c USING (card_id)
            WHERE l.rn = 1
            """
        ).fetchall()
        for m in moves:
            key = (m["card_id"], m["source"], m["variant"])
            if key not in tracked or not m["past7"] or not m["price"]:
                continue
            change = m["price"] / m["past7"] - 1.0
            if abs(change) >= settings["move_threshold"]:
                alert = _insert(
                    conn, "move", *key,
                    f"{m['name']} ({m['source']} · {m['variant']}) moved "
                    f"{change:+.1%} over ~7d, now {m['price']:.2f}",
                    f"move|{m['card_id']}|{m['source']}|{m['variant']}|{m['snapshot_date']}",
                )
                if alert:
                    new.append(alert)

    # portfolio drop: compare collection value on the two most recent snapshot dates
    values = conn.execute(
        """
        SELECT s.snapshot_date,
               SUM(h.quantity * COALESCE(s.market, s.mid, (s.low+s.high)/2.0, s.low)) AS value
        FROM holdings h
        JOIN price_snapshots s ON s.card_id = h.card_id
             AND s.source = h.source AND s.variant = h.variant
        GROUP BY s.snapshot_date ORDER BY s.snapshot_date DESC LIMIT 2
        """
    ).fetchall()
    if len(values) == 2 and values[1]["value"]:
        change = values[0]["value"] / values[1]["value"] - 1.0
        if change <= -settings["collection_drop"]:
            alert = _insert(
                conn, "portfolio", None, None, None,
                f"Collection value dropped {change:+.1%} "
                f"({values[1]['value']:.2f} -> {values[0]['value']:.2f}) "
                f"as of {values[0]['snapshot_date']}",
                f"portfolio|{values[0]['snapshot_date']}",
            )
            if alert:
                new.append(alert)
    conn.commit()
    return new


def deliver(conn: sqlite3.Connection, alerts: list[dict], log=print) -> list[str]:
    """Push new alerts to configured channels; returns channels that succeeded."""
    if not alerts:
        return []
    channels: list[str] = ["in-app"]
    body = "\n".join(f"[{a['kind']}] {a['message']}" for a in alerts)

    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if webhook:
        try:
            requests.post(webhook, json={"content": f"**pokeprice alerts**\n{body}"},
                          timeout=15).raise_for_status()
            channels.append("discord")
        except Exception as exc:
            log(f"discord delivery failed: {exc}")

    host = os.environ.get("SMTP_HOST")
    to = os.environ.get("ALERT_EMAIL_TO")
    if host and to:
        try:
            msg = EmailMessage()
            msg["Subject"] = f"pokeprice: {len(alerts)} alert(s)"
            msg["From"] = os.environ.get("ALERT_EMAIL_FROM", "pokeprice@localhost")
            msg["To"] = to
            msg.set_content(body)
            with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587"))) as smtp:
                if os.environ.get("SMTP_USER"):
                    smtp.starttls()
                    smtp.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD", ""))
                smtp.send_message(msg)
            channels.append("email")
        except Exception as exc:
            log(f"email delivery failed: {exc}")

    ids = [a["alert_id"] for a in alerts]
    conn.executemany(
        "UPDATE alerts_log SET delivered = ? WHERE alert_id = ?",
        [(json.dumps(channels), i) for i in ids],
    )
    conn.commit()
    return channels


def run(conn: sqlite3.Connection, log=print) -> dict:
    new = evaluate(conn)
    channels = deliver(conn, new, log=log)
    return {"new_alerts": len(new), "channels": channels, "alerts": new}
