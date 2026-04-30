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
 * Dates are ISO strings. Today is treated as 2026-04-30 by app.js.
 */

const TODAY = new Date("2026-04-30");

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

window.CARDPULSE_DATA = { PLAYERS, SEASON_MONTHS, TODAY };
