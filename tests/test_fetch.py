"""fetch_api pagination: crawl until the API says done — no silent truncation."""
from pokeprice import fetch


class FakeResp:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeSession:
    """Serves `total` fake cards in pages of 250, like the live API."""

    def __init__(self, total=700):
        self.total = total
        self.headers = {}
        self.pages_served = []

    def get(self, url, params=None, timeout=None):
        page = params["page"]
        self.pages_served.append(page)
        start = (page - 1) * 250
        n = max(0, min(250, self.total - start))
        cards = [{
            "id": f"t-{start + i}", "name": f"Card {start + i}",
            "set": {"id": "t", "name": "Test Set"},
            "tcgplayer": {"updatedAt": "2026/07/17",
                          "prices": {"normal": {"market": 45.0, "low": 40.0}}},
        } for i in range(n)]
        return FakeResp({"data": cards, "totalCount": self.total})


def test_fetch_all_pages_until_api_done(conn, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_: None)
    session = FakeSession(total=700)
    cards, snaps = fetch.fetch_api(conn, session=session, progress=lambda *_: None)
    # the old default cap (50 pages = 12,500 cards) silently cut off full
    # crawls; now the crawl runs to the API's own totalCount
    assert session.pages_served == [1, 2, 3]
    assert cards == 700
    assert snaps == 700
    assert conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 700


def test_max_pages_cap_is_optional_and_explicit(conn, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_: None)
    session = FakeSession(total=700)
    cards, _ = fetch.fetch_api(conn, session=session, max_pages=1,
                               progress=lambda *_: None)
    assert session.pages_served == [1]
    assert cards == 250
