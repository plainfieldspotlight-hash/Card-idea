import json
from datetime import date

import py7zr
import pytest

from pokeprice import backfill, db


def test_normalize_variant():
    assert backfill.normalize_variant("Normal") == "normal"
    assert backfill.normalize_variant("Holofoil") == "holofoil"
    assert backfill.normalize_variant("Reverse Holofoil") == "reverseHolofoil"
    assert backfill.normalize_variant("1st Edition Holofoil") == "1stEditionHolofoil"
    assert backfill.normalize_variant(None) == "normal"


def test_normalize_number():
    assert backfill.normalize_number("025/172") == "25"
    assert backfill.normalize_number("25") == "25"
    assert backfill.normalize_number("TG12/TG30") == "tg12"
    assert backfill.normalize_number("SWSH050") == "swsh50"
    assert backfill.normalize_number("000") == "000"
    assert backfill.normalize_number(None) == ""


def _seed_catalog(conn):
    db.upsert_cards(conn, [
        {"card_id": "swsh9-25", "name": "Flareon", "set_id": "swsh9",
         "set_name": "Brilliant Stars", "set_release_date": "2022-02-25", "number": "25"},
        {"card_id": "swsh9-26", "name": "Vaporeon", "set_id": "swsh9",
         "set_name": "Brilliant Stars", "set_release_date": "2022-02-25", "number": "26"},
        {"card_id": "sv1-1", "name": "Sprigatito", "set_id": "sv1",
         "set_name": "Scarlet & Violet", "set_release_date": "2023-03-31", "number": "1"},
    ])


GROUPS = [
    {"groupId": 3118, "name": "SWSH09: Brilliant Stars", "abbreviation": "BRS",
     "publishedOn": "2022-02-25T00:00:00"},
    {"groupId": 22873, "name": "SV01: Scarlet & Violet Base Set", "abbreviation": "SVI",
     "publishedOn": "2023-03-31T00:00:00"},
    {"groupId": 99999, "name": "Some Unrelated Game Thing", "publishedOn": "2020-01-01"},
]


def test_set_mapping_via_code_and_name(conn):
    _seed_catalog(conn)
    mapping = backfill.build_set_mapping(conn, GROUPS)
    assert mapping[3118] == "swsh9"   # SWSH09 -> swsh9 via prefix code
    assert mapping[22873] == "sv1"    # SV01 -> sv1
    assert 99999 not in mapping

    scoped = backfill.build_set_mapping(conn, GROUPS, set_ids=["sv1"])
    assert list(scoped) == [22873]


def test_product_mapping_by_number_and_name(conn, monkeypatch):
    _seed_catalog(conn)
    products = {
        3118: [
            {"productId": 111, "name": "Flareon", "cleanName": "Flareon",
             "extendedData": [{"name": "Number", "value": "025/172"}]},
            {"productId": 112, "name": "Vaporeon", "cleanName": "Vaporeon",
             "extendedData": []},  # sealed-style: no number -> name fallback
            {"productId": 113, "name": "Booster Box", "cleanName": "Booster Box",
             "extendedData": []},  # unmatched
        ],
    }
    monkeypatch.setattr(backfill, "fetch_products",
                        lambda session, gid: products.get(gid, []))
    pm = backfill.build_product_mapping(conn, None, {3118: "swsh9"},
                                        progress=lambda *_: None)
    assert pm == {111: "swsh9-25", 112: "swsh9-26"}
    # cached: a second run does not refetch (fetch_products now empty -> same map)
    monkeypatch.setattr(backfill, "fetch_products", lambda s, g: pytest.fail("refetched"))
    pm2 = backfill.build_product_mapping(conn, None, {3118: "swsh9"},
                                         progress=lambda *_: None)
    assert pm2 == pm


def _make_archive(path, day, group_id, rows):
    with py7zr.SevenZipFile(path, "w") as z:
        z.writestr(json.dumps({"success": True, "results": rows}),
                   f"{day}/3/{group_id}/prices")


def test_backfill_end_to_end_offline(conn, tmp_path, monkeypatch):
    _seed_catalog(conn)
    day = "2025-03-02"
    archive = tmp_path / "day.7z"
    _make_archive(archive, day, 3118, [
        {"productId": 111, "marketPrice": 4.2, "lowPrice": 3.0, "midPrice": 4.5,
         "highPrice": 9.0, "subTypeName": "Holofoil"},
        {"productId": 111, "marketPrice": 1.1, "lowPrice": 0.9, "midPrice": 1.2,
         "highPrice": 2.0, "subTypeName": "Reverse Holofoil"},
        {"productId": 424242, "marketPrice": 5.0, "subTypeName": "Normal"},  # unmapped
    ])

    monkeypatch.setattr(backfill, "fetch_groups", lambda session: GROUPS)
    monkeypatch.setattr(backfill, "fetch_products", lambda session, gid: [
        {"productId": 111, "name": "Flareon", "cleanName": "Flareon",
         "extendedData": [{"name": "Number", "value": "025/172"}]},
    ])

    class FakeResp:
        status_code = 200

        def __init__(self, data):
            self._data = data

        def raise_for_status(self):
            return None

        def iter_content(self, size):
            yield self._data

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class FakeSession:
        headers = {}

        def get(self, url, stream=False, timeout=None):
            assert day in url
            return FakeResp(archive.read_bytes())

    monkeypatch.setattr(backfill, "_session", lambda: FakeSession())
    monkeypatch.setenv("POKEPRICE_DATA_DIR", str(tmp_path / "data"))

    result = backfill.backfill(conn, days=1, every=1,
                               end=date.fromisoformat(day),
                               progress=lambda *_: None)
    assert result["snapshots_added"] == 2
    rows = conn.execute(
        "SELECT variant, market, snapshot_date FROM price_snapshots "
        "WHERE card_id = 'swsh9-25' ORDER BY variant").fetchall()
    assert [(r["variant"], r["market"], r["snapshot_date"]) for r in rows] == [
        ("holofoil", 4.2, day), ("reverseHolofoil", 1.1, day)]

    # resume: the day is recorded as done, nothing re-ingested
    result2 = backfill.backfill(conn, days=1, every=1,
                                end=date.fromisoformat(day),
                                progress=lambda *_: None)
    assert result2["days_processed"] == 0


def test_backfill_requires_catalog(conn):
    with pytest.raises(RuntimeError, match="catalog"):
        backfill.backfill(conn, days=1)
