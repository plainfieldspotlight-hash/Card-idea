"""Pull current cards + prices from live sources.

Two paths:
  * api.pokemontcg.io — filtered fetches (per set / query). Free; an API key
    via POKEMONTCG_API_KEY raises rate limits.
  * The PokemonTCG/pokemon-tcg-data GitHub dump — every card in one download,
    with the prices current as of the repo's last refresh. Good for a first
    bulk load without an API key.

Each run stores a dated snapshot; run it on a schedule (cron/Task Scheduler)
and the database accumulates the price history the model trains on.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
import time
from pathlib import Path

import requests

from . import config, db
from .ingest import loader, tcg_json

PAGE_SIZE = 250


def _session() -> requests.Session:
    s = requests.Session()
    key = os.environ.get(config.TCG_API_KEY_ENV)
    if key:
        s.headers["X-Api-Key"] = key
    s.headers["User-Agent"] = "pokeprice/0.1 (card price research)"
    return s


def _get_json(session: requests.Session, url: str, params: dict | None = None,
              retries: int = 4) -> dict:
    delay = 2.0
    for attempt in range(retries + 1):
        try:
            resp = session.get(url, params=params, timeout=60)
            if resp.status_code == 429 or resp.status_code >= 500:
                raise requests.HTTPError(f"HTTP {resp.status_code}", response=resp)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError):
            if attempt == retries:
                raise
            time.sleep(delay)
            delay *= 2
    raise RuntimeError("unreachable")


def list_sets(session: requests.Session | None = None) -> list[dict]:
    session = session or _session()
    payload = _get_json(session, f"{config.TCG_API_BASE}/sets",
                        {"pageSize": PAGE_SIZE, "orderBy": "-releaseDate"})
    return payload.get("data", [])


def fetch_api(
    conn: sqlite3.Connection,
    sets: list[str] | None = None,
    query: str | None = None,
    max_pages: int | None = None,
    progress=print,
    session: requests.Session | None = None,
) -> tuple[int, int]:
    """Fetch cards from the API and store today's snapshot. Returns (cards, snapshots).

    Runs until the API reports every card delivered. max_pages is an optional
    safety cap — it used to default to 50 (= 12,500 cards), which silently
    truncated full crawls right around the 2020 sets."""
    session = session or _session()
    queries: list[str | None]
    if sets:
        queries = [f"set.id:{s.strip()}" for s in sets]
    elif query:
        queries = [query]
    else:
        queries = [None]

    total_cards = total_snaps = 0
    for q in queries:
        page = 1
        while max_pages is None or page <= max_pages:
            params = {"page": page, "pageSize": PAGE_SIZE}
            if q:
                params["q"] = q
            payload = _get_json(session, f"{config.TCG_API_BASE}/cards", params)
            cards = payload.get("data", [])
            if not cards:
                break
            rows = [tcg_json.card_row(c) for c in cards]
            snaps = [s for c in cards for s in tcg_json.snapshot_rows(c)]
            total_cards += db.upsert_cards(conn, rows)
            total_snaps += db.insert_snapshots(conn, snaps)
            total_count = payload.get("totalCount", 0)
            progress(f"  {q or 'all cards'}: {min(page * PAGE_SIZE, total_count)}"
                     f"/{total_count} cards ({total_snaps} snapshots so far)")
            if page * PAGE_SIZE >= total_count:
                break
            page += 1
            if max_pages is not None and page > max_pages:
                progress(f"  {q or 'all cards'}: stopped at the --max-pages cap "
                         f"with {total_count - (page - 1) * PAGE_SIZE} cards unfetched")
            time.sleep(0.3)  # be polite to the free API
    return total_cards, total_snaps


def fetch_github_dump(conn: sqlite3.Connection, progress=print) -> loader.IngestReport:
    """Download the full pokemon-tcg-data dump and ingest it (~40 MB zip)."""
    progress(f"Downloading {config.TCG_DATA_ZIP_URL} ...")
    with tempfile.TemporaryDirectory(dir=config.data_dir()) as tmp:
        zip_path = Path(tmp) / "pokemon-tcg-data.zip"
        with requests.get(config.TCG_DATA_ZIP_URL, stream=True, timeout=120) as resp:
            resp.raise_for_status()
            with open(zip_path, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=1 << 20):
                    fh.write(chunk)
        progress(f"Downloaded {zip_path.stat().st_size / 1e6:.1f} MB, ingesting ...")
        return loader.ingest_path(conn, zip_path)
