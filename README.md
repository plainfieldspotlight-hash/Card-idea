# pokeprice — Pokemon card price radar

Track Pokemon card prices over time and predict short-term price movements.
Ingest your own data dumps (`pokemon.zip` and friends), pull live prices from
the Pokemon TCG API, train a gradient-boosted model on the accumulated history,
and browse ranked "predicted movers" in a local web dashboard.

![Dashboard](docs/dashboard.png)

## Quickstart

```bash
pip install -e ".[dev]"

# See the whole pipeline instantly on a synthetic demo market:
pokeprice demo --reset
pokeprice train
pokeprice predict
pokeprice serve            # open http://127.0.0.1:8000
```

## Using your own data (e.g. `pokemon.zip`)

Point `ingest` at a zip, folder, CSV, or JSON — it walks everything inside
(nested folders and zips included) and auto-detects the format:

```bash
pokeprice ingest ~/Downloads/pokemon.zip
pokeprice ingest my_prices.csv --as-of 2026-07-01   # date for undated files
```

Recognized formats:

- **Pokemon TCG API / pokemon-tcg-data JSON** — card objects with
  `tcgplayer.prices` (USD) and/or `cardmarket.prices` (EUR), as bare arrays,
  `{"data": [...]}` envelopes, or per-set files with a `sets/en.json` index.
- **CSV with fuzzy column mapping** — headers like `Card Name / name / title`,
  `Market Price / price / value`, `Set`, `Rarity`, `Date`, `Low/Mid/High` are
  matched case- and punctuation-insensitively; `$`/`€` signs are stripped. The
  ingest report prints exactly which columns were mapped.

Re-ingesting the same file is idempotent — snapshots are keyed by
(card, source, variant, date). If your dump isn't recognized, `ingest` lists
the skipped files so the parser can be extended.

## Getting price history (the important part)

Movement prediction needs *history*, not just current prices — and you don't
have to wait for it to accumulate:

```bash
pokeprice fetch --sets sv8,sv9    # catalog + today's prices (see `pokeprice sets`)
pokeprice backfill                # REAL daily TCGplayer history, months of it, in minutes
pokeprice backfill --days 365 --every 1 --sets sv8,sv9   # deeper + daily + targeted
```

`backfill` pulls tcgcsv.com's archives of TCGplayer's daily price feed
(every day since 2024-02-08, ~3 MB/day), matches the products to your card
catalog by set code + collector number, and stores them as ordinary dated
snapshots — so the model can train on years of genuine market data
immediately. It's resumable and idempotent; re-running only fetches new days.
(`fetch --github` grabs the card *catalog* without an API key — the dump has
no prices, so pair it with `backfill`.)

Then keep history growing automatically — no cron needed:

```bash
pokeprice serve --auto-fetch daily            # API fetch -> train -> predict -> alerts, daily
pokeprice serve --auto-fetch 12h --auto-fetch-sets sv8,sv9   # lighter, targeted
```

The dashboard shows the auto-fetch status as a stat tile (interval, last run,
ok/failed). Prefer external scheduling? The equivalent cron line:

```cron
0 7 * * *  cd /path/to/Card-idea && pokeprice fetch --all && pokeprice predict
```

An [API key](https://dev.pokemontcg.io/) via `POKEMONTCG_API_KEY` raises the
Pokemon TCG API rate limits (optional but recommended for full crawls).

Verified on real data: two sets backfilled over 60 days (13.5k snapshots)
train to ~59% direction accuracy and 0.27 rank IC on a held-out window —
similar to the synthetic-market results, now on genuine prices.

## Trusting the model (or knowing not to)

- **Model report card** (`pokeprice report`, dashboard section) — every stored
  prediction is scored against the realized price once snapshots arrive
  ~horizon days later: live hit rate, rank IC, and range coverage, broken down
  by price tier and rarity. The model earns trust in public, or visibly doesn't.
- **Uncertainty ranges** — quantile regressors predict a 10th–90th percentile
  band alongside the point estimate ("+2% … +15%"), and the buys section ranks
  by **worst case** by default: a card only tops the list when even its
  pessimistic outcome looks good (`/api/buys?rank=expected` for the old way).
- **P(+10%)** — a dedicated classifier estimates the chance of a big move, not
  just the average one; shown on card detail.
- **Backtest** (`pokeprice backtest`, dashboard button) — frozen-model
  walk-forward on held-out dates: train on the past, trade the model's top
  picks weekly through data it never saw, **including marketplace fees**. It
  reports strategy-after-fees vs the raw signal vs just-holding — on the demo
  market the signal is real (+56% gross) and weekly flipping still loses to
  ~13% fees, which is exactly the honest lesson.
- **Cross-card features** — set momentum and same-character momentum
  (leave-one-out, so a card never sees itself) plus hype-event recency
  (`pokeprice event --date ... --note "reprint" --match charizard`). On the
  demo market these lifted direction accuracy 57%→63% and IC 0.27→0.33.

## How prediction works

Every observation of a listing (a card × source × variant series) on a snapshot
date becomes a feature row: trailing 1/7/30-day returns, volatility, bid–ask
spread, Cardmarket's embedded 1/7/30-day averages (momentum that works even from
a single dump), price level, rarity, set age, and history depth. The label is
the forward return to the snapshot ~`horizon` days later (default 7).

- **Model**: `HistGradientBoosting` regressor (expected return) + classifier
  (P(up)), with NaN-tolerant features and native categoricals.
- **Honest evaluation**: time-ordered split — trained on the past, validated on
  the most recent ~20% of dates. `train` reports MAE vs a predict-zero
  baseline, direction accuracy, and Spearman IC (rank correlation between
  predicted and realized returns — the "does the ranking work" number).
- **Leakage control**: trailing lookups tolerate irregular snapshot spacing but
  can never resolve to the row's own date or later.
- **Cold start**: with no trained model, `predict` falls back to a damped
  momentum heuristic, tagged `momentum` everywhere it surfaces.
- Cards under `POKEPRICE_MIN_PRICE` (default $0.25) are excluded — percentage
  moves on penny cards are bid/ask noise.

On the demo market (a momentum-y random walk with hype spikes) the model reaches
~57% direction accuracy and ~0.27 Spearman IC on the holdout — it finds the
planted signal. Real markets are harder; treat the numbers `train` prints as the
truth about your data.

## Dashboard

`pokeprice serve` gives you: stat tiles, top predicted gainers/losers,
**high-confidence buys** bucketed into four price tiers (over $1,000 ·
$500–$1,000 · $100–$500 · $100 or less — listings with P(up) ≥ 70% and a
predicted move ≥ +2%, tunable via `/api/buys?min_prob=&min_return=`), a
searchable/sortable table (price, 7d change, 30d sparkline, predicted move,
P(up)), and per-card detail with multi-series price history, crosshair tooltip,
and a table view. Light and dark mode. When a card trades in both USD
(TCGplayer) and EUR (Cardmarket), the chart indexes both series to 100 rather
than mixing currencies on one axis.

![Card detail](docs/detail-dark.png)

**My collection** — track what you own: add listings from any card's detail
panel, or bulk-**import a CSV** (TCGplayer collection export or a spreadsheet
with name/set/quantity/paid columns). Totals — portfolio value, cost basis,
unrealized gain, predicted 7-day move — are strict USD; EUR converts at the
ECB daily rate (cached, offline-safe).

**Watchlist & alerts** — star any card to track it without owning it. Alert
rules run over everything you track after each auto-fetch (and via
`pokeprice alerts`): model turns bullish (P(up) and predicted move clear your
bars), a card swings hard over 7 days, or your portfolio drops X%. Alerts
always log in-app, and deliver to Discord (`DISCORD_WEBHOOK_URL`) and/or email
(`SMTP_HOST/PORT/USER/PASSWORD`, `ALERT_EMAIL_FROM/TO`) when configured.
Thresholds are editable in the dashboard.

**Buying on eBay** — every card and pick links to a targeted fixed-price eBay
search. With an [eBay developer keyset](https://developer.ebay.com/)
(`EBAY_CLIENT_ID`/`EBAY_CLIENT_SECRET`) the **deal radar** crosses the two
signals that matter: cards the model likes AND live eBay listings below your
tracked market price. Card detail also shows a **max-bid calculator** (worst-
case predicted sale minus your fee % and shipping = the most you can pay and
still expect profit) and, where the approval-gated Marketplace Insights API is
available, recent **sold comps**. Optional: `EBAY_MARKETPLACE`, `EBAY_CATEGORY_ID`.

**Graded cards** — with a [PriceCharting](https://www.pricecharting.com/api-documentation)
token (`PRICECHARTING_TOKEN`), `pokeprice graded <card_id>` stores
PSA 10 / grade 9 / ungraded price points as their own listings
(source=`pricecharting`), so graded copies get their own series and predictions.

The JSON API behind it: `/api/stats`, `/api/cards`, `/api/cards/{id}`,
`/api/cards/{id}/ebay`, `/api/movers`, `/api/buys`, `/api/deals`,
`/api/collection` (+`/import`), `/api/watchlist`, `/api/alerts`,
`/api/report`, `/api/backtest` (interactive docs at `/docs`).

## Hosting it (phone-friendly)

```bash
docker compose up --build      # http://localhost:8000, data persisted in a volume
```

Set `POKEPRICE_PASSWORD` in `docker-compose.yml` to require a login (HTTP
Basic — required before exposing it beyond localhost). The image runs
`serve --auto-fetch daily`, so a deployed instance keeps itself current. Works
as-is on Fly.io/Railway/any Docker host.

## Project layout

```
src/pokeprice/
├── ingest/          # zip/dir walker + TCG-JSON and fuzzy-CSV parsers
├── fetch.py         # live API + bulk GitHub dump fetchers
├── db.py            # SQLite schema: cards, price_snapshots, prediction runs
├── features.py      # leakage-safe trailing features + forward labels
├── model.py         # GBM train/predict + momentum fallback
├── demo.py          # synthetic demo market generator
├── cli.py           # pokeprice ingest|fetch|sets|demo|train|predict|serve|stats
└── web/             # FastAPI app + vanilla-JS dashboard
```

`data/` (database, models, downloads) is gitignored. Configuration via env vars:
`POKEPRICE_DB`, `POKEPRICE_DATA_DIR`, `POKEPRICE_MIN_PRICE`, `POKEPRICE_HORIZON`,
`POKEPRICE_BIG_GAIN`, `POKEPRICE_PASSWORD`, `POKEMONTCG_API_KEY`,
`EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET`, `EBAY_MARKETPLACE`,
`PRICECHARTING_TOKEN`, `DISCORD_WEBHOOK_URL`, `SMTP_*`, `ALERT_EMAIL_*`.

Run the tests with `pytest`.

## Disclaimer

Card prices are thin, hype-driven markets; a 7-day forecast from public price
feeds is a research signal, not a trading edge. **Not financial advice** — use
it to decide what to watch, not what to buy.
