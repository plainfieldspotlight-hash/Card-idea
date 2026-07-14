"""Backfill REAL daily price history from tcgcsv.com archives.

tcgcsv.com (a community service) has archived TCGplayer's full daily price
feed every day since 2024-02-08 — one ~3 MB 7z per day covering every game.
This module downloads the Pokemon slice of those archives and turns it into
dated snapshots in our schema, giving the model years' worth of genuine daily
history in minutes instead of waiting for scheduled fetches to accumulate.

Matching TCGplayer products to our cards is a two-step cascade, cached in the
meta table once built:
  group -> set:  the "SWSH09:"-style prefix code against our set ids, then
                 exact normalized names, then name containment + release-date
                 proximity (unmatched groups are skipped and reported)
  product -> card: collector number within the set (both sides normalized:
                 "025/172" == "25"), falling back to exact normalized names

Prices land as source='tcgplayer' — the same source the live API writes — so
backfilled history and ongoing fetches form one continuous series.
"""
from __future__ import annotations

import io
import json
import re
import sqlite3
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

import requests

from . import config, db

TCGCSV_BASE = "https://tcgcsv.com"
POKEMON_CATEGORY = 3
ARCHIVE_URL = TCGCSV_BASE + "/archive/tcgplayer/prices-{day}.ppmd.7z"
EARLIEST = date(2024, 2, 8)  # first day tcgcsv archived

META_GROUP_MAP = "tcgcsv_group_map"
META_PRODUCT_MAP = "tcgcsv_product_map"
META_DONE = "tcgcsv_days_done"


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


def _norm_code(text: str) -> str:
    """Normalize set codes: 'SWSH09' -> 'swsh9', 'SV01' -> 'sv1'."""
    m = re.fullmatch(r"([a-z]+)0*(\d+)([a-z0-9]*)", _norm(text))
    return f"{m.group(1)}{m.group(2)}{m.group(3)}" if m else _norm(text)


def normalize_variant(sub_type: str) -> str:
    """TCGplayer subTypeName -> our variant keys ('Reverse Holofoil' -> reverseHolofoil)."""
    words = str(sub_type or "Normal").split()
    if not words:
        return "normal"
    head = words[0].lower() if words[0][0].isalpha() else words[0]
    return head + "".join(w.title() for w in words[1:])


def normalize_number(num: str) -> str:
    """Collector number: '025/172' -> '25', 'TG12/TG30' -> 'tg12'."""
    head = str(num or "").split("/")[0].strip().lower()
    if head.isdigit():
        return head.lstrip("0") or head
    return re.sub(r"^([a-z]*)0*(\d+)$", r"\1\2", head)


def _session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = "pokeprice/0.1 (card price research)"
    return s


def _get_json(session: requests.Session, url: str, retries: int = 3) -> dict:
    delay = 2.0
    for attempt in range(retries + 1):
        try:
            resp = session.get(url, timeout=60)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError):
            if attempt == retries:
                raise
            time.sleep(delay)
            delay *= 2
    raise RuntimeError("unreachable")


def fetch_groups(session: requests.Session) -> list[dict]:
    payload = _get_json(session, f"{TCGCSV_BASE}/tcgplayer/{POKEMON_CATEGORY}/groups")
    return payload.get("results", [])


def fetch_products(session: requests.Session, group_id: int) -> list[dict]:
    payload = _get_json(
        session, f"{TCGCSV_BASE}/tcgplayer/{POKEMON_CATEGORY}/{group_id}/products")
    return payload.get("results", [])


def build_set_mapping(conn: sqlite3.Connection, groups: list[dict],
                      set_ids: list[str] | None = None) -> dict[int, str]:
    """Map tcgcsv/TCGplayer groupId -> our set_id."""
    sets = [dict(r) for r in conn.execute(
        "SELECT DISTINCT set_id, set_name, set_release_date FROM cards "
        "WHERE set_id IS NOT NULL")]
    if set_ids:
        wanted = {s.strip() for s in set_ids}
        sets = [s for s in sets if s["set_id"] in wanted]
    by_code = {_norm_code(s["set_id"]): s["set_id"] for s in sets}
    by_name: dict[str, list[dict]] = {}
    for s in sets:
        by_name.setdefault(_norm(s["set_name"]), []).append(s)

    mapping: dict[int, str] = {}
    for g in groups:
        name = g.get("name") or ""
        prefix_match = re.match(r"^\s*([A-Za-z0-9.]+)\s*:\s*(.*)$", name)
        code, bare_name = (prefix_match.group(1), prefix_match.group(2)) if prefix_match \
            else (g.get("abbreviation") or "", name)
        # 1) set code (SWSH09 -> swsh9)
        set_id = by_code.get(_norm_code(code))
        # 2) exact normalized name
        if set_id is None:
            candidates = by_name.get(_norm(bare_name)) or by_name.get(_norm(name)) or []
            if len(candidates) == 1:
                set_id = candidates[0]["set_id"]
        # 3) containment + release-date proximity
        if set_id is None:
            g_norm = _norm(name)
            published = str(g.get("publishedOn") or "")[:10]
            best = None
            for s in sets:
                s_norm = _norm(s["set_name"])
                if not s_norm or (s_norm not in g_norm and g_norm not in s_norm):
                    continue
                try:
                    gap = abs((date.fromisoformat(published)
                               - date.fromisoformat(s["set_release_date"])).days)
                except (ValueError, TypeError):
                    continue
                if gap <= 60 and (best is None or gap < best[0]):
                    best = (gap, s["set_id"])
            if best:
                set_id = best[1]
        if set_id:
            mapping[int(g["groupId"])] = set_id
    return mapping


def build_product_mapping(
    conn: sqlite3.Connection, session: requests.Session,
    group_map: dict[int, str], progress=print,
) -> dict[int, str]:
    """Map TCGplayer productId -> our card_id, one products call per new group."""
    cached = db.get_meta(conn, META_PRODUCT_MAP) or {}
    product_map: dict[int, str] = {int(k): v for k, v in cached.get("products", {}).items()}
    done_groups: set[int] = set(cached.get("groups", []))

    todo = [gid for gid in group_map if gid not in done_groups]
    for i, gid in enumerate(todo):
        set_id = group_map[gid]
        cards = [dict(r) for r in conn.execute(
            "SELECT card_id, name, number FROM cards WHERE set_id = ?", (set_id,))]
        by_number = {}
        for c in cards:
            by_number.setdefault(normalize_number(c["number"]), c["card_id"])
        by_name = {}
        for c in cards:
            by_name.setdefault(_norm(c["name"]), c["card_id"])
        matched = 0
        for p in fetch_products(session, gid):
            ext = {e.get("name"): e.get("value") for e in p.get("extendedData", [])}
            number = ext.get("Number")
            card_id = by_number.get(normalize_number(number)) if number else None
            if card_id is None:
                card_id = by_name.get(_norm(p.get("cleanName") or p.get("name")))
            if card_id:
                product_map[int(p["productId"])] = card_id
                matched += 1
        done_groups.add(gid)
        if (i + 1) % 20 == 0 or i == len(todo) - 1:
            progress(f"  mapped {i + 1}/{len(todo)} new groups "
                     f"({len(product_map)} products total)")
        time.sleep(0.1)
    db.set_meta(conn, META_PRODUCT_MAP, {
        "products": {str(k): v for k, v in product_map.items()},
        "groups": sorted(done_groups),
    })
    return product_map


def _iter_archive_prices(archive_path: Path, day: str, group_ids: set[int]):
    """Yield (group_id, prices_payload) for the wanted groups in a daily archive."""
    import py7zr

    targets = [f"{day}/{POKEMON_CATEGORY}/{gid}/prices" for gid in group_ids]
    with tempfile.TemporaryDirectory(dir=archive_path.parent) as tmp:
        with py7zr.SevenZipFile(archive_path) as z:
            available = set(z.getnames())
            wanted = [t for t in targets if t in available]
            if wanted:
                z.extract(path=tmp, targets=wanted)
        for target in wanted:
            gid = int(target.split("/")[2])
            path = Path(tmp) / target
            if path.exists():
                with open(path, "rb") as fh:
                    yield gid, json.load(io.BytesIO(fh.read()))


def backfill(
    conn: sqlite3.Connection,
    days: int = 120,
    every: int = 2,
    set_ids: list[str] | None = None,
    end: date | None = None,
    progress=print,
) -> dict:
    """Download daily archives and store historical snapshots. Resumable."""
    n_cards = conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
    if n_cards == 0:
        raise RuntimeError(
            "No cards in the database to match prices against — load the catalog "
            "first: `pokeprice fetch --sets <ids>` / `--all` (live API) or "
            "`pokeprice fetch --github` (metadata catalog, no key needed)."
        )
    session = _session()
    progress("Matching TCGplayer groups/products to your card catalog ...")
    groups = fetch_groups(session)
    group_map = db.get_meta(conn, META_GROUP_MAP) or {}
    group_map = {int(k): v for k, v in group_map.items()}
    fresh_map = build_set_mapping(conn, groups, set_ids)
    group_map.update(fresh_map)
    db.set_meta(conn, META_GROUP_MAP, {str(k): v for k, v in group_map.items()})
    active_groups = ({gid for gid, sid in group_map.items() if sid in set(set_ids)}
                     if set_ids else set(group_map))
    if not active_groups:
        raise RuntimeError("No TCGplayer groups matched the requested sets.")
    product_map = build_product_mapping(
        conn, session, {gid: group_map[gid] for gid in active_groups}, progress)
    progress(f"  {len(active_groups)} groups, {len(product_map)} products matched")

    end = end or (date.today() - timedelta(days=1))
    wanted_days = []
    d = end
    while d >= EARLIEST and len(wanted_days) * every < days:
        wanted_days.append(d)
        d -= timedelta(days=every)
    done = set(db.get_meta(conn, META_DONE) or [])
    todo = [d for d in wanted_days if d.isoformat() not in done]
    progress(f"Backfilling {len(todo)} day(s) (~3 MB each), "
             f"{end - timedelta(days=days)} .. {end}, every {every} day(s)")

    total_snaps = 0
    with tempfile.TemporaryDirectory(dir=config.data_dir()) as tmp:
        for i, day_date in enumerate(sorted(todo)):
            day = day_date.isoformat()
            archive = Path(tmp) / f"{day}.7z"
            url = ARCHIVE_URL.format(day=day)
            try:
                with session.get(url, stream=True, timeout=120) as resp:
                    if resp.status_code == 404:
                        progress(f"  {day}: no archive (skipped)")
                        done.add(day)
                        continue
                    resp.raise_for_status()
                    with open(archive, "wb") as fh:
                        for chunk in resp.iter_content(1 << 20):
                            fh.write(chunk)
            except requests.RequestException as exc:
                progress(f"  {day}: download failed ({exc}) — will retry next run")
                continue
            snaps = []
            for gid, payload in _iter_archive_prices(archive, day, active_groups):
                for row in payload.get("results", []):
                    card_id = product_map.get(int(row.get("productId", -1)))
                    if card_id is None:
                        continue
                    snaps.append({
                        "card_id": card_id,
                        "source": "tcgplayer",
                        "variant": normalize_variant(row.get("subTypeName")),
                        "snapshot_date": day,
                        "currency": "USD",
                        "market": row.get("marketPrice"),
                        "low": row.get("lowPrice"),
                        "mid": row.get("midPrice"),
                        "high": row.get("highPrice"),
                        "direct_low": row.get("directLowPrice"),
                    })
            added = db.insert_snapshots(conn, snaps)
            total_snaps += added
            archive.unlink(missing_ok=True)
            done.add(day)
            db.set_meta(conn, META_DONE, sorted(done))
            progress(f"  {day}: +{added} snapshots ({i + 1}/{len(todo)})")
    return {
        "days_processed": len(todo),
        "snapshots_added": total_snaps,
        "groups_matched": len(active_groups),
        "products_matched": len(product_map),
    }
