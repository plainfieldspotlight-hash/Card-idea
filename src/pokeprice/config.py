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


def model_path(horizon_days: int | None = None) -> Path:
    """Where the trained bundle for a horizon lives.

    The default horizon keeps the legacy `model.joblib` name so existing
    installs keep working; other horizons get `model-{h}d.joblib`. A
    POKEPRICE_MODEL override names the default-horizon file and the other
    horizons derive from it (`/x/m.joblib` -> `/x/m-30d.joblib`)."""
    default = horizon_days is None or horizon_days == DEFAULT_HORIZON_DAYS
    override = os.environ.get("POKEPRICE_MODEL")
    if override:
        p = Path(override)
        return p if default else p.with_name(f"{p.stem}-{horizon_days}d{p.suffix}")
    if default:
        return data_dir() / "model.joblib"
    return data_dir() / f"model-{horizon_days}d.joblib"


# The app's focus floor: cards below this price are excluded from training,
# predictions, and the action screens. Cheap cards are bulk — percentage moves
# on them are bid/ask noise and the dollars don't matter. Snapshots still get
# stored, so lowering the floor later brings the history with it.
MIN_PRICE = float(os.environ.get("POKEPRICE_MIN_PRICE", "30"))

# A listing needs at least this many price snapshots before it's trained on
# or scored. One or two sightings tell the model nothing — worse, sparse
# listings' labels all come from the same few fetch dates, so a model trained
# on them learns "no history = huge move" and pollutes the gainer lists.
MIN_HIST = int(os.environ.get("POKEPRICE_MIN_HIST", "3"))

# Forward-looking window (days) that predictions cover by default.
DEFAULT_HORIZON_DAYS = int(os.environ.get("POKEPRICE_HORIZON", "7"))

# All horizons trained/predicted by default (`predict` and the auto-fetch
# cycle produce one run per horizon; the dashboard shows them side by side).
HORIZONS = tuple(int(h) for h in
                 os.environ.get("POKEPRICE_HORIZONS", "7,30,60").split(","))

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


# Money makers are the whole product focus: the dashboard scopes to them by
# default and the auto-fetch cycle trains the chase model. POKEPRICE_CHASE=0
# reverts to the everything model.
CHASE_DEFAULT = os.environ.get("POKEPRICE_CHASE", "1") == "1"

# Matt's taxonomy as one-click buckets. Each bucket matches rarities containing
# any `any` term and none of the `none` terms (IR must not swallow SIR).
CHASE_BUCKETS = {
    "full-art": {"label": "Full Art / Ultra", "any": ("ultra", "full art"), "none": ()},
    "ir": {"label": "IR", "any": ("illustration",), "none": ("special",)},
    "sir": {"label": "SIR", "any": ("special illustration",), "none": ()},
    "secret": {"label": "Secret / Hyper", "any": ("secret", "hyper", "rainbow", "gold"),
               "none": ()},
    "holo": {"label": "Holos", "any": ("holo",), "none": ()},
    "shiny": {"label": "Shiny / Radiant", "any": ("shiny", "amazing", "radiant"),
              "none": ()},
}


# Graded-card variants: a PSA 10 is a different asset than the same card raw,
# so graded copies live as their own listings (source=pricecharting). The
# metadata here powers the Condition filters (raw vs graded, company, grade).
GRADING_COMPANIES = ("PSA", "BGS", "CGC", "SGC")
GRADED_VARIANTS = {
    "grade7":  {"company": None, "grade": "7"},
    "grade8":  {"company": None, "grade": "8"},
    "grade9":  {"company": None, "grade": "9"},
    "grade95": {"company": None, "grade": "9.5"},
    "psa9":    {"company": "PSA", "grade": "9"},
    "psa10":   {"company": "PSA", "grade": "10"},
    "bgs95":   {"company": "BGS", "grade": "9.5"},
    "bgs10":   {"company": "BGS", "grade": "10"},
    "cgc10":   {"company": "CGC", "grade": "10"},
    "sgc10":   {"company": "SGC", "grade": "10"},
}


def graded_variant_names(company: str | None = None,
                         grade: str | None = None) -> list[str]:
    """Variant keys matching the requested company/grade (None = any).

    Company-agnostic grades (PriceCharting's blended 'grade9' etc.) only
    surface when no specific company is requested.
    """
    out = []
    for name, meta in GRADED_VARIANTS.items():
        if company and meta["company"] != company:
            continue
        if grade and meta["grade"] != grade:
            continue
        out.append(name)
    return out


def in_bucket(rarity, bucket: str) -> bool:
    spec = CHASE_BUCKETS.get(bucket)
    if spec is None:
        return True
    text = (rarity or "").lower()
    return (any(t in text for t in spec["any"])
            and not any(t in text for t in spec["none"]))

TCG_API_BASE = os.environ.get("POKEPRICE_API_BASE", "https://api.pokemontcg.io/v2")
TCG_API_KEY_ENV = "POKEMONTCG_API_KEY"

# Bulk card+price dump maintained by the Pokemon TCG developers.
TCG_DATA_ZIP_URL = (
    "https://github.com/PokemonTCG/pokemon-tcg-data/archive/refs/heads/master.zip"
)
