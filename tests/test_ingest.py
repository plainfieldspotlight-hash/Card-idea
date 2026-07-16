import json
import zipfile

from pokeprice.ingest import ingest_path

API_CARD = {
    "id": "test-1",
    "name": "Testachu",
    "supertype": "Pokémon",
    "rarity": "Rare",
    "number": "1",
    "set": {"id": "test", "name": "Test Set", "series": "Testing",
            "releaseDate": "2024/01/05"},
    "images": {"small": "https://example.com/s.png"},
    "tcgplayer": {
        "url": "https://example.com",
        "updatedAt": "2025/06/01",
        "prices": {
            "normal": {"low": 1.0, "mid": 2.0, "high": 4.0, "market": 2.2},
            "holofoil": {"low": 5.0, "mid": 8.0, "high": 12.0, "market": 7.5},
        },
    },
    "cardmarket": {
        "url": "https://example.com",
        "updatedAt": "2025/06/01",
        "prices": {"trendPrice": 2.4, "lowPrice": 1.1, "averageSellPrice": 2.3,
                   "avg1": 2.5, "avg7": 2.2, "avg30": 2.0,
                   "reverseHoloTrend": 3.1, "reverseHoloAvg7": 3.0},
    },
}

# pokemon-tcg-data style: no embedded "set", the file name carries the set id
DUMP_CARD = {
    "id": "xy9-20",
    "name": "Dumpmander",
    "supertype": "Pokémon",
    "rarity": "Uncommon",
    "number": "20",
    "tcgplayer": {"updatedAt": "2025/06/02",
                  "prices": {"normal": {"market": 0.55, "low": 0.3, "mid": 0.6, "high": 1.0}}},
}

SETS = [{"id": "xy9", "name": "BREAKpoint", "series": "XY", "releaseDate": "2016/02/03"}]

CSV = """Card Name,Set,Rarity,Market Price,Low Price,Date
Csvmon,Paper Set,Rare,3.50,2.00,2025-06-03
Csvmon two,Paper Set,Common,$0.99,0.50,2025-06-03
"""


def make_zip(path):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("cards/api_page.json", json.dumps({"data": [API_CARD]}))
        zf.writestr("cards/en/xy9.json", json.dumps([DUMP_CARD]))
        zf.writestr("sets/en.json", json.dumps(SETS))
        zf.writestr("prices.csv", CSV)
        zf.writestr("notes/readme.txt", "not a data file")
        zf.writestr("misc/other.json", json.dumps({"hello": "world"}))


def test_ingest_mixed_zip(conn, tmp_path):
    zip_path = tmp_path / "pokemon.zip"
    make_zip(zip_path)
    report = ingest_path(conn, zip_path)

    assert report.cards == 4  # api card + dump card + 2 csv rows
    assert not report.errors
    names = {r["name"] for r in conn.execute("SELECT name FROM cards")}
    assert names == {"Testachu", "Dumpmander", "Csvmon", "Csvmon two"}

    # tcgplayer normal + holofoil; the card's cardmarket (EUR) block is
    # ignored on purpose — the app is USD-only
    variants = {
        (r["source"], r["variant"])
        for r in conn.execute(
            "SELECT source, variant FROM price_snapshots WHERE card_id='test-1'"
        )
    }
    assert variants == {
        ("tcgplayer", "normal"), ("tcgplayer", "holofoil"),
    }

    # set metadata resolved from sets/en.json for the dump-style card
    row = conn.execute("SELECT set_name, set_release_date FROM cards WHERE card_id='xy9-20'").fetchone()
    assert row["set_name"] == "BREAKpoint"
    assert row["set_release_date"] == "2016-02-03"

    # csv fuzzy mapping: $ sign stripped, date parsed
    csv_snap = conn.execute(
        "SELECT market, snapshot_date FROM price_snapshots "
        "WHERE card_id LIKE 'csv-csvmon-two%'"
    ).fetchone()
    assert csv_snap["market"] == 0.99
    assert csv_snap["snapshot_date"] == "2025-06-03"

    # junk files skipped, not fatal
    assert any("other.json" in s for s in report.files_skipped)


def test_reingest_is_idempotent(conn, tmp_path):
    zip_path = tmp_path / "pokemon.zip"
    make_zip(zip_path)
    first = ingest_path(conn, zip_path)
    second = ingest_path(conn, zip_path)
    assert first.snapshots > 0
    assert second.snapshots == 0  # same (card, source, variant, date) rows ignored
    total = conn.execute("SELECT COUNT(*) FROM price_snapshots").fetchone()[0]
    assert total == first.snapshots


def test_ingest_plain_csv_file(conn, tmp_path):
    csv_path = tmp_path / "prices.csv"
    csv_path.write_text(CSV)
    report = ingest_path(conn, csv_path)
    assert report.cards == 2
    assert report.snapshots == 2
    assert "prices.csv" in report.csv_mappings
