"""eBay purchase surfacing.

Two modes, degrading gracefully:

* **link** (zero config) — build a targeted eBay search URL for the card, so
  every card gets a one-click "buy it on eBay" path.
* **live** — when EBAY_CLIENT_ID / EBAY_CLIENT_SECRET are set (an eBay
  developer keyset), query the Browse API for current fixed-price listings
  and compare each against our tracked market price to flag potential deals.

Tokens (client-credentials flow) and per-card results are cached in-process.
"""
from __future__ import annotations

import base64
import os
import time
from urllib.parse import quote_plus

import requests

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
BROWSE_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
SCOPE = "https://api.ebay.com/oauth/api_scope"

_token: dict = {"value": None, "expires": 0.0}
_cache: dict[str, tuple[float, list]] = {}
CACHE_TTL_S = 900


def credentials() -> tuple[str, str] | None:
    cid = os.environ.get("EBAY_CLIENT_ID")
    secret = os.environ.get("EBAY_CLIENT_SECRET")
    return (cid, secret) if cid and secret else None


def search_query(card: dict, variant: str | None = None) -> str:
    parts = ["pokemon", card.get("name") or ""]
    if card.get("set_name"):
        parts.append(card["set_name"])
    if card.get("number"):
        parts.append(str(card["number"]))
    if variant and variant not in ("normal",):
        # tcgplayer variant keys -> words buyers actually search
        pretty = {"holofoil": "holo", "reverseHolofoil": "reverse holo",
                  "1stEditionHolofoil": "1st edition holo",
                  "1stEditionNormal": "1st edition"}.get(variant, variant)
        parts.append(pretty)
    return " ".join(p for p in parts if p).strip()


def search_url(card: dict, variant: str | None = None) -> str:
    return ("https://www.ebay.com/sch/i.html?_nkw=" +
            quote_plus(search_query(card, variant)) + "&LH_BIN=1")


def _get_token(session: requests.Session) -> str | None:
    creds = credentials()
    if not creds:
        return None
    if _token["value"] and time.time() < _token["expires"] - 60:
        return _token["value"]
    basic = base64.b64encode(f"{creds[0]}:{creds[1]}".encode()).decode()
    resp = session.post(
        TOKEN_URL,
        headers={"Authorization": f"Basic {basic}",
                 "Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "client_credentials", "scope": SCOPE},
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    _token["value"] = payload["access_token"]
    _token["expires"] = time.time() + int(payload.get("expires_in", 7200))
    return _token["value"]


def fetch_listings(card: dict, variant: str | None = None, limit: int = 5,
                   session: requests.Session | None = None) -> list[dict]:
    """Current fixed-price listings for the card (live mode only)."""
    query = search_query(card, variant)
    now = time.time()
    cached = _cache.get(query)
    if cached and now - cached[0] < CACHE_TTL_S:
        return cached[1]
    session = session or requests.Session()
    token = _get_token(session)
    if token is None:
        return []
    params = {
        "q": query,
        "limit": str(limit),
        "filter": "buyingOptions:{FIXED_PRICE}",
    }
    if os.environ.get("EBAY_CATEGORY_ID"):
        params["category_ids"] = os.environ["EBAY_CATEGORY_ID"]
    resp = session.get(
        BROWSE_URL, params=params,
        headers={"Authorization": f"Bearer {token}",
                 "X-EBAY-C-MARKETPLACE-ID": os.environ.get("EBAY_MARKETPLACE", "EBAY_US")},
        timeout=30,
    )
    resp.raise_for_status()
    items = []
    for it in resp.json().get("itemSummaries", []) or []:
        price = it.get("price") or {}
        items.append({
            "title": it.get("title"),
            "price": float(price["value"]) if price.get("value") else None,
            "currency": price.get("currency"),
            "url": it.get("itemWebUrl"),
            "image": (it.get("image") or {}).get("imageUrl"),
            "condition": it.get("condition"),
        })
    _cache[query] = (now, items)
    return items


INSIGHTS_URL = "https://api.ebay.com/buy/marketplace_insights/v1_beta/item_sales/search"
_insights_blocked = {"until": 0.0}


def fetch_sold(card: dict, variant: str | None = None, limit: int = 8,
               session: requests.Session | None = None) -> list[dict]:
    """Recent sold prices via the Marketplace Insights API.

    This API is approval-gated (apply at developer.ebay.com); most keysets get
    403. We probe once, then back off for a day so the card panel stays fast.
    """
    if time.time() < _insights_blocked["until"]:
        return []
    session = session or requests.Session()
    token = _get_token(session)
    if token is None:
        return []
    resp = session.get(
        INSIGHTS_URL,
        params={"q": search_query(card, variant), "limit": str(limit)},
        headers={"Authorization": f"Bearer {token}",
                 "X-EBAY-C-MARKETPLACE-ID": os.environ.get("EBAY_MARKETPLACE", "EBAY_US")},
        timeout=30,
    )
    if resp.status_code == 403:
        _insights_blocked["until"] = time.time() + 86400
        return []
    resp.raise_for_status()
    sold = []
    for it in resp.json().get("itemSales", []) or []:
        price = it.get("lastSoldPrice") or {}
        sold.append({
            "title": it.get("title"),
            "price": float(price["value"]) if price.get("value") else None,
            "currency": price.get("currency"),
            "sold_date": (it.get("lastSoldDate") or "")[:10] or None,
            "url": it.get("itemWebUrl"),
        })
    return sold


def annotate_vs_market(items: list[dict], market_price: float | None,
                       market_currency: str | None) -> list[dict]:
    """Attach vs_market (fraction below/above our tracked price) where comparable."""
    out = []
    for it in items:
        it = dict(it)
        if (market_price and it.get("price")
                and it.get("currency") == (market_currency or "USD")):
            it["vs_market"] = it["price"] / market_price - 1.0
        else:
            it["vs_market"] = None
        out.append(it)
    return out
