/* Mock dataset for CardPulse.
 *
 * Each player has:
 *   - status: "active" or "retired"
 *   - sport:  MLB / NBA / NFL / NHL
 *   - statKey: short label for primary stat (OPS, PPG, PASSER RTG, PPG)
 *   - perf:   array of { date, statValue, gameOrWeek } – ordered oldest → newest.
 *             For retired players this is empty.
 *   - prices: array of { date, value } – ordered oldest → newest.
 *   - cards:  array of representative cards { name, year, grade, value }.
 *
 * Dates are ISO strings. TODAY is the real current date, so the season
 * logic, price windows, and stats always reflect "now" — the app
 * self-updates on every load, and app.js live-ticks prices after that.
 */

const TODAY = new Date();

// ---------- helpers used only inside this file ----------
function daysAgo(n) {
  const d = new Date(TODAY);
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

// Generates a synthetic price series with a trend + noise.
function priceSeries(start, end, days, noise = 0.03) {
  const arr = [];
  const step = (end - start) / (days - 1);
  for (let i = 0; i < days; i++) {
    const trend = start + step * i;
    const wobble = trend * (Math.sin(i / 4) * noise + (Math.random() - 0.5) * noise * 1.5);
    arr.push({
      date: daysAgo(days - 1 - i),
      value: Math.max(1, Math.round((trend + wobble) * 100) / 100),
    });
  }
  return arr;
}

// Generates a synthetic stat series for the last N games.
function perfSeries(games, base, swing, label = "G") {
  const arr = [];
  for (let i = 0; i < games; i++) {
    const v = base + (Math.random() - 0.5) * swing * 2;
    arr.push({
      date: daysAgo((games - 1 - i) * 2),
      statValue: Math.round(v * 1000) / 1000,
      gameOrWeek: `${label}${i + 1}`,
    });
  }
  return arr;
}

// ---------- player records ----------
const PLAYERS = [
  // ---- MLB (in-season in late April) ----
  {
    id: "ohtani",
    name: "Shohei Ohtani",
    team: "Dodgers",
    sport: "MLB",
    position: "DH/SP",
    status: "active",
    statKey: "OPS",
    seasonAvg: 1.012,
    perf: perfSeries(12, 1.18, 0.25),     // recent 12 games trending up vs season avg
    prices: priceSeries(820, 1240, 365),  // strong year-long uptrend
    cards: [
      { name: "Topps Chrome RC Auto", year: 2018, grade: "PSA 10", value: 12500 },
      { name: "Bowman Chrome Prospect Auto", year: 2013, grade: "PSA 10", value: 38000 },
      { name: "Topps Update RC", year: 2018, grade: "PSA 10", value: 1240 },
    ],
  },
  {
    id: "judge",
    name: "Aaron Judge",
    team: "Yankees",
    sport: "MLB",
    position: "OF",
    status: "active",
    statKey: "OPS",
    seasonAvg: 1.045,
    perf: perfSeries(12, 0.82, 0.2),       // trending below season avg = worse
    prices: priceSeries(610, 540, 365),    // year-long mild downtrend
    cards: [
      { name: "Topps Chrome RC", year: 2017, grade: "PSA 10", value: 540 },
      { name: "Bowman Chrome Auto", year: 2013, grade: "PSA 10", value: 4200 },
    ],
  },
  {
    id: "trout",
    name: "Mike Trout",
    team: "Angels",
    sport: "MLB",
    position: "OF",
    status: "active",
    statKey: "OPS",
    seasonAvg: 0.984,
    perf: perfSeries(12, 0.95, 0.18),      // roughly flat
    prices: priceSeries(720, 690, 365),
    cards: [
      { name: "Bowman Chrome Draft Auto", year: 2009, grade: "BGS 9.5", value: 18500 },
      { name: "Topps Update RC", year: 2011, grade: "PSA 10", value: 690 },
    ],
  },
  {
    id: "soto",
    name: "Juan Soto",
    team: "Mets",
    sport: "MLB",
    position: "OF",
    status: "active",
    statKey: "OPS",
    seasonAvg: 0.966,
    perf: perfSeries(12, 1.08, 0.18),
    prices: priceSeries(310, 470, 365),
    cards: [
      { name: "Bowman Chrome Prospect Auto", year: 2016, grade: "PSA 10", value: 4700 },
      { name: "Topps Chrome RC", year: 2019, grade: "PSA 10", value: 470 },
    ],
  },

  // ---- NBA (playoffs in April – treat as in-season) ----
  {
    id: "wemby",
    name: "Victor Wembanyama",
    team: "Spurs",
    sport: "NBA",
    position: "C",
    status: "active",
    statKey: "PPG",
    seasonAvg: 24.3,
    perf: perfSeries(10, 31.2, 6),         // surging
    prices: priceSeries(640, 1180, 365),
    cards: [
      { name: "Topps Chrome RC Auto", year: 2023, grade: "PSA 10", value: 11800 },
      { name: "Prizm RC", year: 2023, grade: "PSA 10", value: 1180 },
    ],
  },
  {
    id: "jokic",
    name: "Nikola Jokić",
    team: "Nuggets",
    sport: "NBA",
    position: "C",
    status: "active",
    statKey: "PPG",
    seasonAvg: 28.1,
    perf: perfSeries(10, 30.4, 4),
    prices: priceSeries(880, 940, 365),
    cards: [
      { name: "Prizm RC", year: 2015, grade: "PSA 10", value: 940 },
      { name: "Optic Holo RC", year: 2015, grade: "PSA 10", value: 1700 },
    ],
  },
  {
    id: "lebron",
    name: "LeBron James",
    team: "Lakers",
    sport: "NBA",
    position: "F",
    status: "active",
    statKey: "PPG",
    seasonAvg: 24.8,
    perf: perfSeries(10, 22.1, 3),         // worse than career/season avg
    prices: priceSeries(2400, 2150, 365),
    cards: [
      { name: "Topps Chrome RC", year: 2003, grade: "PSA 10", value: 9800 },
      { name: "Upper Deck Exquisite RPA /99", year: 2003, grade: "BGS 9", value: 215000 },
    ],
  },
  {
    id: "curry",
    name: "Stephen Curry",
    team: "Warriors",
    sport: "NBA",
    position: "G",
    status: "active",
    statKey: "PPG",
    seasonAvg: 26.4,
    perf: perfSeries(10, 27.1, 4),
    prices: priceSeries(1450, 1490, 365),
    cards: [
      { name: "Topps Chrome RC", year: 2009, grade: "PSA 10", value: 1490 },
      { name: "National Treasures RPA /99", year: 2009, grade: "BGS 9.5", value: 95000 },
    ],
  },

  // ---- NFL (off-season in April → no perf data) ----
  {
    id: "mahomes",
    name: "Patrick Mahomes",
    team: "Chiefs",
    sport: "NFL",
    position: "QB",
    status: "active",
    statKey: "PASSER RTG",
    seasonAvg: 99.6,
    perf: [],                              // off-season
    prices: priceSeries(1240, 1310, 365),
    cards: [
      { name: "Prizm RC", year: 2017, grade: "PSA 10", value: 1310 },
      { name: "National Treasures RPA /99", year: 2017, grade: "BGS 9.5", value: 195000 },
    ],
  },
  {
    id: "allen",
    name: "Josh Allen",
    team: "Bills",
    sport: "NFL",
    position: "QB",
    status: "active",
    statKey: "PASSER RTG",
    seasonAvg: 96.4,
    perf: [],                              // off-season
    prices: priceSeries(620, 580, 365),
    cards: [
      { name: "Prizm RC", year: 2018, grade: "PSA 10", value: 580 },
      { name: "Donruss Optic RC", year: 2018, grade: "PSA 10", value: 220 },
    ],
  },

  // ---- NHL (in playoffs late April) ----
  {
    id: "mcdavid",
    name: "Connor McDavid",
    team: "Oilers",
    sport: "NHL",
    position: "C",
    status: "active",
    statKey: "PPG",
    seasonAvg: 1.52,
    perf: perfSeries(10, 1.81, 0.5),
    prices: priceSeries(880, 1020, 365),
    cards: [
      { name: "Upper Deck Young Guns RC", year: 2015, grade: "PSA 10", value: 1020 },
      { name: "The Cup RPA /99", year: 2015, grade: "BGS 9.5", value: 78000 },
    ],
  },

  // ---- Retired (no perf — only value trends) ----
  {
    id: "mj",
    name: "Michael Jordan",
    team: "Bulls",
    sport: "NBA",
    position: "G",
    status: "retired",
    statKey: "PPG",
    seasonAvg: 30.1,
    perf: [],
    prices: priceSeries(8200, 9100, 365),
    cards: [
      { name: "Fleer RC", year: 1986, grade: "PSA 10", value: 410000 },
      { name: "Fleer RC", year: 1986, grade: "PSA 9", value: 9100 },
    ],
  },
  {
    id: "kobe",
    name: "Kobe Bryant",
    team: "Lakers",
    sport: "NBA",
    position: "G",
    status: "retired",
    statKey: "PPG",
    seasonAvg: 25.0,
    perf: [],
    prices: priceSeries(3200, 4100, 365),
    cards: [
      { name: "Topps Chrome RC", year: 1996, grade: "PSA 10", value: 4100 },
      { name: "Topps Chrome RC Refractor", year: 1996, grade: "PSA 10", value: 78000 },
    ],
  },
  {
    id: "ruth",
    name: "Babe Ruth",
    team: "Yankees",
    sport: "MLB",
    position: "OF",
    status: "retired",
    statKey: "OPS",
    seasonAvg: 1.164,
    perf: [],
    prices: priceSeries(112000, 135000, 365),
    cards: [
      { name: "Goudey", year: 1933, grade: "PSA 7", value: 135000 },
    ],
  },
  {
    id: "gretzky",
    name: "Wayne Gretzky",
    team: "Oilers",
    sport: "NHL",
    position: "C",
    status: "retired",
    statKey: "PPG",
    seasonAvg: 1.92,
    perf: [],
    prices: priceSeries(15800, 14200, 365),
    cards: [
      { name: "O-Pee-Chee RC", year: 1979, grade: "PSA 8", value: 14200 },
    ],
  },
  {
    id: "brady",
    name: "Tom Brady",
    team: "Patriots",
    sport: "NFL",
    position: "QB",
    status: "retired",
    statKey: "PASSER RTG",
    seasonAvg: 97.2,
    perf: [],
    prices: priceSeries(2400, 2280, 365),
    cards: [
      { name: "Bowman Chrome RC", year: 2000, grade: "PSA 10", value: 2280 },
      { name: "Playoff Contenders Auto", year: 2000, grade: "BGS 9.5", value: 510000 },
    ],
  },
];

// Season windows: months when each sport is "in season" (1-indexed).
const SEASON_MONTHS = {
  MLB: [3, 4, 5, 6, 7, 8, 9, 10],
  NBA: [10, 11, 12, 1, 2, 3, 4, 5, 6],
  NFL: [9, 10, 11, 12, 1, 2],
  NHL: [10, 11, 12, 1, 2, 3, 4, 5, 6],
};

// ---------- per-player current stats and recent sales ----------
// Stats vary by sport; we only define the columns that make sense per sport.
const CURRENT_STATS = {
  ohtani:   { season: "2026", line: { GP: 28, AB: 102, HR: 11, RBI: 27, AVG: 0.318, OBP: 0.412, SLG: 0.701, OPS: 1.113 } },
  judge:    { season: "2026", line: { GP: 27, AB:  98, HR:  6, RBI: 18, AVG: 0.241, OBP: 0.359, SLG: 0.461, OPS: 0.820 } },
  trout:    { season: "2026", line: { GP: 24, AB:  88, HR:  5, RBI: 14, AVG: 0.262, OBP: 0.371, SLG: 0.502, OPS: 0.873 } },
  soto:     { season: "2026", line: { GP: 27, AB:  96, HR: 10, RBI: 24, AVG: 0.310, OBP: 0.428, SLG: 0.676, OPS: 1.104 } },
  wemby:    { season: "2025-26", line: { GP: 78, PPG: 25.4, RPG: 11.2, APG: 4.1, BPG: 3.8, FG_PCT: 0.512, "3P_PCT": 0.358 } },
  jokic:    { season: "2025-26", line: { GP: 76, PPG: 29.8, RPG: 12.4, APG: 9.6, "FG_PCT": 0.582, "3P_PCT": 0.371 } },
  lebron:   { season: "2025-26", line: { GP: 71, PPG: 22.4, RPG:  7.3, APG: 8.1, "FG_PCT": 0.498, "3P_PCT": 0.341 } },
  curry:    { season: "2025-26", line: { GP: 74, PPG: 27.0, RPG:  4.6, APG: 6.0, "FG_PCT": 0.469, "3P_PCT": 0.428 } },
  mahomes:  { season: "2025", line: { GP: 17, "PASS_YDS": 4602, "PASS_TD": 36, INT: 11, "PASSER_RTG": 101.4, "QBR": 71.2 } },
  allen:    { season: "2025", line: { GP: 17, "PASS_YDS": 4128, "PASS_TD": 30, INT: 14, "PASSER_RTG": 94.8,  "QBR": 67.5, "RUSH_TD": 11 } },
  mcdavid:  { season: "2025-26", line: { GP: 80, G: 49, A: 92, P: 141, "+/-":  24, PIM: 28 } },
  // Retired / legacy career lines:
  mj:       { season: "Career", line: { GP: 1072, PPG: 30.1, RPG: 6.2, APG: 5.3, "FG_PCT": 0.497, RINGS: 6, MVPs: 5 } },
  kobe:     { season: "Career", line: { GP: 1346, PPG: 25.0, RPG: 5.2, APG: 4.7, "FG_PCT": 0.447, RINGS: 5, MVPs: 1 } },
  ruth:     { season: "Career", line: { GP: 2503, AB: 8398, HR: 714, RBI: 2214, AVG: 0.342, OBP: 0.474, SLG: 0.690, OPS: 1.164 } },
  gretzky:  { season: "Career", line: { GP: 1487, G: 894, A: 1963, P: 2857, RINGS: 4, MVPs: 9 } },
  brady:    { season: "Career", line: { GP: 335, "PASS_YDS": 89214, "PASS_TD": 649, INT: 212, "PASSER_RTG": 97.2, RINGS: 7, MVPs: 3 } },
};

// Synthetic recent-sales feed per player. Real apps would pull from eBay,
// Goldin, PWCC etc. — here we generate plausible comps from the card list.
function buildSales(player) {
  const sales = [];
  const platforms = ["eBay", "Goldin", "PWCC", "MySlabs", "Heritage"];
  for (let i = 0; i < 6; i++) {
    const card = player.cards[i % player.cards.length];
    const drift = 1 + (Math.random() - 0.5) * 0.12;
    const price = Math.max(1, Math.round(card.value * drift));
    sales.push({
      date: daysAgo(Math.floor(i * 4 + Math.random() * 3) + 1),
      card: `${card.year} ${card.name}`,
      grade: card.grade,
      price,
      platform: platforms[Math.floor(Math.random() * platforms.length)],
    });
  }
  // Newest first.
  sales.sort((a, b) => (a.date < b.date ? 1 : -1));
  return sales;
}

// Build comps: for each card a player owns, a few similar past sales at
// nearby grades.
function buildComps(player) {
  const comps = {};
  const otherGrades = ["PSA 10", "PSA 9", "BGS 9.5", "BGS 9", "SGC 10"];
  player.cards.forEach(card => {
    const list = [];
    for (let i = 0; i < 4; i++) {
      const g = otherGrades[(i + (card.grade.length % 5)) % otherGrades.length];
      const factor = g === card.grade
        ? 0.95 + Math.random() * 0.1
        : g.includes("10") ? 1.0
        : g.includes("9.5") ? 0.6
        : g.includes("9") ? 0.35
        : 0.25;
      list.push({
        date: daysAgo(7 + i * 9 + Math.floor(Math.random() * 5)),
        grade: g,
        price: Math.max(1, Math.round(card.value * factor * (0.95 + Math.random() * 0.1))),
        platform: ["eBay", "Goldin", "PWCC", "MySlabs"][i % 4],
      });
    }
    list.sort((a, b) => (a.date < b.date ? 1 : -1));
    comps[card.name] = list;
  });
  return comps;
}

PLAYERS.forEach(p => {
  p.currentStats = CURRENT_STATS[p.id] || null;
  p.recentSales = buildSales(p);
  p.comps = buildComps(p);
});

window.CARDPULSE_DATA = { PLAYERS, SEASON_MONTHS, TODAY };
