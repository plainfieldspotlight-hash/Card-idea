/* pokeprice dashboard.
 * Charts are hand-rolled SVG following the house dataviz rules: thin 2px lines,
 * hairline solid grid, crosshair + one tooltip listing every series, legend for
 * >= 2 series, endpoint labels only where they fit, text in ink tokens (never
 * the series color), and an always-available table view. All data strings go
 * through textContent — never innerHTML.
 */
"use strict";

const $ = (sel) => document.querySelector(sel);

const SERIES_VARS = ["--series-1", "--series-2", "--series-3", "--series-4", "--series-5", "--series-6"];
const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

const VARIANT_LABELS = {
  psa10: "PSA 10", psa9: "PSA 9", bgs10: "BGS 10", bgs95: "BGS 9.5",
  cgc10: "CGC 10", sgc10: "SGC 10", grade95: "Grade 9.5", grade9: "Grade 9",
  grade8: "Grade 8", grade7: "Grade 7", ungraded: "raw",
  reverseHolofoil: "reverse holo", holofoil: "holo",
  "1stEditionHolofoil": "1st ed. holo", "1stEditionNormal": "1st edition",
};
const fmtVariant = (v) => VARIANT_LABELS[v] ?? v;

const state = { page: 0, limit: 25, q: "", source: "", set: "", rarity: "",
                bucket: "", grading: "", company: "", grade: "",
                minPrice: 1, sort: "predicted", total: 0,
                // money makers are the default focus; "0" is the explicit opt-out
                chase: localStorage.getItem("pokeprice-chase") !== "0" };

const chaseParam = () => (state.chase ? "&chase=1" : "");

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

const CUR_SYMBOL = { USD: "$", EUR: "€" };
function fmtMoney(v, currency) {
  if (v === null || v === undefined) return "—";
  const sym = CUR_SYMBOL[currency] || "";
  const val = v >= 1000 ? v.toLocaleString(undefined, { maximumFractionDigits: 0 })
    : v.toFixed(2);
  return sym + val;
}
function fmtPct(v, digits = 1) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return (v >= 0 ? "+" : "") + (v * 100).toFixed(digits) + "%";
}
function fmtCount(v) { return (v ?? 0).toLocaleString(); }
function fmtDate(iso) {
  const d = new Date(iso + "T00:00:00Z");
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", timeZone: "UTC" });
}
function deltaClass(v, threshold = 0.0025) {
  if (v === null || v === undefined) return "";
  return v > threshold ? "up" : v < -threshold ? "down" : "";
}

async function getJSON(url) {
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`${url} -> ${resp.status}`);
  return resp.json();
}

/* ---------- stat tiles ---------- */
function renderTiles(stats) {
  const wrap = $("#tiles");
  wrap.replaceChildren();
  const run = stats.latest_run;
  const metrics = run && run.metrics ? run.metrics : {};
  const tiles = [
    { label: "Cards tracked", value: fmtCount(stats.cards) },
    { label: "Price snapshots", value: fmtCount(stats.snapshots), delta: stats.snapshot_dates ? `${fmtCount(stats.snapshot_dates)} distinct dates` : null },
    { label: "Listings", value: fmtCount(stats.listings),
      delta: "one card can trade in several markets/finishes" },
    { label: "Latest prices", value: stats.last_date ? fmtDate(stats.last_date) : "—", delta: stats.first_date ? `history since ${fmtDate(stats.first_date)}` : null },
  ];
  if (run) {
    const acc = metrics.direction_accuracy;
    tiles.push({
      label: "Direction accuracy",
      value: acc !== null && acc !== undefined ? (acc * 100).toFixed(0) + "%" : "n/a",
      delta: run.model_kind === "gbm" ? `validation · IC ${metrics.spearman_ic?.toFixed(2) ?? "—"}` : "momentum heuristic",
    });
  }
  if (stats.auto_fetch && stats.auto_fetch.enabled) {
    const last = stats.auto_fetch_last;
    tiles.push({
      label: "Auto-fetch",
      value: stats.auto_fetch.interval,
      delta: last
        ? `last run ${last.ok ? "ok" : "FAILED"} · ${fmtDate((last.finished_at || "").slice(0, 10))}`
        : "first run pending",
    });
  }
  for (const t of tiles) {
    const tile = el("div", "card tile");
    tile.append(el("div", "label", t.label), el("div", "value", t.value));
    if (t.delta) tile.append(el("div", "delta", t.delta));
    wrap.append(tile);
  }
}

/* ---------- movers ---------- */
function thumbEl(item) {
  if (item.image_small) {
    const img = el("img", "thumb");
    img.src = item.image_small;
    img.alt = "";
    img.loading = "lazy";
    return img;
  }
  return el("span", "thumb ph", (item.name || "?").slice(0, 1));
}

function moverRow(item) {
  const li = el("li");
  li.append(thumbEl(item));
  const name = el("div", "m-name");
  const title = el("div");
  title.append(el("b", null, item.name));
  name.append(title, el("span", "sub", `${item.set_name ?? ""} · ${fmtVariant(item.variant)} · ${item.source}`));
  const price = el("span", "m-price", fmtMoney(item.price, item.source === "cardmarket" ? "EUR" : "USD"));
  const val = el("span", `m-val delta ${deltaClass(item.predicted_return)}`, fmtPct(item.predicted_return));
  li.append(name, price, val);
  li.addEventListener("click", () => openDetail(item.card_id));
  return li;
}

function renderMovers(payload) {
  const gain = $("#gainers"), lose = $("#losers");
  gain.replaceChildren(); lose.replaceChildren();
  if (!payload.run) {
    const note = "No predictions yet — run `pokeprice predict`.";
    gain.append(el("li", "empty-note", note));
    lose.append(el("li", "empty-note", note));
    $("#model-badge").textContent = "no prediction run yet";
    return;
  }
  const run = payload.run;
  const horizon = `next ${run.horizon_days}d`;
  $("#movers-horizon").textContent = horizon;
  $("#movers-horizon2").textContent = horizon;
  renderExpandable(gain, payload.gainers, moverRow);
  renderExpandable(lose, payload.losers, moverRow);
  const metrics = run.metrics || {};
  const scopeNote = metrics.scope === "chase" ? " · 💰 money-makers model" : "";
  const badge = run.model_kind === "gbm"
    ? `model: gradient boosting${scopeNote} · ${run.horizon_days}d horizon · as of ${run.as_of}` +
      (metrics.spearman_ic !== null && metrics.spearman_ic !== undefined ? ` · IC ${metrics.spearman_ic.toFixed(2)}` : "")
    : `model: momentum heuristic · ${run.horizon_days}d horizon · as of ${run.as_of}`;
  $("#model-badge").textContent = badge;
}

/* ---------- high-confidence buys ---------- */
function buyRow(item) {
  const li = el("li");
  li.append(thumbEl(item));
  const name = el("div", "m-name");
  const title = el("div");
  title.append(el("b", null, item.name));
  name.append(title, el("span", "sub",
    `${item.set_name ?? "—"} · ${fmtMoney(item.price, item.source === "cardmarket" ? "EUR" : "USD")} · ${fmtVariant(item.variant)}`));
  const stack = el("div", "m-stack");
  const val = el("span", `m-val delta ${deltaClass(item.predicted_return)}`, fmtPct(item.predicted_return));
  if (item.predicted_low !== null && item.predicted_low !== undefined) {
    val.title = `range ${fmtPct(item.predicted_low)} … ${fmtPct(item.predicted_high)}`;
  }
  stack.append(val);
  if (item.predicted_low !== null && item.predicted_low !== undefined) {
    stack.append(el("span", "sub", `worst ${fmtPct(item.predicted_low)}`));
  }
  const subline = el("span", "sub", `P(up) ${(item.prob_up * 100).toFixed(0)}% · `);
  if (item.ebay_url) {
    const a = el("a", "ebay-link", "eBay ↗");
    a.href = item.ebay_url;
    a.target = "_blank";
    a.rel = "noopener";
    a.addEventListener("click", (e) => e.stopPropagation());
    subline.append(a);
  }
  stack.append(subline);
  li.append(name, stack);
  li.addEventListener("click", () => openDetail(item.card_id));
  return li;
}

function renderBuys(payload) {
  const grid = $("#buys-grid");
  grid.replaceChildren();
  const crit = payload.criteria;
  $("#buys-criteria").textContent = payload.run
    ? `P(up) ≥ ${(crit.min_prob * 100).toFixed(0)}% and predicted ≥ ${fmtPct(crit.min_return)} over ${payload.run.horizon_days}d · price tiers at face value (USD/EUR)`
    : "";
  for (const tier of payload.tiers) {
    const box = el("div", "buy-tier");
    box.append(el("h3", null, tier.label));
    if (!tier.items.length) {
      box.append(el("div", "empty-note",
        payload.run ? "No cards clear the bar right now." : "Run `pokeprice predict` first."));
    } else {
      const list = el("ol", "movers");
      renderExpandable(list, tier.items, buyRow, 5);
      box.append(list);
    }
    grid.append(box);
  }
}

/* ---------- expandable lists (top 25, preview a handful) ---------- */
function renderExpandable(listEl, items, rowFn, preview = 8) {
  listEl.replaceChildren();
  items.slice(0, preview).forEach((item) => listEl.append(rowFn(item)));
  if (items.length > preview) {
    const li = el("li", "expand-row");
    const btn = el("button", "expand-btn", `Show all ${items.length} ▾`);
    btn.type = "button";
    btn.addEventListener("click", () => {
      li.remove();
      items.slice(preview).forEach((item) => listEl.append(rowFn(item)));
    });
    li.append(btn);
    listEl.append(li);
  }
}

/* ---------- deal radar ---------- */
function renderDeals(payload) {
  const list = $("#deals-list");
  list.replaceChildren();
  const note = $("#deals-note");
  if (payload.mode === "live") {
    note.textContent = "model-liked cards with live eBay listings below your tracked market price";
    if (!payload.deals.length) {
      list.append(el("li", "empty-note", "No below-market listings for current picks — check back after the next fetch."));
    }
  } else {
    note.textContent = "model picks + eBay search links · set EBAY_CLIENT_ID/SECRET for live below-market matching";
    if (!payload.deals.length) {
      list.append(el("li", "empty-note", "No qualifying picks yet — run `pokeprice predict`."));
    }
  }
  renderExpandable(list, payload.deals, dealRow);
}

function dealRow(deal) {
    const li = el("li");
    li.append(thumbEl(deal));
    const name = el("div", "m-name");
    const title = el("div");
    title.append(el("b", null, deal.name));
    name.append(title, el("span", "sub",
      `${deal.set_name ?? ""} · ${fmtVariant(deal.variant)} · tracked ${fmtMoney(deal.price, deal.currency)}`));
    const stack = el("div", "m-stack");
    stack.append(el("span", `m-val delta ${deltaClass(deal.predicted_return)}`,
      fmtPct(deal.predicted_return)));
    const subline = el("span", "sub");
    if (deal.best_listing) {
      const a = el("a", "ebay-link",
        `${fmtMoney(deal.best_listing.price, deal.best_listing.currency)} on eBay (${fmtPct(deal.best_listing.vs_market)} vs market) ↗`);
      a.href = deal.best_listing.url;
      a.target = "_blank"; a.rel = "noopener";
      a.addEventListener("click", (e) => e.stopPropagation());
      subline.append(a);
    } else {
      const a = el("a", "ebay-link", "search eBay ↗");
      a.href = deal.ebay_url; a.target = "_blank"; a.rel = "noopener";
      a.addEventListener("click", (e) => e.stopPropagation());
      subline.append(a);
    }
    stack.append(subline);
    li.append(name, stack);
    li.addEventListener("click", () => openDetail(deal.card_id));
    return li;
}

/* ---------- watchlist & alerts ---------- */
async function toggleWatch(item, watched) {
  if (watched) {
    await fetch(`/api/watchlist?card_id=${encodeURIComponent(item.card_id)}` +
      `&source=${encodeURIComponent(item.source)}&variant=${encodeURIComponent(item.variant)}`,
      { method: "DELETE" });
  } else {
    await fetch("/api/watchlist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ card_id: item.card_id, source: item.source, variant: item.variant }),
    });
  }
  loadWatchAndAlerts();
}

async function loadWatchAndAlerts() {
  const [watch, alertsPayload] = await Promise.all([
    getJSON("/api/watchlist"), getJSON("/api/alerts"),
  ]);
  const list = $("#watchlist");
  list.replaceChildren();
  if (!watch.items.length) {
    list.append(el("li", "empty-note", "Not watching anything yet — click the ☆ next to any card."));
  }
  for (const item of watch.items) {
    const li = el("li");
    const star = el("button", "star on", "★");
    star.title = "Stop watching";
    star.addEventListener("click", (e) => { e.stopPropagation(); toggleWatch(item, true); });
    li.append(star, thumbEl(item));
    const name = el("div", "m-name");
    const title = el("div");
    title.append(el("b", null, item.name));
    name.append(title, el("span", "sub", `${item.set_name ?? ""} · ${fmtVariant(item.variant)} · ${item.source}`));
    const stack = el("div", "m-stack");
    stack.append(el("span", `m-val delta ${deltaClass(item.predicted_return)}`, fmtPct(item.predicted_return)));
    stack.append(el("span", "sub", fmtMoney(item.price, item.currency)));
    li.append(name, stack);
    li.addEventListener("click", () => openDetail(item.card_id));
    list.append(li);
  }

  const settings = alertsPayload.settings;
  const form = $("#alert-settings");
  for (const key of ["min_prob", "min_return", "move_threshold", "collection_drop"]) {
    if (form.elements[key]) form.elements[key].value = settings[key];
  }
  const log = $("#alert-log");
  log.replaceChildren();
  $("#alerts-note").textContent = alertsPayload.alerts.length
    ? `${alertsPayload.alerts.length} recent` : "none fired yet";
  for (const a of alertsPayload.alerts.slice(0, 12)) {
    const li = el("li");
    li.append(el("span", `alert-kind kind-${a.kind}`, a.kind));
    li.append(el("span", null, ` ${a.message} `));
    li.append(el("span", "sub", (a.created_at || "").slice(0, 10)));
    log.append(li);
  }
}

$("#alert-settings").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const body = {};
  for (const key of ["min_prob", "min_return", "move_threshold", "collection_drop"]) {
    body[key] = Number(form.elements[key].value);
  }
  await fetch("/api/alerts/settings", {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  loadWatchAndAlerts();
});
$("#alerts-run").addEventListener("click", async () => {
  await fetch("/api/alerts/run", { method: "POST" });
  loadWatchAndAlerts();
});

/* ---------- model report card & backtest ---------- */
function pctOrDash(v, digits = 0) {
  return v === null || v === undefined ? "—" : (v * 100).toFixed(digits) + "%";
}

async function loadReport() {
  const payload = await getJSON("/api/report");
  const tiles = $("#report-tiles");
  tiles.replaceChildren();
  const o = payload.overall;
  const tileData = [
    { label: "Predictions scored", value: `${o.n_resolved ?? 0} / ${o.n ?? 0}`,
      delta: "resolve ~horizon days after each run" },
    { label: "Live hit rate", value: pctOrDash(o.hit_rate), delta: "direction correct" },
    { label: "Rank IC", value: o.spearman_ic === null || o.spearman_ic === undefined ? "—" : o.spearman_ic.toFixed(2),
      delta: "predicted vs realized ordering" },
    { label: "Range coverage", value: pctOrDash(o.interval_coverage),
      delta: "realized inside predicted range (target ≈80%)" },
  ];
  for (const t of tileData) {
    const tile = el("div", "card tile");
    tile.append(el("div", "label", t.label), el("div", "value", t.value));
    if (t.delta) tile.append(el("div", "delta", t.delta));
    tiles.append(tile);
  }
  const tbody = $("#report-tiers tbody");
  tbody.replaceChildren();
  for (const tier of payload.by_tier) {
    const tr = el("tr");
    tr.append(el("td", null, tier.label));
    tr.append(el("td", "num", String(tier.n_resolved ?? 0)));
    tr.append(el("td", "num", pctOrDash(tier.hit_rate)));
    tr.append(el("td", "num", tier.spearman_ic === null || tier.spearman_ic === undefined ? "—" : tier.spearman_ic.toFixed(2)));
    tbody.append(tr);
  }
  renderBacktest(payload.backtest);
}

function renderBacktest(result) {
  const statsEl = $("#backtest-stats");
  const chart = $("#backtest-chart");
  const legend = $("#backtest-legend");
  legend.replaceChildren();
  if (!result) {
    chart.replaceChildren();
    statsEl.textContent = "Not run yet — click “Run backtest” to simulate trading the model's picks on held-out history.";
    return;
  }
  const series = [
    { name: "strategy (after fees)", color: cssVar("--series-1"), currency: "USD", points: result.equity },
    { name: "hold everything (no fees)", color: cssVar("--series-5"), currency: "USD", points: result.benchmark_equity },
  ];
  for (const s of series) {
    const key = el("span", "key");
    const swatch = el("span", "swatch");
    swatch.style.borderTopColor = s.color;
    key.append(swatch, el("span", null, s.name));
    legend.append(key);
  }
  lineChart(chart, series, { indexed: false });
  statsEl.textContent =
    `${result.n_periods} periods from ${result.test_from} · strategy ${fmtPct(result.total_return)} after fees ` +
    `(${fmtPct(result.gross_return)} before fees — the signal itself) vs benchmark ${fmtPct(result.benchmark_return)} · ` +
    `win rate ${pctOrDash(result.win_rate)} · max drawdown ${pctOrDash(result.max_drawdown, 1)} · ` +
    `top ${result.params.top_k} picks, ${(result.params.fee_rate * 100).toFixed(1)}% sell fee per flip. ${result.note}`;
}

$("#backtest-run").addEventListener("click", async () => {
  const btn = $("#backtest-run");
  btn.disabled = true;
  btn.textContent = "Running…";
  try {
    const resp = await fetch(`/api/backtest?chase=${state.chase ? 1 : 0}`, { method: "POST" });
    const payload = await resp.json();
    if (!resp.ok) {
      $("#backtest-stats").textContent = payload.detail || "Backtest failed.";
    } else {
      renderBacktest(payload);
    }
  } finally {
    btn.disabled = false;
    btn.textContent = "Run backtest";
  }
});

/* ---------- collection import ---------- */
$("#collection-import").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const text = await file.text();
  const resp = await fetch("/api/collection/import", {
    method: "POST", headers: { "Content-Type": "text/csv" }, body: text,
  });
  const payload = await resp.json();
  const note = $("#import-result");
  note.classList.remove("hidden");
  note.textContent = resp.ok
    ? `Imported ${payload.imported} holding(s).` +
      (payload.unmatched.length ? ` Unmatched: ${payload.unmatched.slice(0, 6).join(", ")}` : "")
    : `Import failed: ${payload.detail}`;
  e.target.value = "";
  loadCollection();
});

/* ---------- collection ---------- */
async function loadCollection() {
  const payload = await getJSON("/api/collection");
  const tiles = $("#collection-tiles");
  tiles.replaceChildren();
  const t = payload.totals;
  const tileData = [
    { label: "Portfolio value", value: t.value ? fmtMoney(t.value) : "—" },
    { label: "Cost basis", value: t.cost ? fmtMoney(t.cost) : "—" },
    { label: "Unrealized gain", value: fmtMoney(t.gain), cls: deltaClass(t.gain) },
    { label: "Predicted 7d move", value: fmtMoney(t.predicted_delta), cls: deltaClass(t.predicted_delta) },
    { label: "Holdings", value: String(t.count) },
  ];
  for (const td of tileData) {
    const tile = el("div", "card tile");
    tile.append(el("div", "label", td.label));
    tile.append(el("div", `value delta ${td.cls || ""}`, td.value));
    tiles.append(tile);
  }
  const body = $("#collection-body");
  body.replaceChildren();
  if (!payload.holdings.length) {
    const tr = el("tr");
    const td = el("td", "empty-note",
      "Nothing here yet — click any card, then “Add to collection” on one of its listings.");
    td.colSpan = 9;
    tr.append(td);
    body.append(tr);
    return;
  }
  for (const h of payload.holdings) {
    const tr = el("tr");
    const cardTd = el("td");
    const cell = el("div", "cell-card");
    cell.append(thumbEl(h));
    const n = el("div", "n");
    const nameLine = el("div");
    nameLine.append(el("b", null, h.name));
    n.append(nameLine, el("span", "sub", h.set_name ?? "—"));
    cell.append(n);
    cardTd.append(cell);
    const listingTd = el("td");
    listingTd.append(el("span", "listing-chip", `${h.source} · ${fmtVariant(h.variant)}`));
    const gainPct = h.cost_basis && h.price ? h.price / h.cost_basis - 1 : null;
    const gainTd = el("td", `num delta ${deltaClass(h.gain)}`);
    gainTd.textContent = h.gain === null ? "—"
      : `${fmtMoney(h.gain, h.currency)}${gainPct !== null ? ` (${fmtPct(gainPct)})` : ""}`;
    const removeTd = el("td", "num");
    const btn = el("button", "btn-x", "✕");
    btn.title = "Remove from collection";
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      await fetch(`/api/collection/${h.holding_id}`, { method: "DELETE" });
      loadCollection();
    });
    removeTd.append(btn);
    tr.append(
      cardTd, listingTd,
      el("td", "num", String(h.quantity)),
      el("td", "num", h.cost_basis === null ? "—" : fmtMoney(h.cost_basis, h.currency)),
      el("td", "num", fmtMoney(h.price, h.currency)),
      el("td", "num", h.value === null ? "—" : fmtMoney(h.value, h.currency)),
      gainTd,
      el("td", `num delta ${deltaClass(h.predicted_return)}`, fmtPct(h.predicted_return)),
      removeTd,
    );
    tr.addEventListener("click", () => openDetail(h.card_id));
    body.append(tr);
  }
}

/* ---------- eBay listings block (detail panel) ---------- */
async function loadEbay(cardId, variant) {
  const wrap = $("#detail-ebay");
  wrap.replaceChildren();
  try {
    const payload = await getJSON(
      `/api/cards/${encodeURIComponent(cardId)}/ebay?variant=${encodeURIComponent(variant)}`);
    if (payload.mode !== "live" || !payload.items.length) return; // chips already link out
    const head = el("div", "sub");
    head.append(document.createTextNode("Live eBay listings (fixed price): "));
    wrap.append(head);
    const list = el("div", "ebay-items");
    for (const it of payload.items) {
      const row = el("a", "ebay-item");
      row.href = it.url;
      row.target = "_blank";
      row.rel = "noopener";
      row.append(el("b", null, it.price !== null ? fmtMoney(it.price, it.currency) : "—"));
      if (it.vs_market !== null) {
        row.append(el("span", `delta ${deltaClass(-it.vs_market)}`,
          ` ${fmtPct(it.vs_market)} vs market`));
      }
      row.append(el("span", "sub", ` ${it.condition ?? ""} — ${it.title ?? ""}`));
      list.append(row);
    }
    wrap.append(list);
  } catch {
    /* eBay block is best-effort; the search links in the chips remain */
  }
}

/* ---------- sparkline (micro-chart: de-emphasis hue, accent end dot) ---------- */
function sparkline(points, width = 120, height = 26) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("width", width);
  svg.setAttribute("height", height);
  svg.setAttribute("aria-hidden", "true");
  const vals = points.map((p) => p[1]);
  if (vals.length < 2) return svg;
  const min = Math.min(...vals), max = Math.max(...vals);
  const span = max - min || 1;
  const px = (i) => 2 + (i / (vals.length - 1)) * (width - 8);
  const py = (v) => height - 3 - ((v - min) / span) * (height - 6);
  const d = vals.map((v, i) => `${i ? "L" : "M"}${px(i).toFixed(1)},${py(v).toFixed(1)}`).join("");
  const path = document.createElementNS(svg.namespaceURI, "path");
  path.setAttribute("d", d);
  path.setAttribute("fill", "none");
  path.setAttribute("stroke", cssVar("--spark"));
  path.setAttribute("stroke-width", "1.5");
  path.setAttribute("stroke-linejoin", "round");
  path.setAttribute("stroke-linecap", "round");
  const dot = document.createElementNS(svg.namespaceURI, "circle");
  dot.setAttribute("cx", px(vals.length - 1));
  dot.setAttribute("cy", py(vals[vals.length - 1]));
  dot.setAttribute("r", "2.5");
  dot.setAttribute("fill", cssVar("--accent"));
  svg.append(path, dot);
  return svg;
}

/* ---------- cards table ---------- */
function renderTable(payload) {
  state.total = payload.total;
  const body = $("#cards-body");
  body.replaceChildren();
  if (!payload.items.length) {
    const tr = el("tr");
    const searching = state.q || state.set || state.rarity || state.source || state.bucket;
    const message = state.grading === "graded"
      ? "No graded prices stored yet. Graded data comes from PriceCharting (set PRICECHARTING_TOKEN, see README), then run: python -m pokeprice graded --watchlist --collection"
      : searching && state.minPrice > 0
      ? `No matches at your price floor — cheap cards are hidden by the "≥ ${state.minPrice.toFixed(2)}" filter. Try switching it to "Any price".`
      : searching
        ? "No cards match that search."
        : "No cards yet — run `pokeprice demo` for a demo market, `pokeprice ingest pokemon.zip` for your own data, or `pokeprice fetch` for live data.";
    const td = el("td", "empty-note", message);
    td.colSpan = 8;
    tr.append(td);
    body.append(tr);
  }
  for (const item of payload.items) {
    const tr = el("tr");
    tr.tabIndex = 0;
    const starTd = el("td", "star-cell");
    const watched = Boolean(item.watched);
    const star = el("button", `star${watched ? " on" : ""}`, watched ? "★" : "☆");
    star.title = watched ? "Stop watching" : "Add to watchlist";
    star.addEventListener("click", async (e) => {
      e.stopPropagation();
      await toggleWatch(item, watched);
      loadTable();
    });
    starTd.append(star);
    tr.append(starTd);
    const cardTd = el("td");
    const cell = el("div", "cell-card");
    cell.append(thumbEl(item));
    const n = el("div", "n");
    const nameLine = el("div");
    nameLine.append(el("b", null, item.name));
    n.append(nameLine, el("span", "sub", `${item.set_name ?? "—"}${item.rarity ? " · " + item.rarity : ""}`));
    cell.append(n);
    cardTd.append(cell);

    const listingTd = el("td");
    listingTd.append(el("span", "listing-chip", `${item.source} · ${fmtVariant(item.variant)}`));

    const priceTd = el("td", "num", fmtMoney(item.price, item.currency));
    const chTd = el("td", `num delta ${deltaClass(item.change7)}`, fmtPct(item.change7));
    const sparkTd = el("td", "spark-cell");
    sparkTd.append(sparkline(item.spark || []));
    const predTd = el("td", `num delta ${deltaClass(item.predicted_return)}`);
    predTd.append(el("b", null, fmtPct(item.predicted_return)));
    if (item.predicted_low !== null && item.predicted_low !== undefined) {
      predTd.title = `range ${fmtPct(item.predicted_low)} … ${fmtPct(item.predicted_high)}`;
      predTd.append(el("span", "sub", ` ${fmtPct(item.predicted_low)}…${fmtPct(item.predicted_high)}`));
    }
    const probTd = el("td", "num", item.prob_up === null || item.prob_up === undefined ? "—" : (item.prob_up * 100).toFixed(0) + "%");
    probTd.title = "Probability the price is higher in 7 days";

    tr.append(cardTd, listingTd, priceTd, chTd, sparkTd, predTd, probTd);
    const open = () => openDetail(item.card_id);
    tr.addEventListener("click", open);
    tr.addEventListener("keydown", (e) => { if (e.key === "Enter") open(); });
    body.append(tr);
  }
  const from = state.page * state.limit + 1;
  const to = Math.min(state.total, from + payload.items.length - 1);
  $("#table-count").textContent = state.total ? `${from}–${to} of ${fmtCount(state.total)} listings` : "0 listings";
  $("#prev").disabled = state.page === 0;
  $("#next").disabled = to >= state.total;
}

async function loadTable() {
  const params = new URLSearchParams({
    q: state.q, source: state.source, set_id: state.set, rarity: state.rarity,
    chase: state.chase ? "1" : "0", bucket: state.bucket,
    grading: state.grading, company: state.company, grade: state.grade,
    sort: state.sort, min_price: String(state.minPrice),
    limit: String(state.limit), offset: String(state.page * state.limit),
  });
  const panel = $("#cards-table");
  panel.style.opacity = "0.55"; // hold previous render while refetching
  try {
    renderTable(await getJSON(`/api/cards?${params}`));
  } finally {
    panel.style.opacity = "";
  }
}

/* ---------- detail line chart ---------- */
const tooltip = $("#tooltip");

function lineChart(container, series, opts) {
  // series: [{name, color, currency, points: [[iso, value], ...]}]
  container.replaceChildren();
  const W = 860, H = 300, mL = 52, mR = 96, mT = 12, mB = 26;
  const svgNS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(svgNS, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("role", "img");

  const indexed = opts.indexed;
  const toVal = (s, v) => (indexed ? (v / s.base) * 100 : v);
  series.forEach((s) => { s.base = s.points.length ? s.points[0][1] : 1; });

  const allDates = [...new Set(series.flatMap((s) => s.points.map((p) => p[0])))].sort();
  const t0 = Date.parse(allDates[0]), t1 = Date.parse(allDates[allDates.length - 1]) || t0 + 1;
  const vals = series.flatMap((s) => s.points.map((p) => toVal(s, p[1])));
  let vMin = Math.min(...vals), vMax = Math.max(...vals);
  if (vMin === vMax) { vMin -= 1; vMax += 1; }
  const pad = (vMax - vMin) * 0.08;
  vMin -= pad; vMax += pad;

  const x = (iso) => mL + ((Date.parse(iso) - t0) / (t1 - t0 || 1)) * (W - mL - mR);
  const y = (v) => mT + (1 - (v - vMin) / (vMax - vMin)) * (H - mT - mB);

  // grid: clean-step horizontal hairlines
  const rawStep = (vMax - vMin) / 4;
  const mag = Math.pow(10, Math.floor(Math.log10(rawStep)));
  const step = [1, 2, 5, 10].map((m) => m * mag).find((s) => s >= rawStep) || mag;
  for (let v = Math.ceil(vMin / step) * step; v <= vMax; v += step) {
    const line = document.createElementNS(svgNS, "line");
    line.setAttribute("x1", mL); line.setAttribute("x2", W - mR);
    line.setAttribute("y1", y(v)); line.setAttribute("y2", y(v));
    line.setAttribute("stroke", cssVar("--grid"));
    line.setAttribute("stroke-width", "1");
    svg.append(line);
    const tick = document.createElementNS(svgNS, "text");
    tick.setAttribute("x", mL - 8); tick.setAttribute("y", y(v) + 3.5);
    tick.setAttribute("text-anchor", "end");
    tick.setAttribute("fill", cssVar("--muted"));
    tick.setAttribute("font-size", "11");
    tick.textContent = indexed ? v.toFixed(0) : v >= 100 ? v.toFixed(0) : v.toFixed(2);
    svg.append(tick);
  }
  // baseline + x ticks
  const base = document.createElementNS(svgNS, "line");
  base.setAttribute("x1", mL); base.setAttribute("x2", W - mR);
  base.setAttribute("y1", H - mB); base.setAttribute("y2", H - mB);
  base.setAttribute("stroke", cssVar("--baseline"));
  base.setAttribute("stroke-width", "1");
  svg.append(base);
  const nTicks = Math.min(5, allDates.length);
  for (let i = 0; i < nTicks; i++) {
    const iso = allDates[Math.round((i * (allDates.length - 1)) / Math.max(1, nTicks - 1))];
    const tick = document.createElementNS(svgNS, "text");
    tick.setAttribute("x", x(iso)); tick.setAttribute("y", H - mB + 16);
    tick.setAttribute("text-anchor", "middle");
    tick.setAttribute("fill", cssVar("--muted"));
    tick.setAttribute("font-size", "11");
    tick.textContent = fmtDate(iso);
    svg.append(tick);
  }

  // series paths (+10% area wash when there's a single series)
  const endLabelYs = [];
  series.forEach((s) => {
    if (!s.points.length) return;
    const d = s.points.map((p, i) => `${i ? "L" : "M"}${x(p[0]).toFixed(1)},${y(toVal(s, p[1])).toFixed(1)}`).join("");
    if (series.length === 1) {
      const area = document.createElementNS(svgNS, "path");
      const first = s.points[0], last = s.points[s.points.length - 1];
      area.setAttribute("d", `${d}L${x(last[0]).toFixed(1)},${H - mB}L${x(first[0]).toFixed(1)},${H - mB}Z`);
      area.setAttribute("fill", s.color);
      area.setAttribute("opacity", "0.1");
      svg.append(area);
    }
    const path = document.createElementNS(svgNS, "path");
    path.setAttribute("d", d);
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", s.color);
    path.setAttribute("stroke-width", "2");
    path.setAttribute("stroke-linejoin", "round");
    path.setAttribute("stroke-linecap", "round");
    svg.append(path);

    const [lastDate, lastVal] = s.points[s.points.length - 1];
    const dot = document.createElementNS(svgNS, "circle");
    dot.setAttribute("cx", x(lastDate)); dot.setAttribute("cy", y(toVal(s, lastVal)));
    dot.setAttribute("r", "4");
    dot.setAttribute("fill", s.color);
    dot.setAttribute("stroke", cssVar("--surface-1"));
    dot.setAttribute("stroke-width", "2");
    svg.append(dot);

    // endpoint value label — only where it fits without colliding (ink token, not series color)
    const ly = y(toVal(s, lastVal));
    if (series.length <= 4 && !endLabelYs.some((used) => Math.abs(used - ly) < 13)) {
      endLabelYs.push(ly);
      const label = document.createElementNS(svgNS, "text");
      label.setAttribute("x", x(lastDate) + 9);
      label.setAttribute("y", ly + 3.5);
      label.setAttribute("fill", cssVar("--text-primary"));
      label.setAttribute("font-size", "11");
      label.setAttribute("font-weight", "600");
      label.textContent = fmtMoney(lastVal, s.currency);
      svg.append(label);
    }
  });

  // crosshair + unified tooltip
  const cross = document.createElementNS(svgNS, "line");
  cross.setAttribute("y1", mT); cross.setAttribute("y2", H - mB);
  cross.setAttribute("stroke", cssVar("--baseline"));
  cross.setAttribute("stroke-width", "1");
  cross.setAttribute("visibility", "hidden");
  svg.append(cross);
  const hoverDots = series.map((s) => {
    const c = document.createElementNS(svgNS, "circle");
    c.setAttribute("r", "4.5");
    c.setAttribute("fill", s.color);
    c.setAttribute("stroke", cssVar("--surface-1"));
    c.setAttribute("stroke-width", "2");
    c.setAttribute("visibility", "hidden");
    svg.append(c);
    return c;
  });
  const byDate = series.map((s) => new Map(s.points.map((p) => [p[0], p[1]])));

  function showAt(dateIdx, clientX, clientY) {
    const iso = allDates[dateIdx];
    const cx = x(iso);
    cross.setAttribute("x1", cx); cross.setAttribute("x2", cx);
    cross.setAttribute("visibility", "visible");
    tooltip.replaceChildren(el("div", "t-date", iso));
    series.forEach((s, i) => {
      const v = byDate[i].get(iso);
      if (v === undefined) { hoverDots[i].setAttribute("visibility", "hidden"); return; }
      hoverDots[i].setAttribute("cx", cx);
      hoverDots[i].setAttribute("cy", y(toVal(s, v)));
      hoverDots[i].setAttribute("visibility", "visible");
      const row = el("div", "t-row");
      const swatch = el("span", "swatch");
      swatch.style.borderTopColor = s.color;
      row.append(swatch, el("b", null, fmtMoney(v, s.currency)), el("span", "t-name", s.name));
      tooltip.append(row);
    });
    tooltip.classList.remove("hidden");
    const tw = tooltip.offsetWidth;
    const left = clientX + 14 + tw > window.innerWidth ? clientX - tw - 14 : clientX + 14;
    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${Math.max(8, clientY - 20)}px`;
  }
  function hide() {
    cross.setAttribute("visibility", "hidden");
    hoverDots.forEach((d) => d.setAttribute("visibility", "hidden"));
    tooltip.classList.add("hidden");
  }

  let kbIdx = allDates.length - 1;
  const nearestIdx = (px) => {
    let best = 0, bestDist = Infinity;
    allDates.forEach((iso, i) => {
      const d = Math.abs(x(iso) - px);
      if (d < bestDist) { bestDist = d; best = i; }
    });
    return best;
  };
  svg.addEventListener("pointermove", (e) => {
    const rect = svg.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * W;
    kbIdx = nearestIdx(px);
    showAt(kbIdx, e.clientX, e.clientY);
  });
  svg.addEventListener("pointerleave", hide);
  container.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    e.preventDefault();
    kbIdx = Math.max(0, Math.min(allDates.length - 1, kbIdx + (e.key === "ArrowRight" ? 1 : -1)));
    const rect = svg.getBoundingClientRect();
    const cx = rect.left + (x(allDates[kbIdx]) / W) * rect.width;
    showAt(kbIdx, cx, rect.top + rect.height / 3);
  });
  container.addEventListener("blur", hide);

  container.append(svg);
}

/* ---------- detail panel ---------- */
async function openDetail(cardId) {
  const data = await getJSON(`/api/cards/${encodeURIComponent(cardId)}`);
  const panel = $("#detail-panel");
  const head = $("#detail-head");
  head.replaceChildren();
  const card = data.card;
  if (card.image_large || card.image_small) {
    const img = el("img", "big");
    img.src = card.image_large || card.image_small;
    img.alt = card.name;
    head.append(img);
  }
  const meta = el("div");
  meta.append(el("h2", null, card.name));
  meta.append(el("div", "sub",
    [card.set_name, card.rarity, card.number ? `#${card.number}` : null, card.artist]
      .filter(Boolean).join(" · ")));
  head.append(meta);

  const listings = data.listings
    .filter((l) => l.history.length)
    .slice(0, SERIES_VARS.length);
  const currencies = new Set(listings.map((l) => l.currency || "?"));
  const indexed = currencies.size > 1;
  const series = listings.map((l, i) => ({
    name: `${l.source} · ${fmtVariant(l.variant)}`,
    color: cssVar(SERIES_VARS[i]),
    currency: l.currency,
    points: l.history,
  }));

  const legend = $("#detail-legend");
  legend.replaceChildren();
  if (series.length >= 2) {
    for (const s of series) {
      const key = el("span", "key");
      const swatch = el("span", "swatch");
      swatch.style.borderTopColor = s.color;
      key.append(swatch, el("span", null, s.name));
      legend.append(key);
    }
  }
  $("#detail-axis-note").textContent = indexed
    ? "Sources use different currencies, so lines are indexed (first point = 100); the tooltip shows real prices."
    : series.length ? `Prices in ${[...currencies][0]}.` : "No price history for this card yet.";
  if (series.length) lineChart($("#detail-chart"), series, { indexed });
  else $("#detail-chart").replaceChildren();

  const predWrap = $("#detail-predictions");
  predWrap.replaceChildren();
  for (const l of data.listings) {
    const chip = el("div", "pred-chip");
    const title = el("div");
    title.append(el("b", null, `${l.source} · ${fmtVariant(l.variant)}`));
    chip.append(title);
    chip.append(el("div", null, `latest ${fmtMoney(l.latest_price, l.currency)} on ${l.latest_date ?? "—"}`));
    if (l.prediction) {
      const p = l.prediction;
      const line = el("div", `delta ${deltaClass(p.predicted_return)}`);
      line.append(el("b", null, fmtPct(p.predicted_return)));
      line.append(document.createTextNode(
        ` over ${p.horizon_days}d · P(up) ${(p.prob_up * 100).toFixed(0)}% · ${p.model_kind}`));
      chip.append(line);
      if (p.predicted_low !== null && p.predicted_low !== undefined) {
        chip.append(el("div", "sub",
          `range ${fmtPct(p.predicted_low)} … ${fmtPct(p.predicted_high)}` +
          (p.prob_gain !== null && p.prob_gain !== undefined
            ? ` · P(+10%) ${(p.prob_gain * 100).toFixed(0)}%` : "")));
      }
      if (l.latest_price) {
        const maxBid = el("div", "sub maxbid");
        maxBid.dataset.price = l.latest_price;
        maxBid.dataset.low = p.predicted_low ?? p.predicted_return * 0.5;
        maxBid.dataset.currency = l.currency || "USD";
        chip.append(maxBid);
      }
    } else {
      chip.append(el("div", "sub", "no prediction yet"));
    }

    const actions = el("div", "chip-actions");
    if (l.ebay_url) {
      const a = el("a", "ebay-link", "Buy on eBay ↗");
      a.href = l.ebay_url;
      a.target = "_blank";
      a.rel = "noopener";
      actions.append(a);
    }
    const form = el("form", "add-form");
    const qty = el("input");
    qty.type = "number"; qty.min = "1"; qty.step = "1"; qty.value = "1";
    qty.title = "Quantity";
    const paid = el("input");
    paid.type = "number"; paid.min = "0"; paid.step = "0.01";
    paid.placeholder = "paid ea.";
    paid.title = "What you paid per card (optional)";
    const btn = el("button", null, "＋ Collection");
    btn.type = "submit";
    form.append(qty, paid, btn);
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      btn.disabled = true;
      try {
        const resp = await fetch("/api/collection", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            card_id: card.card_id, source: l.source, variant: l.variant,
            quantity: Number(qty.value) || 1,
            cost_basis: paid.value === "" ? null : Number(paid.value),
          }),
        });
        btn.textContent = resp.ok ? "Added ✓" : "Failed";
        if (resp.ok) loadCollection();
      } finally {
        setTimeout(() => { btn.textContent = "＋ Collection"; btn.disabled = false; }, 1500);
      }
    });
    actions.append(form);
    chip.append(actions);
    predWrap.append(chip);
  }
  updateMaxBids();
  loadEbay(cardId, listings[0]?.variant ?? "normal");

  // table view twin — every charted value reachable without hover
  const details = el("details");
  details.append(el("summary", "sub", "Table view of price history"));
  const scroller = el("div", "table-scroll");
  scroller.style.maxHeight = "220px";
  scroller.style.overflowY = "auto";
  const table = el("table");
  const thead = el("thead");
  const hrow = el("tr");
  ["Date", ...series.map((s) => s.name)].forEach((h) => hrow.append(el("th", null, h)));
  thead.append(hrow);
  const tbody = el("tbody");
  const allDates = [...new Set(series.flatMap((s) => s.points.map((p) => p[0])))].sort().reverse();
  const maps = series.map((s) => new Map(s.points));
  for (const iso of allDates) {
    const tr = el("tr");
    tr.append(el("td", null, iso));
    series.forEach((s, i) => {
      const v = maps[i].get(iso);
      tr.append(el("td", "num", v === undefined ? "—" : fmtMoney(v, s.currency)));
    });
    tbody.append(tr);
  }
  table.append(thead, tbody);
  scroller.append(table);
  details.append(scroller);
  predWrap.append(details);

  panel.classList.remove("hidden");
  panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
  $("#detail-chart").focus({ preventScroll: true });
}

/* ---------- max-bid calculator (pure client-side) ---------- */
function updateMaxBids() {
  const fee = Number($("#mb-fee").value) / 100 || 0;
  const ship = Number($("#mb-ship").value) || 0;
  document.querySelectorAll(".maxbid").forEach((node) => {
    const price = Number(node.dataset.price);
    const low = Number(node.dataset.low);
    // conservative expected sale = tracked price at the worst-case prediction,
    // minus seller fees and shipping; paying more than this risks a loss
    const maxBid = price * (1 + low) * (1 - fee) - ship;
    node.textContent = maxBid > 0
      ? `max bid ≈ ${fmtMoney(maxBid, node.dataset.currency)} to stay profitable in the worst case`
      : "no profitable bid at the worst-case prediction";
  });
}
$("#mb-fee").addEventListener("input", updateMaxBids);
$("#mb-ship").addEventListener("input", updateMaxBids);

/* ---------- wiring ---------- */
function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

async function loadFilterOptions() {
  const payload = await getJSON("/api/sets");
  const setSel = $("#set-filter");
  for (const s of payload.sets) {
    const opt = el("option", null,
      `${s.set_name}${s.release_date ? ` (${s.release_date.slice(0, 4)})` : ""}`);
    opt.value = s.set_id;
    setSel.append(opt);
  }
  const raritySel = $("#rarity-filter");
  for (const r of payload.rarities) {
    const opt = el("option", null, r);
    opt.value = r;
    raritySel.append(opt);
  }
}

const refreshSuggestions = debounce(async (text) => {
  if (text.length < 2) return;
  try {
    const payload = await getJSON(`/api/suggest?q=${encodeURIComponent(text)}`);
    const list = $("#card-suggest");
    list.replaceChildren();
    for (const name of payload.suggestions) {
      const opt = el("option");
      opt.value = name;
      list.append(opt);
    }
  } catch { /* suggestions are best-effort */ }
}, 200);

$("#search").addEventListener("input", debounce((e) => {
  state.q = e.target.value.trim(); state.page = 0; loadTable();
  refreshSuggestions(e.target.value.trim());
}, 250));
document.querySelectorAll(".bucket-chips button[data-bucket]").forEach((chip) => {
  chip.addEventListener("click", () => {
    state.bucket = chip.dataset.bucket;
    state.page = 0;
    document.querySelectorAll(".bucket-chips button[data-bucket]").forEach((b) =>
      b.classList.toggle("on", b === chip));
    loadTable();
  });
});

document.querySelectorAll(".condition-chips button[data-grading]").forEach((chip) => {
  chip.addEventListener("click", () => {
    state.grading = chip.dataset.grading;
    state.page = 0;
    document.querySelectorAll(".condition-chips button[data-grading]").forEach((b) =>
      b.classList.toggle("on", b === chip));
    const graded = state.grading === "graded";
    $("#grade-company").classList.toggle("hidden", !graded);
    $("#grade-level").classList.toggle("hidden", !graded);
    if (!graded) {
      state.company = ""; state.grade = "";
      $("#grade-company").value = ""; $("#grade-level").value = "";
    }
    loadTable();
  });
});
$("#grade-company").addEventListener("change", (e) => {
  state.company = e.target.value; state.page = 0; loadTable();
});
$("#grade-level").addEventListener("change", (e) => {
  state.grade = e.target.value; state.page = 0; loadTable();
});

$("#set-filter").addEventListener("change", (e) => {
  state.set = e.target.value; state.page = 0; loadTable();
});
$("#rarity-filter").addEventListener("change", (e) => {
  state.rarity = e.target.value; state.page = 0; loadTable();
});
$("#source-filter").addEventListener("change", (e) => {
  state.source = e.target.value; state.page = 0; loadTable();
});
$("#min-price").addEventListener("change", (e) => {
  state.minPrice = Number(e.target.value); state.page = 0; loadTable();
});
$("#sort").addEventListener("change", (e) => {
  state.sort = e.target.value; state.page = 0; loadTable();
});
$("#prev").addEventListener("click", () => { state.page = Math.max(0, state.page - 1); loadTable(); });
$("#next").addEventListener("click", () => { state.page += 1; loadTable(); });
$("#detail-close").addEventListener("click", () => $("#detail-panel").classList.add("hidden"));
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") $("#detail-panel").classList.add("hidden");
});

async function loadScopedSections() {
  const [movers, buys, deals] = await Promise.all([
    getJSON(`/api/movers?limit=25&min_price=1${chaseParam()}`),
    getJSON(`/api/buys?rank=worst_case&per_tier=25${chaseParam()}`),
    getJSON(`/api/deals?limit=25${chaseParam()}`),
  ]);
  renderMovers(movers);
  renderBuys(buys);
  renderDeals(deals);
}

const chaseButton = $("#chase-toggle");
function syncChaseButton() {
  chaseButton.classList.toggle("on", state.chase);
  chaseButton.setAttribute("aria-pressed", state.chase ? "true" : "false");
}
chaseButton.addEventListener("click", () => {
  state.chase = !state.chase;
  localStorage.setItem("pokeprice-chase", state.chase ? "1" : "0");
  state.page = 0;
  syncChaseButton();
  loadScopedSections();
  loadTable();
});

async function init() {
  try {
    syncChaseButton();
    renderTiles(await getJSON("/api/stats"));
    await loadScopedSections();
    await Promise.all([loadTable(), loadCollection(), loadWatchAndAlerts(),
                       loadReport(), loadFilterOptions()]);
  } catch (err) {
    $("#model-badge").textContent = "failed to load — is the server running?";
    console.error(err);
  }
}
init();
