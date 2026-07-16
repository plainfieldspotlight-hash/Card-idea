"""Command-line interface: pokeprice <command>."""
from __future__ import annotations

import argparse
import json
import sys

from . import alerts, backtest, config, db, demo, fetch, model, report
from .ingest import ingest_path


def cmd_ingest(args) -> int:
    conn = db.connect()
    report = ingest_path(conn, args.path, default_date=args.as_of)
    print(report.summary())
    print(f"Database: {config.db_path()}")
    return 0


def cmd_fetch(args) -> int:
    conn = db.connect()
    if args.github:
        report = fetch.fetch_github_dump(conn)
        print(report.summary())
        print("Note: the GitHub dump is a card CATALOG (names, sets, rarities) — "
              "it carries no prices. Get prices with `pokeprice fetch --sets/--all` "
              "or historical ones with `pokeprice backfill`.")
        return 0
    if not (args.sets or args.query or args.all):
        print(
            "Choose a scope:\n"
            "  pokeprice fetch --sets sv8,sv9     # specific sets (see `pokeprice sets`)\n"
            "  pokeprice fetch --query 'name:charizard'\n"
            "  pokeprice fetch --github           # bulk dump of every card, no API key\n"
            "  pokeprice fetch --all              # crawl the whole API (slow)",
            file=sys.stderr,
        )
        return 2
    sets = [s for s in (args.sets or "").split(",") if s.strip()] or None
    cards, snaps = fetch.fetch_api(conn, sets=sets, query=args.query,
                                   max_pages=args.max_pages)
    print(f"Fetched {cards} cards, {snaps} new price snapshots.")
    print("Run this on a schedule (daily cron) to accumulate the history the model needs.")
    return 0


def cmd_sets(args) -> int:
    for s in fetch.list_sets()[: args.limit]:
        print(f"{s['id']:<12} {s.get('releaseDate', ''):<12} {s['name']} "
              f"({s.get('total', '?')} cards)")
    return 0


def cmd_demo(args) -> int:
    conn = db.connect()
    if args.remove:
        removed = 0
        for table in ("price_snapshots", "predictions", "holdings",
                      "watchlist", "alerts_log", "cards"):
            removed += conn.execute(
                f"DELETE FROM {table} WHERE card_id LIKE 'demo%'").rowcount
        conn.commit()
        print(f"Removed {removed} demo rows — only real cards remain. "
              "Retrain so the model forgets them: pokeprice train")
        return 0
    if args.reset and config.db_path().exists():
        conn.close()
        config.db_path().unlink()
        conn = db.connect()
    result = demo.seed(conn, n_cards=args.cards, days=args.days)
    print(f"Seeded demo market: {result['cards']} cards, {result['snapshots']} snapshots.")
    print("Next: pokeprice train && pokeprice predict && pokeprice serve")
    return 0


def _print_train_metrics(metrics: dict, horizon: int) -> None:
    print(f"Model trained ({horizon}-day horizon) -> {config.model_path(horizon)}")
    for key in ("n_train", "n_valid", "valid_from", "mae", "baseline_mae",
                "direction_accuracy", "spearman_ic", "stale_rows_dropped"):
        value = metrics.get(key)
        if isinstance(value, float):
            value = f"{value:.4f}"
        print(f"  {key:<20} {value}")
    if metrics.get("scope") == "chase":
        print("  scope                money-maker rarities only")
    elif metrics.get("chase_subset"):
        cs = metrics["chase_subset"]
        acc = f"{cs['direction_accuracy']:.4f}" if cs.get("direction_accuracy") is not None else "—"
        ic = f"{cs['spearman_ic']:.4f}" if cs.get("spearman_ic") is not None else "—"
        print(f"  on money-makers      direction {acc}, IC {ic} ({cs['n']} rows) "
              "— compare with `pokeprice train --chase`")


def cmd_train(args) -> int:
    conn = db.connect()
    horizons = [args.horizon] if args.horizon else list(config.HORIZONS)
    trained = 0
    for horizon in horizons:
        try:
            metrics = model.train(conn, horizon_days=horizon, tune=args.tune,
                                  min_activity=args.min_activity, chase=args.chase)
        except model.InsufficientHistory as exc:
            print(f"{horizon}-day horizon: not enough history yet — skipped.\n"
                  f"  {exc}", file=sys.stderr)
            continue
        trained += 1
        _print_train_metrics(metrics, horizon)
    if not trained:
        print("No horizon had enough history to train. `pokeprice predict` "
              "still works via the momentum fallback.", file=sys.stderr)
        return 1
    return 0


def cmd_predict(args) -> int:
    conn = db.connect()
    result = model.predict(conn, horizon_days=args.horizon)
    runs = result["runs"] if "runs" in result else [result]
    for run in runs:
        print(f"Run #{run['run_id']}: scored {run['listings_scored']} listings "
              f"with {run['model_kind']} model "
              f"({run['horizon_days']}-day horizon, as of {run['as_of']}).")
    skipped = runs[0].get("listings_skipped_thin", 0)
    if skipped:
        print(f"Skipped {skipped} listing(s) seen fewer than {config.MIN_HIST} "
              "times — no prediction without some history. "
              "`pokeprice backfill` imports months of daily prices.")
    primary = next((r for r in runs
                    if r["horizon_days"] == config.DEFAULT_HORIZON_DAYS), runs[0])
    rows = conn.execute(
        """
        SELECT p.card_id, c.name, c.set_name, p.variant, p.price, p.predicted_return
        FROM predictions p JOIN cards c USING (card_id)
        WHERE p.run_id = ? AND p.price >= ?
        ORDER BY p.predicted_return DESC LIMIT ?
        """,
        (primary["run_id"], max(config.MIN_PRICE, 1.0), args.top),
    ).fetchall()
    if rows:
        print(f"\nTop predicted gainers ({primary['horizon_days']}d):")
        for r in rows:
            print(f"  {r['predicted_return']:+7.1%}  {r['name']} "
                  f"[{r['set_name']} · {r['variant']}]  @ {r['price']:.2f}")
    print("\nOpen the dashboard: pokeprice serve")
    return 0


def cmd_serve(args) -> int:
    import uvicorn

    from .web.app import create_app

    if args.auto_fetch and args.auto_fetch != "off":
        from . import scheduler

        sets = [s for s in (args.auto_fetch_sets or "").split(",") if s.strip()] or None
        scheduler.start(args.auto_fetch, sets=sets)
        scope = f"sets {','.join(sets)}" if sets else "all cards via the live API"
        print(f"auto-fetch enabled: {scope}, every {args.auto_fetch}"
              " (fetch -> train -> predict)")
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info")
    return 0


def cmd_stats(args) -> int:
    conn = db.connect()
    print(json.dumps(db.stats(conn), indent=2, default=str))
    return 0


def cmd_backfill(args) -> int:
    from . import backfill

    conn = db.connect()
    sets = [s for s in (args.sets or "").split(",") if s.strip()] or None
    try:
        result = backfill.backfill(conn, days=args.days, every=args.every,
                                   set_ids=sets)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Backfill complete: {result['snapshots_added']} historical snapshots "
          f"across {result['days_processed']} day(s) "
          f"({result['groups_matched']} sets, {result['products_matched']} products matched).")
    print("Next: pokeprice train && pokeprice predict")
    return 0


def cmd_report(args) -> int:
    conn = db.connect()
    payload = report.prediction_report(conn)
    overall = payload["overall"]
    if not overall.get("n_resolved"):
        print("No predictions have resolved yet — they score automatically once "
              "snapshots arrive ~horizon days after each prediction run.")
        return 0
    print(f"Resolved predictions: {overall['n_resolved']} of {overall['n']}")
    for key in ("hit_rate", "mae", "baseline_mae", "spearman_ic", "interval_coverage"):
        if overall.get(key) is not None:
            print(f"  {key:<20} {overall[key]:.4f}")
    print("\nBy price tier:")
    for tier in payload["by_tier"]:
        hr = f"{tier['hit_rate']:.0%}" if tier.get("hit_rate") is not None else "  —"
        print(f"  {tier['label']:<16} resolved {tier.get('n_resolved', 0):>5}  hit rate {hr}")
    return 0


def cmd_backtest(args) -> int:
    conn = db.connect()
    try:
        result = backtest.run_backtest(
            conn, capital=args.capital, top_k=args.top_k, fee_rate=args.fees,
            min_price=args.min_price, max_price=args.max_price, rank=args.rank,
            chase=args.chase,
        )
    except model.InsufficientHistory as exc:
        print(f"Cannot backtest yet: {exc}", file=sys.stderr)
        return 1
    print(f"Backtest ({result['n_periods']} periods from {result['test_from']}, "
          f"top {args.top_k} picks, {args.fees:.1%} sell fee):")
    print(f"  strategy   {result['total_return']:+8.1%}  "
          f"(${args.capital:.0f} -> ${result['final_equity']:.2f}, after fees)")
    print(f"  signal     {result['gross_return']:+8.1%}  (same picks before fees)")
    print(f"  benchmark  {result['benchmark_return']:+8.1%}  (hold everything, no fees)")
    print(f"  win rate   {result['win_rate']:.0%}   max drawdown {result['max_drawdown']:.1%}")
    print(f"  {result['note']}")
    return 0


def cmd_alerts(args) -> int:
    conn = db.connect()
    result = alerts.run(conn)
    if not result["new_alerts"]:
        print("No new alerts.")
        return 0
    print(f"{result['new_alerts']} new alert(s), delivered via: "
          f"{', '.join(result['channels'])}")
    for a in result["alerts"]:
        print(f"  [{a['kind']}] {a['message']}")
    return 0


def cmd_import_collection(args) -> int:
    from .web.app import create_app  # reuse the same matching logic via the API
    from fastapi.testclient import TestClient

    with open(args.path, encoding="utf-8") as fh:
        text = fh.read()
    client = TestClient(create_app())
    resp = client.post("/api/collection/import", content=text,
                       headers={"Content-Type": "text/csv"})
    if resp.status_code != 200:
        print(f"Import failed: {resp.json().get('detail')}", file=sys.stderr)
        return 1
    payload = resp.json()
    print(f"Imported {payload['imported']} holding(s); columns used: "
          f"{payload['columns_used']}")
    if payload["unmatched"]:
        print(f"Unmatched ({len(payload['unmatched'])}): "
              f"{', '.join(payload['unmatched'][:10])}")
    return 0


def cmd_graded(args) -> int:
    from . import pricecharting

    conn = db.connect()
    targets: list[str] = []
    if args.card_id:
        targets.append(args.card_id)
    if args.watchlist:
        targets += [r["card_id"] for r in conn.execute(
            "SELECT DISTINCT card_id FROM watchlist")]
    if args.collection:
        targets += [r["card_id"] for r in conn.execute(
            "SELECT DISTINCT card_id FROM holdings")]
    if args.set:
        targets += [r["card_id"] for r in conn.execute(
            "SELECT card_id FROM cards WHERE set_id = ?", (args.set,))]
    targets = list(dict.fromkeys(targets))
    if not targets:
        print("Nothing to fetch — pass a card id, or --watchlist / --collection "
              "/ --set <id>.", file=sys.stderr)
        return 2
    matched = missed = stored = 0
    for i, card_id in enumerate(targets):
        try:
            result = pricecharting.fetch_graded(conn, card_id, query=args.query)
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        if result["matched"]:
            matched += 1
            stored += result["snapshots"]
        else:
            missed += 1
        if (i + 1) % 10 == 0 or i == len(targets) - 1:
            print(f"  {i + 1}/{len(targets)} cards "
                  f"({matched} matched, {stored} graded prices stored)")
        import time
        time.sleep(0.5)  # be polite to PriceCharting
    if missed:
        print(f"{missed} card(s) had no PriceCharting match.")
    print("Graded copies now appear under the Condition filter "
          "(Graded -> company -> grade) and get their own predictions.")
    return 0


def cmd_event(args) -> int:
    conn = db.connect()
    conn.execute(
        "INSERT INTO events (event_date, note, match) VALUES (?, ?, ?)",
        (args.date, args.note, args.match),
    )
    conn.commit()
    print(f"Recorded event {args.date}: {args.note!r} (matches cards containing "
          f"{args.match!r}). It feeds the model's event_recency feature on the "
          "next train.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="pokeprice",
        description="Track Pokemon card prices and predict short-term movements.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("ingest", help="load a zip/folder/CSV/JSON of card data (e.g. pokemon.zip)")
    p.add_argument("path")
    p.add_argument("--as-of", default=None,
                   help="snapshot date (YYYY-MM-DD) for files without their own dates")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("fetch", help="pull current cards+prices from live sources")
    p.add_argument("--sets", default=None, help="comma-separated set ids, e.g. sv8,sv9")
    p.add_argument("--query", default=None, help="raw API query, e.g. 'name:charizard'")
    p.add_argument("--github", action="store_true",
                   help="bulk-download the card CATALOG from pokemon-tcg-data "
                        "(metadata only — the dump has no prices)")
    p.add_argument("--all", action="store_true", help="crawl every card via the API")
    p.add_argument("--max-pages", type=int, default=50)
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser(
        "backfill",
        help="import months of REAL daily TCGplayer price history from tcgcsv.com archives")
    p.add_argument("--days", type=int, default=120, help="how far back (default %(default)s)")
    p.add_argument("--every", type=int, default=2,
                   help="day step between snapshots (1 = daily; default %(default)s)")
    p.add_argument("--sets", default=None,
                   help="restrict to comma-separated set ids (default: every set in your catalog)")
    p.set_defaults(func=cmd_backfill)

    p = sub.add_parser("sets", help="list set ids available on the API")
    p.add_argument("--limit", type=int, default=40)
    p.set_defaults(func=cmd_sets)

    p = sub.add_parser("demo", help="seed a synthetic demo market to try the app end-to-end")
    p.add_argument("--cards", type=int, default=60)
    p.add_argument("--days", type=int, default=120)
    p.add_argument("--reset", action="store_true", help="delete the database first")
    p.add_argument("--remove", action="store_true",
                   help="delete all demo cards/snapshots from the database, keeping real data")
    p.set_defaults(func=cmd_demo)

    p = sub.add_parser("train", help="train the movement model on accumulated history")
    p.add_argument("--horizon", type=int, default=None,
                   help="train a single horizon in days (default: all of "
                        f"{','.join(str(h) for h in config.HORIZONS)})")
    p.add_argument("--tune", action="store_true",
                   help="search a small hyperparameter grid on an inner time split first")
    p.add_argument("--min-activity", type=float, default=None,
                   help="drop listings whose price moved in fewer than this fraction of "
                        "their snapshots (default %s; 0 disables)" % config.MIN_ACTIVITY)
    p.add_argument("--chase", action="store_true",
                   help="train and predict on money-maker rarities only "
                        "(Full Art / IR / SIR / Ultra / Secret / Hyper / Holo)")
    p.set_defaults(func=cmd_train)

    p = sub.add_parser("predict", help="score every listing and store a prediction run")
    p.add_argument("--horizon", type=int, default=None,
                   help="predict a single horizon in days (default: all of "
                        f"{','.join(str(h) for h in config.HORIZONS)})")
    p.add_argument("--top", type=int, default=10)
    p.set_defaults(func=cmd_predict)

    p = sub.add_parser("serve", help="launch the dashboard web app")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--auto-fetch", default=None, metavar="INTERVAL",
                   help="keep data fresh automatically: daily, weekly, or e.g. 12h "
                        "(runs fetch -> train -> predict on that cadence)")
    p.add_argument("--auto-fetch-sets", default=None,
                   help="limit auto-fetch to comma-separated set ids (default: full dump)")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("stats", help="print database summary")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("report", help="score past predictions against realized prices")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("backtest", help="simulate trading the model's picks on held-out history")
    p.add_argument("--capital", type=float, default=500.0)
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--fees", type=float, default=backtest.DEFAULT_FEE_RATE,
                   help="sell-side fee rate (default %(default)s ≈ eBay)")
    p.add_argument("--min-price", type=float, default=max(1.0, config.MIN_PRICE))
    p.add_argument("--max-price", type=float, default=None)
    p.add_argument("--rank", choices=["worst_case", "expected"], default="worst_case")
    p.add_argument("--chase", action="store_true",
                   help="trade money-maker rarities only")
    p.set_defaults(func=cmd_backtest)

    p = sub.add_parser("alerts", help="evaluate alert rules and deliver new alerts")
    p.set_defaults(func=cmd_alerts)

    p = sub.add_parser("import-collection", help="bulk-import holdings from a CSV export")
    p.add_argument("path")
    p.set_defaults(func=cmd_import_collection)

    p = sub.add_parser("graded",
                       help="fetch graded (PSA/BGS/CGC/SGC) prices via PriceCharting")
    p.add_argument("card_id", nargs="?", default=None)
    p.add_argument("--watchlist", action="store_true",
                   help="fetch graded prices for every watched card")
    p.add_argument("--collection", action="store_true",
                   help="fetch graded prices for every card you own")
    p.add_argument("--set", default=None, help="fetch for every card in a set id")
    p.add_argument("--query", default=None,
                   help="override the search query (single-card mode only)")
    p.set_defaults(func=cmd_graded)

    p = sub.add_parser("event", help="record a hype event (reprint news, tournament result)")
    p.add_argument("--date", required=True, help="YYYY-MM-DD")
    p.add_argument("--note", required=True)
    p.add_argument("--match", required=True,
                   help="substring matched against card names, e.g. 'charizard'")
    p.set_defaults(func=cmd_event)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
