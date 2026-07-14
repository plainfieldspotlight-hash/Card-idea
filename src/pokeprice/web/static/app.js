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

const state = { page: 0, limit: 25, q: "", source: "", minPrice: 1, sort: "predicted", total: 0 };

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
    { label: "Listings", value: fmtCount(stats.listings), delta: "card × source × variant" },
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
  name.append(title, el("span", "sub", `${item.set_name ?? ""} · ${item.variant} · ${item.source}`));
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
  const metrics = run.metrics || {};
  const badge = run.model_kind === "gbm"
    ? `model: gradient boosting · ${run.horizon_days}d horizon · as of ${run.as_of}` +
      (metrics.spearman_ic !== null && metrics.spearman_ic !== undefined ? ` · IC ${metrics.spearman_ic.toFixed(2)}` : "")
    : `model: momentum heuristic · ${run.horizon_days}d horizon · as of ${run.as_of}`;
  $("#model-badge").textContent = badge;
  payload.gainers.forEach((g) => gain.append(moverRow(g)));
  payload.losers.forEach((l) => lose.append(moverRow(l)));
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
    const td = el("td", "empty-note",
      "No cards match. If the database is empty: `pokeprice demo` for a demo market, " +
      "`pokeprice ingest pokemon.zip` for your own data, or `pokeprice fetch` for live data.");
    td.colSpan = 7;
    tr.append(td);
    body.append(tr);
  }
  for (const item of payload.items) {
    const tr = el("tr");
    tr.tabIndex = 0;
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
    listingTd.append(el("span", "listing-chip", `${item.source} · ${item.variant}`));

    const priceTd = el("td", "num", fmtMoney(item.price, item.currency));
    const chTd = el("td", `num delta ${deltaClass(item.change7)}`, fmtPct(item.change7));
    const sparkTd = el("td", "spark-cell");
    sparkTd.append(sparkline(item.spark || []));
    const predTd = el("td", `num delta ${deltaClass(item.predicted_return)}`);
    predTd.append(el("b", null, fmtPct(item.predicted_return)));
    const probTd = el("td", "num", item.prob_up === null || item.prob_up === undefined ? "—" : (item.prob_up * 100).toFixed(0) + "%");

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
    q: state.q, source: state.source, sort: state.sort,
    min_price: String(state.minPrice),
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
    name: `${l.source} · ${l.variant}`,
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
    title.append(el("b", null, `${l.source} · ${l.variant}`));
    chip.append(title);
    chip.append(el("div", null, `latest ${fmtMoney(l.latest_price, l.currency)} on ${l.latest_date ?? "—"}`));
    if (l.prediction) {
      const p = l.prediction;
      const line = el("div", `delta ${deltaClass(p.predicted_return)}`);
      line.append(el("b", null, fmtPct(p.predicted_return)));
      line.append(document.createTextNode(
        ` over ${p.horizon_days}d · P(up) ${(p.prob_up * 100).toFixed(0)}% · ${p.model_kind}`));
      chip.append(line);
    } else {
      chip.append(el("div", "sub", "no prediction yet"));
    }
    predWrap.append(chip);
  }

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

/* ---------- wiring ---------- */
function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

$("#search").addEventListener("input", debounce((e) => {
  state.q = e.target.value.trim(); state.page = 0; loadTable();
}, 250));
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

async function init() {
  try {
    const [stats, movers] = await Promise.all([
      getJSON("/api/stats"),
      getJSON("/api/movers?limit=8&min_price=1"),
    ]);
    renderTiles(stats);
    renderMovers(movers);
    await loadTable();
  } catch (err) {
    $("#model-badge").textContent = "failed to load — is the server running?";
    console.error(err);
  }
}
init();
