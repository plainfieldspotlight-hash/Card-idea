"""Command-line interface: pokeprice <command>."""
from __future__ import annotations

import argparse
import json
import sys

from . import config, db, demo, fetch, model
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
    if args.reset and config.db_path().exists():
        config.db_path().unlink()
    conn = db.connect()
    result = demo.seed(conn, n_cards=args.cards, days=args.days)
    print(f"Seeded demo market: {result['cards']} cards, {result['snapshots']} snapshots.")
    print("Next: pokeprice train && pokeprice predict && pokeprice serve")
    return 0


def cmd_train(args) -> int:
    conn = db.connect()
    try:
        metrics = model.train(conn, horizon_days=args.horizon)
    except model.InsufficientHistory as exc:
        print(f"Not enough history to train yet.\n{exc}", file=sys.stderr)
        return 1
    print(f"Model trained ({args.horizon}-day horizon) -> {config.model_path()}")
    for key in ("n_train", "n_valid", "valid_from", "mae", "baseline_mae",
                "direction_accuracy", "spearman_ic"):
        value = metrics.get(key)
        if isinstance(value, float):
            value = f"{value:.4f}"
        print(f"  {key:<20} {value}")
    return 0


def cmd_predict(args) -> int:
    conn = db.connect()
    result = model.predict(conn, horizon_days=args.horizon)
    print(f"Run #{result['run_id']}: scored {result['listings_scored']} listings "
          f"with {result['model_kind']} model "
          f"({result['horizon_days']}-day horizon, as of {result['as_of']}).")
    rows = conn.execute(
        """
        SELECT p.card_id, c.name, c.set_name, p.variant, p.price, p.predicted_return
        FROM predictions p JOIN cards c USING (card_id)
        WHERE p.run_id = ? AND p.price >= ?
        ORDER BY p.predicted_return DESC LIMIT ?
        """,
        (result["run_id"], max(config.MIN_PRICE, 1.0), args.top),
    ).fetchall()
    if rows:
        print("\nTop predicted gainers:")
        for r in rows:
            print(f"  {r['predicted_return']:+7.1%}  {r['name']} "
                  f"[{r['set_name']} · {r['variant']}]  @ {r['price']:.2f}")
    print("\nOpen the dashboard: pokeprice serve")
    return 0


def cmd_serve(args) -> int:
    import uvicorn

    from .web.app import create_app

    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info")
    return 0


def cmd_stats(args) -> int:
    conn = db.connect()
    print(json.dumps(db.stats(conn), indent=2, default=str))
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
                   help="bulk-download the pokemon-tcg-data dump instead of the API")
    p.add_argument("--all", action="store_true", help="crawl every card via the API")
    p.add_argument("--max-pages", type=int, default=50)
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("sets", help="list set ids available on the API")
    p.add_argument("--limit", type=int, default=40)
    p.set_defaults(func=cmd_sets)

    p = sub.add_parser("demo", help="seed a synthetic demo market to try the app end-to-end")
    p.add_argument("--cards", type=int, default=60)
    p.add_argument("--days", type=int, default=120)
    p.add_argument("--reset", action="store_true", help="delete the database first")
    p.set_defaults(func=cmd_demo)

    p = sub.add_parser("train", help="train the movement model on accumulated history")
    p.add_argument("--horizon", type=int, default=config.DEFAULT_HORIZON_DAYS,
                   help="days ahead to predict (default %(default)s)")
    p.set_defaults(func=cmd_train)

    p = sub.add_parser("predict", help="score every listing and store a prediction run")
    p.add_argument("--horizon", type=int, default=None)
    p.add_argument("--top", type=int, default=10)
    p.set_defaults(func=cmd_predict)

    p = sub.add_parser("serve", help="launch the dashboard web app")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("stats", help="print database summary")
    p.set_defaults(func=cmd_stats)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
