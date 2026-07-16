"""Parser for Pokemon TCG card JSON.

Handles the format used by api.pokemontcg.io and the PokemonTCG/pokemon-tcg-data
GitHub dump: card objects with optional `tcgplayer.prices` (USD, one block per
print variant). A file may be a bare card list, an API envelope
{"data": [...]}, or a single card object.

The app is USD-only: `cardmarket.prices` blocks (EUR) are ignored on purpose —
mixing currencies muddied every price comparison for no extra signal.
"""
from __future__ import annotations

from datetime import date
from typing import Iterable, Mapping

TCGPLAYER_PRICE_KEYS = ("low", "mid", "high", "market", "directLow")


def _parse_date(value, fallback: str | None = None) -> str | None:
    """Normalize '2023/04/01' or '2023-04-01' (optionally with time) to ISO."""
    if not value:
        return fallback
    text = str(value).strip().replace("/", "-")[:10]
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return fallback


def looks_like_cards(payload) -> bool:
    if isinstance(payload, Mapping) and isinstance(payload.get("data"), list):
        payload = payload["data"]
    if isinstance(payload, Mapping):
        payload = [payload]
    if not isinstance(payload, list) or not payload:
        return False
    sample = payload[0]
    return isinstance(sample, Mapping) and "id" in sample and "name" in sample


def iter_cards(payload) -> Iterable[Mapping]:
    if isinstance(payload, Mapping) and isinstance(payload.get("data"), list):
        payload = payload["data"]
    if isinstance(payload, Mapping):
        payload = [payload]
    for item in payload:
        if isinstance(item, Mapping) and item.get("id") and item.get("name"):
            yield item


def card_row(card: Mapping, set_info: Mapping | None = None) -> dict:
    s = card.get("set") or set_info or {}
    images = card.get("images") or {}
    return {
        "card_id": str(card["id"]),
        "name": card.get("name"),
        "supertype": card.get("supertype"),
        "subtypes": card.get("subtypes"),
        "rarity": card.get("rarity"),
        "set_id": s.get("id"),
        "set_name": s.get("name"),
        "set_series": s.get("series"),
        "set_release_date": _parse_date(s.get("releaseDate")),
        "number": str(card.get("number")) if card.get("number") is not None else None,
        "artist": card.get("artist"),
        "image_small": images.get("small"),
        "image_large": images.get("large"),
        "tcgplayer_url": (card.get("tcgplayer") or {}).get("url"),
        "cardmarket_url": (card.get("cardmarket") or {}).get("url"),
    }


def snapshot_rows(card: Mapping, default_date: str | None = None) -> list[dict]:
    """Extract one price snapshot per (source, variant) present on the card."""
    rows: list[dict] = []
    card_id = str(card["id"])
    default_date = default_date or date.today().isoformat()

    tcg = card.get("tcgplayer") or {}
    tcg_date = _parse_date(tcg.get("updatedAt"), default_date)
    for variant, prices in (tcg.get("prices") or {}).items():
        if not isinstance(prices, Mapping):
            continue
        rows.append({
            "card_id": card_id,
            "source": "tcgplayer",
            "variant": variant,
            "snapshot_date": tcg_date,
            "currency": "USD",
            "market": prices.get("market"),
            "low": prices.get("low"),
            "mid": prices.get("mid"),
            "high": prices.get("high"),
            "direct_low": prices.get("directLow"),
        })

    return [r for r in rows if r.get("market") or r.get("mid") or r.get("low")]


def looks_like_sets(payload) -> bool:
    """The pokemon-tcg-data repo ships sets/en.json: set objects without prices."""
    if not isinstance(payload, list) or not payload:
        return False
    sample = payload[0]
    return (
        isinstance(sample, Mapping)
        and "id" in sample
        and "name" in sample
        and ("releaseDate" in sample or "series" in sample)
        and "supertype" not in sample
    )
