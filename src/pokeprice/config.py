"""Central configuration. Everything overridable via environment variables."""
from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    d = Path(os.environ.get("POKEPRICE_DATA_DIR", "data"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path() -> Path:
    return Path(os.environ.get("POKEPRICE_DB", data_dir() / "pokeprice.db"))


def model_path() -> Path:
    return Path(os.environ.get("POKEPRICE_MODEL", data_dir() / "model.joblib"))


# Cards below this price are excluded from training and ranking: percentage
# moves on penny cards are mostly bid/ask noise, not signal.
MIN_PRICE = float(os.environ.get("POKEPRICE_MIN_PRICE", "0.25"))

# Forward-looking window (days) that predictions cover by default.
DEFAULT_HORIZON_DAYS = int(os.environ.get("POKEPRICE_HORIZON", "7"))

# "Big move" threshold for the P(gain >= X) classifier.
BIG_GAIN = float(os.environ.get("POKEPRICE_BIG_GAIN", "0.10"))

# Stale-listing filter: training drops observations of listings whose price
# changed in fewer than this fraction of their snapshots so far (once there is
# enough history to judge). Dead vintage listings are noise, not signal.
MIN_ACTIVITY = float(os.environ.get("POKEPRICE_MIN_ACTIVITY", "0.2"))

# "Money makers": the chase rarities that actually trade — commons/uncommons
# sell as bulk. Substring-matched against the rarity so every era's naming
# works (Illustration/Special Illustration Rare, Hyper/Secret/Rainbow,
# Ultra Rare + Rare Ultra full arts, every Rare Holo tier, golds, shinies,
# Amazing/Radiant, ACE SPEC).
CHASE_TERMS = ("illustration", "hyper", "secret", "rainbow", "ultra", "holo",
               "full art", "gold", "shiny", "amazing", "radiant", "ace spec")


def is_chase(rarity) -> bool:
    text = (rarity or "").lower()
    return any(term in text for term in CHASE_TERMS)

TCG_API_BASE = os.environ.get("POKEPRICE_API_BASE", "https://api.pokemontcg.io/v2")
TCG_API_KEY_ENV = "POKEMONTCG_API_KEY"

# Bulk card+price dump maintained by the Pokemon TCG developers.
TCG_DATA_ZIP_URL = (
    "https://github.com/PokemonTCG/pokemon-tcg-data/archive/refs/heads/master.zip"
)
