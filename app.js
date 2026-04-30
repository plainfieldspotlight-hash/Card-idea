(() => {
  const { PLAYERS, SEASON_MONTHS, TODAY } = window.CARDPULSE_DATA;

  const state = {
    tab: "movers",
    sport: "all",
    windowDays: 30,
    sort: "value-change-desc",
    query: "",
    watchlist: new Set(JSON.parse(localStorage.getItem("cp_watch") || "[]")),
  };

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
    const items = visiblePlayers();
    if (!items.length) {
      grid.innerHTML = `<div class="empty-state">No players match these filters.</div>`;
      return;
    }
    grid.innerHTML = items.map(renderCard).join("");
    $$(".card").forEach(el => {
      el.addEventListener("click", () => openDetail(el.dataset.id));
    });
  }

  function renderCard({ player, window: w, perf }) {
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
          <span class="signal-pill ${signal.pill}">${signal.text}</span>
        </div>
      </article>`;
  }

  // ---------- detail modal ----------
  function openDetail(id) {
    const p = PLAYERS.find(x => x.id === id);
    if (!p) return;
    const w = sliceWindow(p.prices, state.windowDays);
    const perf = performanceVerdict(p);
    const signal = combinedSignal(p, w);
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
      .map(
        c => `<div class="card-row">
          <span>${c.year} ${c.name} <span style="color:var(--muted)">(${c.grade})</span></span>
          <strong>${formatMoney(c.value)}</strong>
        </div>`
      )
      .join("");

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

      <div class="detail-block">
        <h4>Representative cards</h4>
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
