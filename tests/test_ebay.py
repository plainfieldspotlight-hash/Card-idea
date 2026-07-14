import pytest

from pokeprice import ebay

CARD = {"name": "Charizard ex", "set_name": "Obsidian Flames", "number": "125"}


def test_search_query_and_url():
    q = ebay.search_query(CARD, "holofoil")
    assert q == "pokemon Charizard ex Obsidian Flames 125 holo"
    url = ebay.search_url(CARD, "reverseHolofoil")
    assert url.startswith("https://www.ebay.com/sch/i.html?_nkw=pokemon+Charizard")
    assert "reverse+holo" in url
    assert "LH_BIN=1" in url  # fixed-price only
    assert "holo" not in ebay.search_query(CARD, "normal")


def test_credentials_absent(monkeypatch):
    monkeypatch.delenv("EBAY_CLIENT_ID", raising=False)
    monkeypatch.delenv("EBAY_CLIENT_SECRET", raising=False)
    assert ebay.credentials() is None
    assert ebay.fetch_listings(CARD) == []  # no creds -> no live mode, no crash


def test_annotate_vs_market():
    items = [
        {"price": 90.0, "currency": "USD"},
        {"price": 120.0, "currency": "USD"},
        {"price": 80.0, "currency": "EUR"},   # different currency: not comparable
        {"price": None, "currency": "USD"},
    ]
    out = ebay.annotate_vs_market(items, market_price=100.0, market_currency="USD")
    assert out[0]["vs_market"] == pytest.approx(-0.1)
    assert out[1]["vs_market"] == pytest.approx(0.2)
    assert out[2]["vs_market"] is None
    assert out[3]["vs_market"] is None
