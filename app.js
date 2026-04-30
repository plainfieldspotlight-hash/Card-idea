(() => {
  const { PLAYERS, SEASON_MONTHS, TODAY } = window.CARDPULSE_DATA;

  const state = {
    tab: "movers",
    sport: "all",
    windowDays: 30,
    sort: "value-change-desc",
    recFilter: "all",
    query: "",
    watchlist: new Set(JSON.parse(localStorage.getItem("cp_watch") || "[]")),
    collection: JSON.parse(localStorage.getItem("cp_collection") || "[]"),
  };

  function saveCollection() {
    localStorage.setItem("cp_collection", JSON.stringify(state.collection));
  }

  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => Array.from(root.querySelectorAll(s));

  // ---------- season helpers ----------
  function isInSeason(sport) {
    const month = TODAY.getMonth() + 1;
    return (SEASON_MONTHS[sport] || []).includes(month);
  }

  // ---------- analysis ----------
  // Slice price series to the last N days; returns {start, end, change, pct, series}.
  function sliceWindow(series, days) {
    if (!series.length) return null;
    const cutoff = new Date(TODAY);
    cutoff.setDate(cutoff.getDate() - days);
    const filtered = series.filter(p => new Date(p.date) >= cutoff);
    if (filtered.length < 2) {
      // fall back to full range
      const start = series[0].value;
      const end = series[series.length - 1].value;
      return { start, end, change: end - start, pct: ((end - start) / start) * 100, series };
    }
    const start = filtered[0].value;
    const end = filtered[filtered.length - 1].value;
    return {
      start,
      end,
      change: end - start,
      pct: ((end - start) / start) * 100,
      series: filtered,
    };
  }

  // Build the perf delta vs season average. Returns null if no perf data.
  function performanceVerdict(player) {
    if (player.status === "retired") {
      return { label: "Retired — legacy", verdict: "legacy", delta: null };
    }
    if (!isInSeason(player.sport) || player.perf.length === 0) {
      return { label: "Off-season — no change", verdict: "offseason", delta: 0 };
    }
    const recentN = Math.min(5, player.perf.length);
    const recent = player.perf.slice(-recentN);
    const avg = recent.reduce((s, p) => s + p.statValue, 0) / recent.length;
    const delta = avg - player.seasonAvg;
    const pct = (delta / player.seasonAvg) * 100;
    let verdict, label;
    if (pct > 4) {
      verdict = "better";
      label = `Playing better (+${pct.toFixed(1)}% vs season avg)`;
    } else if (pct < -4) {
      verdict = "worse";
      label = `Playing worse (${pct.toFixed(1)}% vs season avg)`;
    } else {
      verdict = "same";
      label = `On pace (${pct >= 0 ? "+" : ""}${pct.toFixed(1)}% vs season avg)`;
    }
    return { label, verdict, delta, pct, recentAvg: avg };
  }

  // Combine performance verdict with value change → an actionable signal.
  function combinedSignal(player, valueWindow) {
    const perf = performanceVerdict(player);
    const valueDir =
      valueWindow.pct > 1 ? "up" : valueWindow.pct < -1 ? "down" : "flat";

    if (perf.verdict === "legacy") {
      return { pill: "legacy", text: `Legacy — value ${valueDir}` };
    }
    if (perf.verdict === "offseason") {
      return { pill: "offseason", text: `Off-season — value ${valueDir}` };
    }

    // Active in-season — compare perf to value direction.
    if (perf.verdict === "better" && valueDir === "up")
      return { pill: "aligned-up", text: "Playing better, value rising — aligned" };
    if (perf.verdict === "worse" && valueDir === "down")
      return { pill: "aligned-down", text: "Playing worse, value falling — aligned" };
    if (perf.verdict === "better" && valueDir !== "up")
      return { pill: "undervalued", text: "Playing better, value lagging — possibly undervalued" };
    if (perf.verdict === "worse" && valueDir === "up")
      return { pill: "overvalued", text: "Playing worse, value rising — possibly overvalued" };
    return { pill: "legacy", text: `On pace — value ${valueDir}` };
  }

  // ---------- recommendation ----------
  // Five-tier recommendation derived from performance vs value, scored -2..+2.
  // Active players: weighted edge of perf% over value%.
  // Off-season:     value-trend-only score (muted) — usually Hold.
  // Retired:        value-trend-only score.
  function recommendation(player, valueWindow) {
    const perf = performanceVerdict(player);
    const valuePct = valueWindow.pct;

    let score, basis;
    if (perf.verdict === "legacy") {
      // Retired: pure market signal.
      score = clamp(valuePct / 8, -2, 2);
      basis = `Retired — value ${pctStr(valuePct)} over ${state.windowDays}d`;
    } else if (perf.verdict === "offseason") {
      // Off-season: performance is fixed at "no change" — only value direction matters,
      // and we mute it because no on-field news is moving things.
      score = clamp(valuePct / 14, -2, 2);
      basis = `Off-season — value ${pctStr(valuePct)} (perf: no change)`;
    } else {
      // Active in-season: edge = how much perf is outrunning (or trailing) the market.
      const edge = (perf.pct || 0) - valuePct;
      score = clamp(edge / 6, -2, 2);
      basis = `Perf ${pctStr(perf.pct || 0)} vs value ${pctStr(valuePct)} → edge ${pctStr(edge)}`;
    }

    let level, label, pill;
    if (score >=  1.25) { level =  2; label = "Strong Buy";  pill = "rec-strong-buy"; }
    else if (score >=  0.45) { level =  1; label = "Buy";         pill = "rec-buy"; }
    else if (score <= -1.25) { level = -2; label = "Strong Sell"; pill = "rec-strong-sell"; }
    else if (score <= -0.45) { level = -1; label = "Sell";        pill = "rec-sell"; }
    else                     { level =  0; label = "Hold — No Change"; pill = "rec-hold"; }

    return { level, label, pill, basis, score };
  }

  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

  // ---------- sparkline ----------
  function sparkline(series, { width = 280, height = 50, color = "#5b8cff" } = {}) {
    if (!series || series.length < 2) {
      return `<svg class="spark" viewBox="0 0 ${width} ${height}"></svg>`;
    }
    const xs = series.map(p => new Date(p.date).getTime());
    const ys = series.map(p => p.value);
    const minX = Math.min(...xs), maxX = Math.max(...xs);
    const minY = Math.min(...ys), maxY = Math.max(...ys);
    const sx = x => ((x - minX) / Math.max(1, maxX - minX)) * (width - 4) + 2;
    const sy = y => height - 2 - ((y - minY) / Math.max(0.0001, maxY - minY)) * (height - 6);
    const d = series
      .map((p, i) => `${i === 0 ? "M" : "L"} ${sx(xs[i]).toFixed(1)} ${sy(p.value).toFixed(1)}`)
      .join(" ");
    const areaD = d + ` L ${sx(maxX).toFixed(1)} ${height} L ${sx(minX).toFixed(1)} ${height} Z`;
    const id = "g" + Math.random().toString(36).slice(2, 8);
    return `
      <svg class="spark" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">
        <defs>
          <linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="${color}" stop-opacity="0.35"/>
            <stop offset="100%" stop-color="${color}" stop-opacity="0"/>
          </linearGradient>
        </defs>
        <path d="${areaD}" fill="url(#${id})" />
        <path d="${d}" fill="none" stroke="${color}" stroke-width="1.6"/>
      </svg>`;
  }

  // Larger detail chart with Y-axis ticks.
  function bigChart(series, color) {
    const width = 640, height = 220, padL = 50, padB = 24, padT = 10, padR = 10;
    if (!series || series.length < 2) {
      return `<svg class="chart-svg" viewBox="0 0 ${width} ${height}"><text x="20" y="30" fill="#8a93a6">No data.</text></svg>`;
    }
    const xs = series.map(p => new Date(p.date).getTime());
    const ys = series.map(p => p.value);
    const minX = Math.min(...xs), maxX = Math.max(...xs);
    const minY = Math.min(...ys), maxY = Math.max(...ys);
    const sx = x => padL + ((x - minX) / Math.max(1, maxX - minX)) * (width - padL - padR);
    const sy = y => height - padB - ((y - minY) / Math.max(0.0001, maxY - minY)) * (height - padT - padB);
    const d = series.map((p, i) => `${i === 0 ? "M" : "L"} ${sx(xs[i]).toFixed(1)} ${sy(p.value).toFixed(1)}`).join(" ");

    const ticks = 4;
    let ticksMarkup = "";
    for (let i = 0; i <= ticks; i++) {
      const yVal = minY + ((maxY - minY) * i) / ticks;
      const yPx = sy(yVal);
      ticksMarkup += `
        <line x1="${padL}" y1="${yPx}" x2="${width - padR}" y2="${yPx}" stroke="#232a3d" stroke-dasharray="2 3"/>
        <text x="${padL - 6}" y="${yPx + 3}" fill="#8a93a6" font-size="10" text-anchor="end">${formatMoney(yVal)}</text>`;
    }
    const startLabel = series[0].date;
    const endLabel = series[series.length - 1].date;
    return `
      <svg class="chart-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">
        ${ticksMarkup}
        <path d="${d}" fill="none" stroke="${color}" stroke-width="2"/>
        <text x="${padL}"        y="${height - 6}" fill="#8a93a6" font-size="10">${startLabel}</text>
        <text x="${width - padR}" y="${height - 6}" fill="#8a93a6" font-size="10" text-anchor="end">${endLabel}</text>
      </svg>`;
  }

  // ---------- formatting ----------
  function formatMoney(n) {
    if (n >= 1000) return "$" + Math.round(n).toLocaleString();
    return "$" + n.toFixed(2);
  }
  function pctStr(n) {
    const sign = n > 0 ? "+" : "";
    return `${sign}${n.toFixed(1)}%`;
  }
  function dirClass(pct) {
    if (pct > 1) return "up";
    if (pct < -1) return "down";
    return "flat";
  }
  function dirArrow(pct) {
    if (pct > 1) return "▲";
    if (pct < -1) return "▼";
    return "→";
  }

  // ---------- filtering / sorting ----------
  function visiblePlayers() {
    let list = PLAYERS.slice();

    if (state.tab === "retired")   list = list.filter(p => p.status === "retired");
    if (state.tab === "watchlist") list = list.filter(p => state.watchlist.has(p.id));

    if (state.sport !== "all") list = list.filter(p => p.sport === state.sport);

    if (state.query.trim()) {
      const q = state.query.toLowerCase();
      list = list.filter(
        p =>
          p.name.toLowerCase().includes(q) ||
          p.team.toLowerCase().includes(q) ||
          p.cards.some(c => c.name.toLowerCase().includes(q))
      );
    }

    const enriched = list.map(p => {
      const w = sliceWindow(p.prices, state.windowDays);
      const perf = performanceVerdict(p);
      return { player: p, window: w, perf };
    });

    // Attach recommendation to each enriched item.
    enriched.forEach(e => { e.rec = recommendation(e.player, e.window); });

    if (state.recFilter !== "all") {
      const want = parseInt(state.recFilter, 10);
      enriched.splice(0, enriched.length, ...enriched.filter(e => e.rec.level === want));
    }

    switch (state.sort) {
      case "value-change-asc":
        enriched.sort((a, b) => a.window.pct - b.window.pct);
        break;
      case "divergence":
        enriched.sort((a, b) => {
          const da = divergence(a), db = divergence(b);
          return db - da;
        });
        break;
      case "value-desc":
        enriched.sort((a, b) => b.window.end - a.window.end);
        break;
      case "rec-desc":
        enriched.sort((a, b) => b.rec.score - a.rec.score);
        break;
      case "rec-asc":
        enriched.sort((a, b) => a.rec.score - b.rec.score);
        break;
      case "sport-group":
        enriched.sort((a, b) => {
          const s = a.player.sport.localeCompare(b.player.sport);
          return s !== 0 ? s : b.rec.score - a.rec.score;
        });
        break;
      case "value-change-desc":
      default:
        enriched.sort((a, b) => b.window.pct - a.window.pct);
    }
    return enriched;
  }

  // Higher = more interesting mismatch between perf and value.
  function divergence({ perf, window }) {
    if (perf.verdict === "legacy" || perf.verdict === "offseason") return -1;
    return Math.abs((perf.pct || 0) - window.pct);
  }

  // ---------- rendering ----------
  function renderGrid() {
    const grid = $("#player-grid");
    const collectionView = $("#collection-view");

    if (state.tab === "collection") {
      grid.classList.add("hidden");
      collectionView.classList.remove("hidden");
      renderCollection();
      return;
    }
    if (state.tab === "picks") {
      grid.classList.remove("hidden");
      collectionView.classList.add("hidden");
      renderTopPicks();
      return;
    }
    grid.classList.remove("hidden");
    collectionView.classList.add("hidden");
    grid.style.gridTemplateColumns = ""; // restore the default from CSS

    const items = visiblePlayers();
    if (!items.length) {
      grid.innerHTML = `<div class="empty-state">No players match these filters.</div>`;
      return;
    }

    // When sorted by sport, render sport headers between groups.
    if (state.sort === "sport-group") {
      let lastSport = null;
      const html = items.map(item => {
        let prefix = "";
        if (item.player.sport !== lastSport) {
          lastSport = item.player.sport;
          prefix = `<div class="sport-section-head">${lastSport}</div>`;
        }
        return prefix + renderCard(item);
      }).join("");
      grid.innerHTML = html;
    } else {
      grid.innerHTML = items.map(renderCard).join("");
    }

    $$(".card").forEach(el => {
      el.addEventListener("click", () => openDetail(el.dataset.id));
    });
  }

  // ---------- top picks ----------
  function renderTopPicks() {
    const grid = $("#player-grid");
    grid.style.gridTemplateColumns = "1fr"; // override so picks sections stack full-width

    // Build enriched list (without rec filter — Top Picks shows everything per sport).
    const all = PLAYERS
      .filter(p => state.sport === "all" || p.sport === state.sport)
      .map(p => {
        const w = sliceWindow(p.prices, state.windowDays);
        const perf = performanceVerdict(p);
        return { player: p, window: w, perf, rec: recommendation(p, w) };
      });

    const sports = ["MLB", "NBA", "NFL", "NHL"];
    const sections = sports
      .map(s => {
        const inSport = all.filter(e => e.player.sport === s);
        if (!inSport.length) return "";

        const buys  = inSport.slice().sort((a, b) => b.rec.score - a.rec.score).slice(0, 3);
        const sells = inSport.slice().sort((a, b) => a.rec.score - b.rec.score).slice(0, 3);

        const renderPickRow = (e, kind) => {
          const top = e.player.cards
            .slice()
            .sort((a, b) => b.value - a.value)[0];
          return `<div class="pick-row" data-id="${e.player.id}">
            <div>
              <div class="pick-name">${e.player.name}</div>
              <div class="pick-meta">${top.year} ${top.name} (${top.grade}) — ${formatMoney(top.value)}</div>
            </div>
            <span class="rec-badge ${e.rec.pill}">${recIcon(e.rec.level)} ${e.rec.label}</span>
            <span class="${dirClass(e.window.pct)}" style="font-size:12px">${pctStr(e.window.pct)}</span>
          </div>`;
        };

        return `<div class="picks-section">
          <h3>${s} <span class="player-meta">· ${inSport.length} players</span></h3>
          <div class="picks-grid">
            <div>
              <div class="picks-col-head"><span class="rec-badge rec-strong-buy">▲▲</span> Top Buys</div>
              ${buys.map(e => renderPickRow(e, "buy")).join("")}
            </div>
            <div>
              <div class="picks-col-head"><span class="rec-badge rec-strong-sell">▼▼</span> Top Sells</div>
              ${sells.map(e => renderPickRow(e, "sell")).join("")}
            </div>
          </div>
        </div>`;
      })
      .join("");

    grid.innerHTML = sections || `<div class="empty-state">No picks for this filter.</div>`;
    $$(".pick-row").forEach(el => {
      el.addEventListener("click", () => openDetail(el.dataset.id));
    });
  }

  // ---------- collection ----------
  // A collection entry: { id, playerId, cardName, year, grade, qty, costBasis, acquiredOn, notes }
  function currentCardValue(entry) {
    const p = PLAYERS.find(x => x.id === entry.playerId);
    if (!p) return null;
    const match = p.cards.find(c => c.name === entry.cardName && c.grade === entry.grade);
    if (match) return match.value;
    return null; // user-entered card not in dataset
  }

  function entryStats(entry) {
    const unit = currentCardValue(entry);
    const known = unit !== null;
    const currentValue = (known ? unit : 0) * entry.qty;
    const cost = (entry.costBasis || 0) * entry.qty;
    const pnl = known ? currentValue - cost : 0;
    const pct = known && cost > 0 ? (pnl / cost) * 100 : 0;
    return { unit, known, currentValue, cost, pnl, pct };
  }

  function renderCollection() {
    const view = $("#collection-view");
    const totals = state.collection.reduce(
      (acc, e) => {
        const s = entryStats(e);
        acc.cost += s.cost;
        if (s.known) acc.value += s.currentValue;
        if (s.known) acc.pnl += s.pnl;
        return acc;
      },
      { cost: 0, value: 0, pnl: 0 }
    );
    const totalPct = totals.cost > 0 ? (totals.pnl / totals.cost) * 100 : 0;

    const playerOptions = PLAYERS
      .map(p => `<option value="${p.id}">${p.name} (${p.sport})</option>`)
      .join("");

    const rows = state.collection.length
      ? state.collection.map((e, idx) => {
          const p = PLAYERS.find(x => x.id === e.playerId);
          const s = entryStats(e);
          const pnlClass = !s.known ? "flat" : s.pnl > 0 ? "up" : s.pnl < 0 ? "down" : "flat";
          return `<tr data-row="${idx}">
            <td>
              <button class="link-btn" data-open-player="${e.playerId}">${p ? p.name : "Unknown"}</button>
              <div style="color:var(--muted);font-size:11px">${p ? `${p.sport} · ${p.team}` : ""}</div>
            </td>
            <td>${e.year} ${e.cardName}<div style="color:var(--muted);font-size:11px">${e.grade}${e.notes ? ` · ${escapeHtml(e.notes)}` : ""}</div></td>
            <td>${e.qty}</td>
            <td>${formatMoney(e.costBasis || 0)}</td>
            <td>${s.known ? formatMoney(s.unit) : `<span style="color:var(--muted)">—</span>`}</td>
            <td>${s.known ? formatMoney(s.currentValue) : `<span style="color:var(--muted)">—</span>`}</td>
            <td class="${pnlClass}">${s.known ? `${formatMoney(s.pnl)} (${pctStr(s.pct)})` : `<span style="color:var(--muted)">—</span>`}</td>
            <td><button class="link-btn danger" data-remove="${idx}">Remove</button></td>
          </tr>`;
        }).join("")
      : `<tr><td colspan="8" class="empty-row">No cards yet. Add your first card below.</td></tr>`;

    view.innerHTML = `
      <div class="collection-summary">
        <div class="sum-cell"><div class="sum-key">Cards</div><div class="sum-val">${state.collection.reduce((n,e)=>n+e.qty,0)}</div></div>
        <div class="sum-cell"><div class="sum-key">Cost basis</div><div class="sum-val">${formatMoney(totals.cost)}</div></div>
        <div class="sum-cell"><div class="sum-key">Current value</div><div class="sum-val">${formatMoney(totals.value)}</div></div>
        <div class="sum-cell"><div class="sum-key">P&amp;L</div>
          <div class="sum-val ${totals.pnl > 0 ? "up" : totals.pnl < 0 ? "down" : "flat"}">${formatMoney(totals.pnl)} (${pctStr(totalPct)})</div>
        </div>
      </div>

      <div class="collection-table-wrap">
        <table class="collection-table">
          <thead>
            <tr>
              <th>Player</th><th>Card</th><th>Qty</th><th>Cost / each</th>
              <th>Now / each</th><th>Current value</th><th>P&amp;L</th><th></th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>

      <div class="add-card-form detail-block">
        <h4>Add a card</h4>
        <form id="add-card-form" class="add-grid">
          <label>Player
            <select name="playerId" required>
              <option value="">Select…</option>${playerOptions}
            </select>
          </label>
          <label>Pick from known cards
            <select name="knownCard">
              <option value="">— Or fill in manually —</option>
            </select>
          </label>
          <label>Year <input name="year" type="number" min="1900" max="2100" required></label>
          <label>Card name <input name="cardName" type="text" required placeholder="e.g. Topps Chrome RC Auto"></label>
          <label>Grade <input name="grade" type="text" required placeholder="e.g. PSA 10, Raw, BGS 9.5"></label>
          <label>Qty <input name="qty" type="number" min="1" value="1" required></label>
          <label>Cost basis (per card) <input name="costBasis" type="number" min="0" step="0.01" value="0"></label>
          <label>Acquired <input name="acquiredOn" type="date"></label>
          <label class="full">Notes <input name="notes" type="text" placeholder="Optional"></label>
          <div class="form-actions">
            <button type="submit" class="primary-btn">Add to Collection</button>
            <button type="button" id="export-json" class="link-btn">Export JSON</button>
            <label class="link-btn" style="cursor:pointer">
              Import JSON
              <input id="import-json" type="file" accept="application/json" style="display:none">
            </label>
          </div>
        </form>
      </div>
    `;

    bindCollectionEvents();
  }

  function bindCollectionEvents() {
    $$("[data-remove]").forEach(btn => {
      btn.addEventListener("click", () => {
        const i = parseInt(btn.dataset.remove, 10);
        state.collection.splice(i, 1);
        saveCollection();
        renderCollection();
      });
    });
    $$("[data-open-player]").forEach(btn => {
      btn.addEventListener("click", () => openDetail(btn.dataset.openPlayer));
    });

    const form = $("#add-card-form");
    if (!form) return;

    const knownSelect = form.querySelector('[name="knownCard"]');
    const playerSelect = form.querySelector('[name="playerId"]');

    playerSelect.addEventListener("change", () => {
      const p = PLAYERS.find(x => x.id === playerSelect.value);
      knownSelect.innerHTML = `<option value="">— Or fill in manually —</option>` +
        (p ? p.cards.map((c, i) =>
          `<option value="${i}">${c.year} ${c.name} (${c.grade}) — ${formatMoney(c.value)}</option>`
        ).join("") : "");
    });

    knownSelect.addEventListener("change", () => {
      const p = PLAYERS.find(x => x.id === playerSelect.value);
      if (!p) return;
      const c = p.cards[parseInt(knownSelect.value, 10)];
      if (!c) return;
      form.year.value = c.year;
      form.cardName.value = c.name;
      form.grade.value = c.grade;
    });

    form.addEventListener("submit", e => {
      e.preventDefault();
      const data = Object.fromEntries(new FormData(form).entries());
      if (!data.playerId) return;
      state.collection.push({
        id: "c" + Date.now(),
        playerId: data.playerId,
        year: parseInt(data.year, 10),
        cardName: data.cardName.trim(),
        grade: data.grade.trim(),
        qty: parseInt(data.qty, 10) || 1,
        costBasis: parseFloat(data.costBasis) || 0,
        acquiredOn: data.acquiredOn || null,
        notes: data.notes || "",
      });
      saveCollection();
      renderCollection();
    });

    $("#export-json").addEventListener("click", () => {
      const blob = new Blob([JSON.stringify(state.collection, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = "cardpulse-collection.json"; a.click();
      URL.revokeObjectURL(url);
    });

    $("#import-json").addEventListener("change", e => {
      const file = e.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => {
        try {
          const parsed = JSON.parse(reader.result);
          if (!Array.isArray(parsed)) throw new Error("Expected an array.");
          state.collection = parsed;
          saveCollection();
          renderCollection();
        } catch (err) {
          alert("Import failed: " + err.message);
        }
      };
      reader.readAsText(file);
    });
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
  }

  function renderCard({ player, window: w, perf, rec }) {
    const dir = dirClass(w.pct);
    const sigColor = w.pct > 1 ? "#2ecc71" : w.pct < -1 ? "#ff5566" : "#b0b6c3";
    const signal = combinedSignal(player, w);

    const perfBlock = (() => {
      if (perf.verdict === "legacy") {
        return `<div class="metric-value flat">— Retired</div>`;
      }
      if (perf.verdict === "offseason") {
        return `<div class="metric-value flat">→ No change (off-season)</div>`;
      }
      const cls = perf.verdict === "better" ? "up" : perf.verdict === "worse" ? "down" : "flat";
      const arrow = perf.verdict === "better" ? "▲" : perf.verdict === "worse" ? "▼" : "→";
      return `<div class="metric-value ${cls}"><span class="arrow">${arrow}</span>${pctStr(perf.pct || 0)} <span style="color:var(--muted);font-weight:400">${player.statKey}</span></div>`;
    })();

    return `
      <article class="card" data-id="${player.id}">
        <div class="card-head">
          <div class="player">
            <div class="player-name">${player.name}
              ${state.watchlist.has(player.id) ? `<span style="color:var(--accent)">★</span>` : ""}
            </div>
            <div class="player-meta">
              ${player.sport} · ${player.team} · ${player.position}
              ${player.status === "retired" ? `<span class="retired">RETIRED</span>` : ""}
            </div>
          </div>
          <div class="value">
            <div class="value-now">${formatMoney(w.end)}</div>
            <div class="value-change ${dir}">${dirArrow(w.pct)} ${pctStr(w.pct)}</div>
          </div>
        </div>

        <div class="card-body">
          <div class="metric">
            <div class="metric-label">Performance</div>
            ${perfBlock}
          </div>
          <div class="metric">
            <div class="metric-label">Value (${state.windowDays}d)</div>
            <div class="metric-value ${dir}">
              <span class="arrow">${dirArrow(w.pct)}</span>${pctStr(w.pct)}
            </div>
          </div>
        </div>

        <div class="spark-row">
          <div class="spark-row-label">
            <span>Card value trend</span>
            <span>${formatMoney(w.start)} → ${formatMoney(w.end)}</span>
          </div>
          ${sparkline(w.series, { color: sigColor })}
        </div>

        <div class="signal">
          <span class="rec-badge ${rec.pill}" title="${rec.basis}">${recIcon(rec.level)} ${rec.label}</span>
          <span class="signal-pill ${signal.pill}">${signal.text}</span>
        </div>
      </article>`;
  }

  function recIcon(level) {
    if (level === 2)  return "▲▲";
    if (level === 1)  return "▲";
    if (level === -1) return "▼";
    if (level === -2) return "▼▼";
    return "→";
  }

  // ---------- detail modal ----------
  function openDetail(id) {
    const p = PLAYERS.find(x => x.id === id);
    if (!p) return;
    const w = sliceWindow(p.prices, state.windowDays);
    const perf = performanceVerdict(p);
    const signal = combinedSignal(p, w);
    const rec = recommendation(p, w);
    const watching = state.watchlist.has(p.id);
    const valueColor = w.pct > 1 ? "#2ecc71" : w.pct < -1 ? "#ff5566" : "#b0b6c3";

    let perfChartBlock = "";
    if (perf.verdict === "legacy") {
      perfChartBlock = `<p style="color:var(--muted);margin:0">Retired player — no current performance to track. Card value reflects collector demand and historical legacy.</p>`;
    } else if (perf.verdict === "offseason") {
      perfChartBlock = `<p style="color:var(--muted);margin:0">${p.sport} is off-season. Performance shows <strong>no change</strong> until the season resumes.</p>`;
    } else {
      const perfSeriesForChart = p.perf.map(pt => ({ date: pt.date, value: pt.statValue }));
      perfChartBlock = `
        <div class="kv"><span>Stat</span><span>${p.statKey}</span></div>
        <div class="kv"><span>Season avg</span><span>${p.seasonAvg}</span></div>
        <div class="kv"><span>Recent avg (last ${Math.min(5, p.perf.length)})</span><span>${perf.recentAvg.toFixed(3)}</span></div>
        <div class="kv"><span>Δ vs season</span><span class="${perf.verdict === "better" ? "up" : perf.verdict === "worse" ? "down" : "flat"}">${pctStr(perf.pct || 0)}</span></div>
        ${sparkline(perfSeriesForChart, { width: 320, height: 70, color: perf.verdict === "better" ? "#2ecc71" : perf.verdict === "worse" ? "#ff5566" : "#b0b6c3" })}
      `;
    }

    const cardsRows = p.cards
      .map(c => {
        const compsList = (p.comps[c.name] || [])
          .map(s => `<div class="comp-row">
            <span>${s.date}</span>
            <span>${s.grade}</span>
            <span style="color:var(--muted)">${s.platform}</span>
            <strong>${formatMoney(s.price)}</strong>
          </div>`)
          .join("");
        return `<div class="card-block">
          <div class="card-row">
            <span>${c.year} ${c.name} <span style="color:var(--muted)">(${c.grade})</span></span>
            <strong>${formatMoney(c.value)}</strong>
          </div>
          <div class="comps">
            <div class="comps-head">Comps</div>
            ${compsList || `<div style="color:var(--muted);font-size:12px">No recent comps.</div>`}
          </div>
        </div>`;
      })
      .join("");

    // Recent sales feed (across all of this player's cards)
    const salesRows = (p.recentSales || [])
      .map(s => `<div class="sale-row">
        <span>${s.date}</span>
        <span>${s.card} <span style="color:var(--muted)">(${s.grade})</span></span>
        <span style="color:var(--muted)">${s.platform}</span>
        <strong>${formatMoney(s.price)}</strong>
      </div>`)
      .join("");

    // Current stats line
    let statsBlock = "";
    if (p.currentStats) {
      const cs = p.currentStats;
      const entries = Object.entries(cs.line)
        .map(([k, v]) => {
          const display = typeof v === "number" && !Number.isInteger(v) ? v.toFixed(3) : v;
          return `<div class="stat-cell"><div class="stat-key">${k.replace(/_/g, " ")}</div><div class="stat-val">${display}</div></div>`;
        })
        .join("");
      statsBlock = `
        <div class="detail-block stats-block">
          <div class="stats-head">
            <h4 style="margin:0">Current stats</h4>
            <span class="player-meta">${cs.season}${p.status === "retired" ? "" : " season"}</span>
          </div>
          <div class="stats-grid">${entries}</div>
        </div>`;
    }

    $("#detail-body").innerHTML = `
      <div class="detail-head">
        <div>
          <h2>${p.name} ${p.status === "retired" ? `<span class="retired" style="color:var(--warn)">· RETIRED</span>` : ""}</h2>
          <div class="player-meta">${p.sport} · ${p.team} · ${p.position}</div>
        </div>
        <div class="value">
          <div class="value-now">${formatMoney(w.end)}</div>
          <div class="value-change ${dirClass(w.pct)}">${dirArrow(w.pct)} ${pctStr(w.pct)} (${state.windowDays}d)</div>
          <button id="watch-toggle" class="tab" style="margin-top:8px">${watching ? "★ On Watchlist" : "☆ Add to Watchlist"}</button>
        </div>
      </div>

      <div class="rec-banner ${rec.pill}">
        <div class="rec-banner-label">${recIcon(rec.level)} ${rec.label}</div>
        <div class="rec-banner-basis">${rec.basis}</div>
      </div>

      <div class="signal" style="border:0;padding:0;margin-bottom:14px">
        <span class="signal-pill ${signal.pill}">${signal.text}</span>
      </div>

      <div class="detail-grid">
        <div class="detail-block">
          <h4>Performance</h4>
          ${perfChartBlock}
        </div>
        <div class="detail-block">
          <h4>Value summary</h4>
          <div class="kv"><span>Window</span><span>${state.windowDays} days</span></div>
          <div class="kv"><span>Start</span><span>${formatMoney(w.start)}</span></div>
          <div class="kv"><span>Now</span><span>${formatMoney(w.end)}</span></div>
          <div class="kv"><span>Change</span><span class="${dirClass(w.pct)}">${pctStr(w.pct)}</span></div>
          <div class="kv"><span>1y range</span><span>${formatMoney(Math.min(...p.prices.map(x => x.value)))} – ${formatMoney(Math.max(...p.prices.map(x => x.value)))}</span></div>
        </div>
      </div>

      <div class="detail-chart">
        <h4 style="margin:0 0 8px;font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:0.5px">Card value, last ${state.windowDays}d</h4>
        ${bigChart(w.series, valueColor)}
      </div>

      ${statsBlock}

      <div class="detail-block">
        <h4>Recent sales</h4>
        <div class="sales-list">
          ${salesRows || `<div style="color:var(--muted);font-size:12px">No recent sales.</div>`}
        </div>
      </div>

      <div class="detail-block">
        <h4>Cards & comps</h4>
        <div class="cards-list">${cardsRows}</div>
      </div>
    `;

    $("#watch-toggle").addEventListener("click", () => {
      if (state.watchlist.has(p.id)) state.watchlist.delete(p.id);
      else state.watchlist.add(p.id);
      localStorage.setItem("cp_watch", JSON.stringify([...state.watchlist]));
      openDetail(p.id);
      renderGrid();
    });

    $("#detail-modal").classList.remove("hidden");
  }

  function closeDetail() {
    $("#detail-modal").classList.add("hidden");
  }

  // ---------- wiring ----------
  function bindEvents() {
    $$(".tab").forEach(t =>
      t.addEventListener("click", () => {
        $$(".tab").forEach(x => x.classList.remove("active"));
        t.classList.add("active");
        state.tab = t.dataset.tab;
        renderGrid();
      })
    );
    $("#sport-filter").addEventListener("change", e => {
      state.sport = e.target.value;
      renderGrid();
    });
    $("#window-filter").addEventListener("change", e => {
      state.windowDays = parseInt(e.target.value, 10);
      renderGrid();
    });
    $("#sort-filter").addEventListener("change", e => {
      state.sort = e.target.value;
      renderGrid();
    });
    $("#rec-filter").addEventListener("change", e => {
      state.recFilter = e.target.value;
      renderGrid();
    });
    $("#search").addEventListener("input", e => {
      state.query = e.target.value;
      renderGrid();
    });
    $$("[data-close]").forEach(el => el.addEventListener("click", closeDetail));
    document.addEventListener("keydown", e => {
      if (e.key === "Escape") closeDetail();
    });
  }

  // ---------- init ----------
  $("#today-stamp").textContent = `As of ${TODAY.toISOString().slice(0, 10)}`;
  bindEvents();
  renderGrid();
})();
