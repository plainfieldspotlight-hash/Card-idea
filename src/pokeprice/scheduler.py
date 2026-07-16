"""Built-in auto-fetch scheduler: keep the database, model, and predictions
fresh without external cron.

`pokeprice serve --auto-fetch daily` starts a daemon thread that periodically
runs one cycle: fetch current prices (bulk dump by default) -> retrain when
enough labeled history exists -> re-predict. Status is written to the `meta`
table so the dashboard can show it.
"""
from __future__ import annotations

import re
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config, db, fetch, model

MIN_INTERVAL_S = 3600  # be polite to the free data sources

INTERVALS = {"daily": 86400, "weekly": 7 * 86400, "hourly": 3600}


def parse_interval(text: str) -> int:
    """'daily' | 'weekly' | 'hourly' | '12h' | '2d' -> seconds (min 1h)."""
    text = text.strip().lower()
    if text in INTERVALS:
        return INTERVALS[text]
    m = re.fullmatch(r"(\d+)\s*([hd])", text)
    if not m:
        raise ValueError(
            f"unrecognized interval {text!r} — use daily, weekly, hourly, or e.g. 12h / 2d"
        )
    seconds = int(m.group(1)) * (3600 if m.group(2) == "h" else 86400)
    return max(seconds, MIN_INTERVAL_S)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_cycle(db_path: Path | str | None = None,
              sets: list[str] | None = None, log=print) -> dict:
    """One fetch -> train -> predict pass. Returns a status dict (also persisted).

    Prices always come from the live API (the GitHub dump carries card metadata
    only, no prices); `sets` narrows the crawl, otherwise every card is pulled.
    """
    conn = db.connect(db_path)
    status: dict = {"started_at": _now(), "steps": {}}
    try:
        cards, snaps = fetch.fetch_api(conn, sets=sets, progress=log)
        status["steps"]["fetch"] = {"ok": True, "cards": cards, "snapshots": snaps}
        # money makers are the product focus: the self-updating models are
        # chase specialists unless POKEPRICE_CHASE=0. One model per horizon;
        # long horizons stay skipped until enough history accumulates.
        trained = []
        for horizon in config.HORIZONS:
            try:
                metrics = model.train(conn, horizon_days=horizon,
                                      chase=config.CHASE_DEFAULT)
                trained.append({
                    "ok": True,
                    "horizon_days": horizon,
                    "scope": metrics.get("scope"),
                    "direction_accuracy": metrics.get("direction_accuracy"),
                    "spearman_ic": metrics.get("spearman_ic"),
                })
            except model.InsufficientHistory as exc:
                trained.append({"ok": False, "horizon_days": horizon,
                                "skipped": str(exc)})
            except Exception as exc:  # one horizon must not sink the cycle
                trained.append({"ok": False, "horizon_days": horizon,
                                "error": f"{type(exc).__name__}: {exc}"})
        status["steps"]["train"] = trained
        result = model.predict(conn)
        runs = result["runs"] if "runs" in result else [result]
        status["steps"]["predict"] = {
            "ok": True,
            "runs": [{"horizon_days": r["horizon_days"],
                      "model_kind": r["model_kind"]} for r in runs],
            "errors": result.get("errors", []) if isinstance(result, dict) else [],
            "listings_scored": runs[0]["listings_scored"],
        }
        try:
            from . import pricecharting

            if pricecharting.token():
                tracked = [r["card_id"] for r in conn.execute(
                    "SELECT DISTINCT card_id FROM watchlist "
                    "UNION SELECT DISTINCT card_id FROM holdings")]
                graded_stored = 0
                for card_id in tracked:
                    try:
                        graded_stored += pricecharting.fetch_graded(
                            conn, card_id)["snapshots"]
                    except Exception:
                        continue
                    time.sleep(0.5)
                if tracked:
                    status["steps"]["graded"] = {
                        "ok": True, "cards": len(tracked),
                        "snapshots": graded_stored,
                    }
        except Exception as exc:
            status["steps"]["graded"] = {"ok": False, "error": str(exc)}
        try:
            from . import alerts

            alert_result = alerts.run(conn, log=log)
            status["steps"]["alerts"] = {
                "ok": True, "new": alert_result["new_alerts"],
                "channels": alert_result["channels"],
            }
        except Exception as exc:
            status["steps"]["alerts"] = {"ok": False, "error": str(exc)}
        status["ok"] = True
    except Exception as exc:  # keep the loop alive; surface the error in status
        status["ok"] = False
        status["error"] = f"{type(exc).__name__}: {exc}"
        log(f"auto-fetch cycle failed: {status['error']}\n{traceback.format_exc()}")
    status["finished_at"] = _now()
    db.set_meta(conn, "auto_fetch_last", status)
    conn.close()
    return status


def start(interval: str, db_path: Path | str | None = None,
          sets: list[str] | None = None, log=print) -> threading.Thread:
    """Start the background loop; first cycle runs shortly after startup."""
    seconds = parse_interval(interval)
    resolved_db = Path(db_path) if db_path else config.db_path()

    conn = db.connect(resolved_db)
    db.set_meta(conn, "auto_fetch", {
        "enabled": True, "interval": interval, "interval_seconds": seconds,
        "sets": sets, "started_at": _now(),
    })
    conn.close()

    stop_event = threading.Event()

    def loop():
        stop_event.wait(10)  # let the server come up first
        while not stop_event.is_set():
            log(f"auto-fetch: running cycle (every {interval})")
            status = run_cycle(resolved_db, sets=sets, log=log)
            nxt = datetime.now(timezone.utc) + timedelta(seconds=seconds)
            conn = db.connect(resolved_db)
            db.set_meta(conn, "auto_fetch", {
                "enabled": True, "interval": interval, "interval_seconds": seconds,
                "sets": sets, "last_ok": status.get("ok"),
                "last_finished_at": status.get("finished_at"),
                "next_run_at": nxt.isoformat(timespec="seconds"),
            })
            conn.close()
            log(f"auto-fetch: cycle {'ok' if status.get('ok') else 'FAILED'}; "
                f"next at {nxt.isoformat(timespec='seconds')}")
            stop_event.wait(seconds)

    thread = threading.Thread(target=loop, name="pokeprice-auto-fetch", daemon=True)
    thread.stop_event = stop_event  # handy for tests
    thread.start()
    return thread
