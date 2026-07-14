"""Walk a zip / directory / file, detect each entry's format, load into SQLite.

This is the entry point for `pokeprice ingest pokemon.zip` — it doesn't care
how the archive is laid out, it inspects every .json/.csv inside (including
nested zips) and ingests whatever it recognizes.
"""
from __future__ import annotations

import io
import json
import sqlite3
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from .. import db
from . import csv_ingest, tcg_json

SKIP_DIR_PARTS = {"__MACOSX", ".git", "node_modules"}


@dataclass
class IngestReport:
    cards: int = 0
    snapshots: int = 0
    files_ingested: int = 0
    files_skipped: list[str] = field(default_factory=list)
    csv_mappings: dict[str, dict] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"Ingested {self.cards} card records and {self.snapshots} new price "
            f"snapshots from {self.files_ingested} file(s).",
        ]
        for name, mapping in self.csv_mappings.items():
            lines.append(f"  CSV {name}: mapped columns {mapping}")
        if self.files_skipped:
            shown = ", ".join(self.files_skipped[:8])
            more = f" (+{len(self.files_skipped) - 8} more)" if len(self.files_skipped) > 8 else ""
            lines.append(f"  Skipped unrecognized: {shown}{more}")
        for err in self.errors:
            lines.append(f"  WARNING: {err}")
        return "\n".join(lines)


def _iter_entries(path: Path):
    """Yield (display_name, bytes) for every data file under path (zip or dir or file)."""
    def from_zip(data: bytes, prefix: str):
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                parts = PurePosixPath(info.filename).parts
                if any(p in SKIP_DIR_PARTS for p in parts):
                    continue
                name = f"{prefix}{info.filename}"
                suffix = PurePosixPath(info.filename).suffix.lower()
                if suffix == ".zip":
                    yield from from_zip(zf.read(info), f"{name}!/")
                elif suffix in (".json", ".csv", ".txt"):
                    yield name, zf.read(info)

    if path.is_dir():
        for child in sorted(path.rglob("*")):
            if not child.is_file() or any(p in SKIP_DIR_PARTS for p in child.parts):
                continue
            suffix = child.suffix.lower()
            if suffix == ".zip":
                yield from from_zip(child.read_bytes(), f"{child.name}!/")
            elif suffix in (".json", ".csv", ".txt"):
                yield str(child.relative_to(path)), child.read_bytes()
    elif path.suffix.lower() == ".zip":
        yield from from_zip(path.read_bytes(), f"{path.name}!/")
    else:
        yield path.name, path.read_bytes()


def _ingest_json(
    conn: sqlite3.Connection, name: str, payload, default_date: str | None,
    report: IngestReport, set_index: dict[str, dict],
) -> bool:
    if tcg_json.looks_like_sets(payload):
        for s in payload:
            set_index[str(s.get("id"))] = s
        report.files_ingested += 1
        return True
    if not tcg_json.looks_like_cards(payload):
        return False
    cards, snaps = [], []
    for card in tcg_json.iter_cards(payload):
        set_info = None
        if "set" not in card:
            # pokemon-tcg-data names card files after their set id (cards/en/sv1.json)
            stem = PurePosixPath(name).stem
            set_info = set_index.get(stem) or set_index.get(str(card["id"]).rsplit("-", 1)[0])
        cards.append(tcg_json.card_row(card, set_info))
        snaps.extend(tcg_json.snapshot_rows(card, default_date))
    report.cards += db.upsert_cards(conn, cards)
    report.snapshots += db.insert_snapshots(conn, snaps)
    report.files_ingested += 1
    return True


def ingest_path(
    conn: sqlite3.Connection, path: Path | str, default_date: str | None = None
) -> IngestReport:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist")
    report = IngestReport()
    set_index: dict[str, dict] = {}
    entries = list(_iter_entries(path))

    # Two passes so sets/en.json metadata is available before card files that
    # rely on it, regardless of archive ordering.
    json_entries, other_entries = [], []
    for name, data in entries:
        (json_entries if name.lower().endswith(".json") else other_entries).append((name, data))
    for name, data in json_entries:
        try:
            payload = json.loads(data.decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            report.errors.append(f"{name}: invalid JSON ({exc})")
            continue
        if tcg_json.looks_like_sets(payload):
            for s in payload:
                set_index[str(s.get("id"))] = s
            report.files_ingested += 1
    for name, data in json_entries:
        try:
            payload = json.loads(data.decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue  # already reported above
        if tcg_json.looks_like_sets(payload):
            continue
        if not _ingest_json(conn, name, payload, default_date, report, set_index):
            report.files_skipped.append(name)

    for name, data in other_entries:
        lower = name.lower()
        try:
            if lower.endswith(".csv") or lower.endswith(".txt"):
                text = data.decode("utf-8", errors="replace")
                header = text.splitlines()[0].split(",") if text.strip() else []
                if not csv_ingest.looks_like_cards_csv(header):
                    report.files_skipped.append(name)
                    continue
                cards, snaps, mapping = csv_ingest.parse_csv(text, default_date)
                report.cards += db.upsert_cards(conn, cards)
                report.snapshots += db.insert_snapshots(conn, snaps)
                report.csv_mappings[name] = mapping
                report.files_ingested += 1
            else:
                report.files_skipped.append(name)
        except Exception as exc:  # keep going: one bad file shouldn't sink the archive
            report.errors.append(f"{name}: {exc}")
    return report
