"""SQLite storage: cards, price snapshots, prediction runs.

The schema is deliberately source-agnostic: every price observation is a
(card, source, variant, date) row, whether it came from the user's own data
dump, the live API, or a CSV export. Repeated ingests are idempotent.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable, Mapping

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS cards (
    card_id          TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    supertype        TEXT,
    subtypes         TEXT,
    rarity           TEXT,
    set_id           TEXT,
    set_name         TEXT,
    set_series       TEXT,
    set_release_date TEXT,
    number           TEXT,
    artist           TEXT,
    image_small      TEXT,
    image_large      TEXT,
    tcgplayer_url    TEXT,
    cardmarket_url   TEXT
);

CREATE TABLE IF NOT EXISTS price_snapshots (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id       TEXT NOT NULL REFERENCES cards(card_id),
    source        TEXT NOT NULL,
    variant       TEXT NOT NULL DEFAULT 'normal',
    snapshot_date TEXT NOT NULL,
    currency      TEXT,
    market        REAL,
    low           REAL,
    mid           REAL,
    high          REAL,
    direct_low    REAL,
    avg1          REAL,
    avg7          REAL,
    avg30         REAL,
    UNIQUE (card_id, source, variant, snapshot_date)
);
CREATE INDEX IF NOT EXISTS idx_snap_card ON price_snapshots(card_id, source, variant, snapshot_date);
CREATE INDEX IF NOT EXISTS idx_snap_date ON price_snapshots(snapshot_date);

CREATE TABLE IF NOT EXISTS prediction_runs (
    run_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at   TEXT NOT NULL,
    model_kind   TEXT NOT NULL,
    horizon_days INTEGER NOT NULL,
    as_of        TEXT NOT NULL,
    metrics      TEXT
);

CREATE TABLE IF NOT EXISTS predictions (
    run_id           INTEGER NOT NULL REFERENCES prediction_runs(run_id),
    card_id          TEXT NOT NULL,
    source           TEXT NOT NULL,
    variant          TEXT NOT NULL,
    price            REAL,
    predicted_return REAL,
    prob_up          REAL,
    PRIMARY KEY (run_id, card_id, source, variant)
);

CREATE TABLE IF NOT EXISTS holdings (
    holding_id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id    TEXT NOT NULL REFERENCES cards(card_id),
    source     TEXT NOT NULL,
    variant    TEXT NOT NULL DEFAULT 'normal',
    quantity   REAL NOT NULL DEFAULT 1,
    cost_basis REAL,               -- paid per card, in the listing's currency
    added_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def set_meta(conn: sqlite3.Connection, key: str, value) -> None:
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, json.dumps(value)),
    )
    conn.commit()


def get_meta(conn: sqlite3.Connection, key: str, default=None):
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default

CARD_COLUMNS = (
    "card_id", "name", "supertype", "subtypes", "rarity", "set_id", "set_name",
    "set_series", "set_release_date", "number", "artist", "image_small",
    "image_large", "tcgplayer_url", "cardmarket_url",
)

SNAPSHOT_COLUMNS = (
    "card_id", "source", "variant", "snapshot_date", "currency", "market",
    "low", "mid", "high", "direct_low", "avg1", "avg7", "avg30",
)


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    p = Path(path) if path is not None else config.db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def upsert_cards(conn: sqlite3.Connection, cards: Iterable[Mapping]) -> int:
    """Insert or update card metadata. Only non-null incoming values overwrite."""
    rows = []
    for c in cards:
        row = {k: c.get(k) for k in CARD_COLUMNS}
        if not row["card_id"] or not row["name"]:
            continue
        if isinstance(row["subtypes"], (list, tuple)):
            row["subtypes"] = json.dumps(list(row["subtypes"]))
        rows.append(row)
    if not rows:
        return 0
    updates = ", ".join(
        f"{col}=COALESCE(excluded.{col}, {col})" for col in CARD_COLUMNS[1:]
    )
    sql = (
        f"INSERT INTO cards ({', '.join(CARD_COLUMNS)}) "
        f"VALUES ({', '.join(':' + c for c in CARD_COLUMNS)}) "
        f"ON CONFLICT(card_id) DO UPDATE SET {updates}"
    )
    conn.executemany(sql, rows)
    conn.commit()
    return len(rows)


def insert_snapshots(conn: sqlite3.Connection, snapshots: Iterable[Mapping]) -> int:
    """Insert price observations; duplicates (same card/source/variant/date) are ignored."""
    rows = []
    for s in snapshots:
        row = {k: s.get(k) for k in SNAPSHOT_COLUMNS}
        if not row["card_id"] or not row["snapshot_date"]:
            continue
        if row["market"] is None and row["mid"] is None and row["low"] is None:
            continue
        row["source"] = row["source"] or "unknown"
        row["variant"] = row["variant"] or "normal"
        rows.append(row)
    if not rows:
        return 0
    before = conn.execute("SELECT COUNT(*) FROM price_snapshots").fetchone()[0]
    sql = (
        f"INSERT OR IGNORE INTO price_snapshots ({', '.join(SNAPSHOT_COLUMNS)}) "
        f"VALUES ({', '.join(':' + c for c in SNAPSHOT_COLUMNS)})"
    )
    conn.executemany(sql, rows)
    conn.commit()
    after = conn.execute("SELECT COUNT(*) FROM price_snapshots").fetchone()[0]
    return after - before


def stats(conn: sqlite3.Connection) -> dict:
    q = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
    latest_run = conn.execute(
        "SELECT * FROM prediction_runs ORDER BY run_id DESC LIMIT 1"
    ).fetchone()
    return {
        "cards": q("SELECT COUNT(*) FROM cards"),
        "snapshots": q("SELECT COUNT(*) FROM price_snapshots"),
        "listings": q(
            "SELECT COUNT(*) FROM (SELECT DISTINCT card_id, source, variant FROM price_snapshots)"
        ),
        "snapshot_dates": q("SELECT COUNT(DISTINCT snapshot_date) FROM price_snapshots"),
        "first_date": q("SELECT MIN(snapshot_date) FROM price_snapshots"),
        "last_date": q("SELECT MAX(snapshot_date) FROM price_snapshots"),
        "latest_run": dict(latest_run) if latest_run else None,
    }
