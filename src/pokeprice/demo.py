"""Seed the database with a synthetic-but-realistic demo market.

Lets you exercise the full pipeline (ingest -> train -> predict -> dashboard)
before any real data is loaded. Prices follow a momentum-y random walk with
occasional hype spikes, so the model has genuine (if simplified) structure to
learn. Everything is tagged with set ids starting with "demo" — obviously fake.
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import numpy as np

from . import db

NAMES = [
    "Charizard", "Pikachu", "Umbreon", "Rayquaza", "Gengar", "Mewtwo", "Lugia",
    "Blastoise", "Venusaur", "Sylveon", "Dragonite", "Snorlax", "Eevee",
    "Gyarados", "Alakazam", "Machamp", "Arcanine", "Lapras", "Espeon", "Mew",
    "Tyranitar", "Garchomp", "Lucario", "Greninja", "Zoroark", "Absol",
    "Salamence", "Metagross", "Milotic", "Flareon",
]
SUFFIXES = ["", " ex", " V", " VMAX", " GX", " Holo"]

RARITIES = [
    # (name, base price range, daily vol, spike chance/day)
    ("Common", (0.10, 0.60), 0.010, 0.001),
    ("Uncommon", (0.30, 1.50), 0.012, 0.002),
    ("Rare", (1.00, 5.00), 0.016, 0.004),
    ("Rare Holo", (3.00, 15.00), 0.020, 0.006),
    ("Ultra Rare", (10.00, 80.00), 0.026, 0.010),
    ("Secret Rare", (30.00, 300.00), 0.032, 0.012),
]

SETS = [
    ("demo1", "Demo Base", "Demo Series", 720),
    ("demo2", "Demo Fossil", "Demo Series", 420),
    ("demo3", "Demo Neon Skies", "Demo Modern", 180),
    ("demo4", "Demo Crown Relics", "Demo Modern", 45),
]


def seed(
    conn: sqlite3.Connection,
    n_cards: int = 60,
    days: int = 120,
    step_days: int = 2,
    seed: int = 7,
    end: date | None = None,
) -> dict:
    rng = np.random.default_rng(seed)
    end = end or date.today()

    cards, snapshots = [], []
    for i in range(n_cards):
        name = NAMES[i % len(NAMES)] + SUFFIXES[(i // len(NAMES)) % len(SUFFIXES)]
        rarity, (lo, hi), vol, spike_p = RARITIES[int(rng.integers(len(RARITIES)))]
        set_id, set_name, series, set_age = SETS[int(rng.integers(len(SETS)))]
        card_id = f"{set_id}-{i + 1}"
        cards.append({
            "card_id": card_id,
            "name": name,
            "supertype": "Pokémon",
            "rarity": rarity,
            "set_id": set_id,
            "set_name": set_name,
            "set_series": series,
            "set_release_date": (end - timedelta(days=set_age)).isoformat(),
            "number": str(i + 1),
        })

        # Momentum-y log-price walk: today's drift leans on the trailing week's
        # return (phi > 0), plus rare hype spikes that decay over ~2 weeks.
        price = float(rng.uniform(lo, hi))
        log_p = np.log(price)
        drift = float(rng.normal(0, 0.0006))
        phi = 0.35
        recent: list[float] = []
        spike = 0.0
        use_cardmarket = i % 3 == 0
        history: list[tuple[date, float]] = []
        for d in range(days, -1, -1):
            day = end - timedelta(days=d)
            mom = float(np.mean(recent[-7:])) if recent else 0.0
            if rng.random() < spike_p:
                spike += float(rng.uniform(0.15, 0.5))
            r = drift + phi * mom + float(rng.normal(0, vol)) + spike * 0.15
            spike *= 0.85
            log_p += r
            recent.append(r)
            if d % step_days == 0:
                history.append((day, float(np.exp(log_p))))

        for idx, (day, p) in enumerate(history):
            snapshots.append({
                "card_id": card_id,
                "source": "tcgplayer",
                "variant": "holofoil" if rarity in ("Ultra Rare", "Secret Rare") else "normal",
                "snapshot_date": day.isoformat(),
                "currency": "USD",
                "market": round(p, 2),
                "low": round(p * 0.85, 2),
                "mid": round(p * 1.05, 2),
                "high": round(p * 1.25, 2),
            })
            if use_cardmarket:
                # An independently noisy echo of the USD series, so the two
                # markets track each other without being identical.
                fx = 0.92 * (1.0 + float(rng.normal(0, 0.02)))
                trailing = [q for _, q in history[max(0, idx - 15) : idx + 1]]
                snapshots.append({
                    "card_id": card_id,
                    "source": "cardmarket",
                    "variant": "normal",
                    "snapshot_date": day.isoformat(),
                    "currency": "EUR",
                    "market": round(p * fx, 2),
                    "low": round(p * fx * 0.87, 2),
                    "avg1": round(p * fx * 1.01, 2),
                    "avg7": round(float(np.mean(trailing[-4:])) * 0.92, 2),
                    "avg30": round(float(np.mean(trailing)) * 0.92, 2),
                })

    n_cards_inserted = db.upsert_cards(conn, cards)
    n_snaps = db.insert_snapshots(conn, snapshots)
    return {"cards": n_cards_inserted, "snapshots": n_snaps}
