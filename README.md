# CardPulse

A static web app inspired by Market Movers and Card Ladder that pairs **card
value trends** with **player performance trends** so you can spot when the two
disagree.

## Features

- **Movers / All / Retired / Watchlist** tabs across MLB, NBA, NFL, NHL.
- **Card value trend** sparklines and a detail chart over a 7d / 30d / 90d / 1y
  window.
- **Player performance** indicator — recent stat average vs season average:
  - `Playing better`, `Playing worse`, or `On pace`.
- **Combined signal** for each player:
  - `Aligned up` — playing better, value rising.
  - `Aligned down` — playing worse, value falling.
  - `Possibly undervalued` — playing better, value lagging.
  - `Possibly overvalued` — playing worse, value rising.
- **Retired players** show value trend only and are tagged `Legacy`.
- **Off-season** sports show **No change** for performance (e.g. NFL in April).
- Sort by biggest gainers, biggest losers, or **performance/value divergence**.
- Search, sport filter, time window filter, watchlist persisted to
  localStorage.

## Run

It's a static site — no build step. Open `index.html` directly, or:

```sh
python3 -m http.server 8000
```

Then visit `http://localhost:8000`.

## Files

- `index.html` — markup and tab/filter shell.
- `styles.css` — dark theme, grid layout, modal.
- `data.js` — mock player + price + performance dataset.
- `app.js` — filtering, sorting, sparkline rendering, signal logic.

Data is mock. Plug in a real source by replacing `PLAYERS` in `data.js`.
