"""Generic CSV ingestion with fuzzy column mapping.

Card price exports come with wildly different headers (Kaggle datasets,
TCGplayer collection exports, spreadsheet trackers). Rather than demand one
schema, we map whatever columns we can recognize and report the mapping.
"""
from __future__ import annotations

import io
import re
from datetime import date

import pandas as pd

# canonical field -> candidate header names (compared lowercased, non-alnum stripped)
COLUMN_ALIASES: dict[str, list[str]] = {
    "card_id": ["cardid", "id", "uniqueid", "productid", "tcgplayerid", "cardnumberid"],
    "name": ["name", "cardname", "card", "productname", "title"],
    "set_name": ["setname", "set", "expansion", "series", "groupname"],
    "set_release_date": ["releasedate", "setreleasedate", "released"],
    "number": ["number", "cardnumber", "collectornumber", "no"],
    "rarity": ["rarity", "cardrarity"],
    "supertype": ["supertype", "cardtype", "type"],
    "artist": ["artist", "illustrator"],
    "image_small": ["imageurl", "image", "imagesmall", "img", "imgurl"],
    "variant": ["variant", "printing", "finish", "foil", "subtypename", "condition"],
    "snapshot_date": ["date", "snapshotdate", "updatedat", "priceddate", "asof", "timestamp", "updated"],
    "market": ["market", "marketprice", "price", "priceusd", "usd", "value", "trendprice", "averagesellprice", "avgprice", "meanprice"],
    "low": ["low", "lowprice", "lowestprice", "min", "minprice"],
    "mid": ["mid", "midprice", "median", "medianprice"],
    "high": ["high", "highprice", "max", "maxprice"],
    "avg1": ["avg1"],
    "avg7": ["avg7"],
    "avg30": ["avg30"],
    "currency": ["currency", "curr"],
}


def _norm(header: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(header).lower())


def map_columns(headers) -> dict[str, str]:
    """Return {canonical: actual_header} using exact-normalized then prefix matches."""
    normed = {_norm(h): h for h in headers}
    mapping: dict[str, str] = {}
    taken: set[str] = set()
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            hit = normed.get(alias)
            if hit is not None and hit not in taken:
                mapping[canonical] = hit
                taken.add(hit)
                break
    return mapping


def looks_like_cards_csv(headers) -> bool:
    mapping = map_columns(headers)
    return "name" in mapping or "card_id" in mapping


def _clean_price(series: pd.Series) -> pd.Series:
    if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
        series = (
            series.astype(str)
            .str.replace(r"[$€£,]", "", regex=True)
            .str.strip()
            .replace({"": None, "nan": None, "None": None, "-": None})
        )
    return pd.to_numeric(series, errors="coerce")


def parse_csv(
    text_or_buffer, default_date: str | None = None, source: str = "csv"
) -> tuple[list[dict], list[dict], dict[str, str]]:
    """Parse CSV content -> (card rows, snapshot rows, column mapping used)."""
    if isinstance(text_or_buffer, (str, bytes)):
        if isinstance(text_or_buffer, bytes):
            text_or_buffer = text_or_buffer.decode("utf-8", errors="replace")
        text_or_buffer = io.StringIO(text_or_buffer)
    df = pd.read_csv(text_or_buffer)
    mapping = map_columns(df.columns)
    if "name" not in mapping and "card_id" not in mapping:
        raise ValueError(
            f"CSV not recognized: no name/id column among {list(df.columns)[:15]}"
        )

    out = pd.DataFrame(index=df.index)
    for canonical, actual in mapping.items():
        out[canonical] = df[actual]

    if "name" not in out:
        out["name"] = out["card_id"].astype(str)
    if "card_id" not in out:
        # Stable synthetic id from name + set + collector number.
        parts = [out["name"].astype(str)]
        for extra in ("set_name", "number"):
            if extra in out:
                parts.append(out[extra].astype(str))
        key = parts[0].str.cat(parts[1:], sep="|") if len(parts) > 1 else parts[0]
        out["card_id"] = "csv-" + key.map(
            lambda s: re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:80]
        )
    out["card_id"] = out["card_id"].astype(str)

    for price_col in ("market", "low", "mid", "high", "avg1", "avg7", "avg30"):
        if price_col in out:
            out[price_col] = _clean_price(out[price_col])
    if "market" not in out:
        for fallback in ("mid", "high", "low"):
            if fallback in out:
                out["market"] = out[fallback]
                break

    if "snapshot_date" in out:
        parsed = pd.to_datetime(out["snapshot_date"], errors="coerce", utc=True)
        out["snapshot_date"] = parsed.dt.date.astype(str).replace({"NaT": None})
    out_date = default_date or date.today().isoformat()
    if "snapshot_date" not in out:
        out["snapshot_date"] = out_date
    out["snapshot_date"] = out["snapshot_date"].fillna(out_date)

    if "set_release_date" in out:
        rel = pd.to_datetime(out["set_release_date"], errors="coerce", utc=True)
        out["set_release_date"] = rel.dt.date.astype(str).replace({"NaT": None})

    if "variant" not in out:
        out["variant"] = "normal"
    out["variant"] = out["variant"].fillna("normal").astype(str)

    card_cols = [c for c in (
        "card_id", "name", "supertype", "rarity", "set_name", "set_release_date",
        "number", "artist", "image_small",
    ) if c in out]
    cards = (
        out[card_cols]
        .drop_duplicates(subset=["card_id"])
        .astype(object)
        .where(pd.notna(out[card_cols].drop_duplicates(subset=["card_id"])), None)
        .to_dict("records")
    )

    snapshots: list[dict] = []
    if "market" in out:
        snap_cols = [c for c in (
            "card_id", "variant", "snapshot_date", "currency", "market",
            "low", "mid", "high", "avg1", "avg7", "avg30",
        ) if c in out]
        snaps = out[snap_cols].astype(object).where(pd.notna(out[snap_cols]), None)
        for rec in snaps.to_dict("records"):
            rec["source"] = source
            snapshots.append(rec)

    return cards, snapshots, mapping
