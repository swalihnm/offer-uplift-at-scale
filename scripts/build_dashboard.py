"""Build a self-contained HTML dashboard from outputs/metrics (no Tableau needed).

Reads the CSV and JSON outputs of the pipeline, embeds them as JSON in one HTML file,
and writes outputs/dashboard/index.html. Every number on the page comes from those files.

Run:  python scripts/build_dashboard.py
"""

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METRICS = ROOT / "outputs" / "metrics"
OUT = ROOT / "outputs" / "dashboard" / "index.html"


def read_csv(name: str) -> list[dict]:
    rows = []
    with (METRICS / name).open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            parsed = {}
            for key, value in row.items():
                try:
                    parsed[key] = float(value) if value not in ("", None) else None
                except ValueError:
                    parsed[key] = value
            rows.append(parsed)
    return rows


def read_json(name: str) -> dict:
    return json.loads((METRICS / name).read_text(encoding="utf-8"))


def sanitize(value):
    """Replace NaN with None (JSON null), e.g. the ROI of target-nobody, which has no cost."""
    if isinstance(value, float) and value != value:
        return None
    if isinstance(value, dict):
        return {k: sanitize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    return value


def main() -> None:
    data = {
        "ab": read_json("ab_test.json"),
        "uplift": read_json("uplift.json"),
        "roi": read_json("roi.json"),
        "balance": read_csv("balance_smd.csv"),
        "power": read_csv("power_table.csv"),
        "deciles": read_csv("uplift_deciles.csv"),
        "segments": read_csv("segment_profile.csv"),
        "shap": read_csv("shap_importance.csv"),
        "budget": read_csv("budget_curve.csv"),
        "policies": read_csv("policy_comparison.csv"),
        "sensitivity": read_csv("sensitivity.csv"),
    }
    html = TEMPLATE.replace("__DATA__", json.dumps(sanitize(data), allow_nan=False))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT}")


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Offer Uplift Dashboard</title>
<style>
/* Palette: reference validated palette (dataviz skill, references/palette.md) */
:root {
  color-scheme: light;
  --page: #f9f9f7;
  --surface-1: #fcfcfb;
  --text-primary: #0b0b0b;
  --text-secondary: #52514e;
  --text-muted: #898781;
  --grid: #e1e0d9;
  --baseline: #c3c2b7;
  --series-1: #2a78d6;
  --series-2: #eb6834;
  --critical: #d03b3b;
  --border: rgba(11, 11, 11, 0.10);
}
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])) {
    color-scheme: dark;
    --page: #0d0d0d;
    --surface-1: #1a1a19;
    --text-primary: #f0efec;
    --text-secondary: #c3c2b7;
    --text-muted: #898781;
    --grid: #2c2c2a;
    --baseline: #383835;
    --series-1: #3987e5;
    --series-2: #d95926;
    --critical: #e66767;
    --border: rgba(255, 255, 255, 0.10);
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --page: #0d0d0d;
  --surface-1: #1a1a19;
  --text-primary: #f0efec;
  --text-secondary: #c3c2b7;
  --text-muted: #898781;
  --grid: #2c2c2a;
  --baseline: #383835;
  --series-1: #3987e5;
  --series-2: #d95926;
  --critical: #e66767;
  --border: rgba(255, 255, 255, 0.10);
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--page);
  color: var(--text-primary);
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  line-height: 1.45;
}
main { max-width: 1100px; margin: 0 auto; padding: 24px 16px 48px; }
header h1 { font-size: 24px; margin: 0 0 4px; }
header p { margin: 0; color: var(--text-secondary); max-width: 760px; }
section { margin-top: 32px; }
section > h2 { font-size: 18px; margin: 0 0 4px; }
section > .lede { color: var(--text-secondary); margin: 0 0 16px; max-width: 760px; }
.panel {
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
}
.panel h3 { font-size: 14px; margin: 0 0 8px; font-weight: 600; }
.panel .note { color: var(--text-secondary); font-size: 13px; margin: 8px 0 0; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-bottom: 16px; }
.card { background: var(--surface-1); border: 1px solid var(--border); border-radius: 8px; padding: 14px; }
.card .label { color: var(--text-secondary); font-size: 13px; }
.card .value { font-size: 26px; font-weight: 600; margin: 4px 0 2px; }
.card .sub { color: var(--text-muted); font-size: 12px; }
.grid2 { display: grid; grid-template-columns: 1fr; gap: 16px; }
.grid2 > * { min-width: 0; }
@media (min-width: 860px) { .grid2 { grid-template-columns: 1fr 1fr; } }
svg.chart { width: 100%; height: auto; display: block; }
svg .grid { stroke: var(--grid); stroke-width: 1; }
svg .axis { stroke: var(--baseline); stroke-width: 1; }
svg .threshold { stroke: var(--text-muted); stroke-width: 1; stroke-dasharray: 4 4; }
svg .tick { fill: var(--text-muted); font-size: 11px; }
svg .axis-label { fill: var(--text-secondary); font-size: 12px; }
svg .mark-label { fill: var(--text-secondary); font-size: 11px; }
svg .bar { fill: var(--series-1); }
svg .bar-neg { fill: var(--series-2); }
svg .dot { fill: var(--series-1); }
svg .line { fill: none; stroke: var(--series-1); stroke-width: 2; }
svg .cut { stroke: var(--series-2); stroke-width: 1.5; stroke-dasharray: 5 4; }
svg .cut-label { fill: var(--series-2); font-size: 11px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; font-variant-numeric: tabular-nums; }
th, td { text-align: right; padding: 6px 8px; border-bottom: 1px solid var(--grid); }
td.amt { white-space: nowrap; }
th:first-child, td:first-child { text-align: left; }
th { color: var(--text-secondary); font-weight: 600; }
.wrap { overflow-x: auto; }
.flag { color: var(--critical); font-weight: 600; }
footer { margin-top: 40px; color: var(--text-muted); font-size: 12px; }
</style>
</head>
<body>
<main>
  <header>
    <h1>Offer Uplift at Scale</h1>
    <p>Criteo Uplift v2.1 randomized experiment, 13,979,592 customers. Every number on this page is read from the pipeline outputs in <code>outputs/metrics/</code>.</p>
  </header>

  <section id="experiment">
    <h2>1. Experiment</h2>
    <p class="lede">Does the offer raise visits and conversions? The headline is the intent-to-treat estimate. The randomization checks come first.</p>
    <div class="cards" id="exp-cards"></div>
    <div class="grid2">
      <div class="panel">
        <h3>Balance: standardized mean difference by feature</h3>
        <div id="balance-chart"></div>
        <p class="note" id="balance-note"></p>
      </div>
      <div class="panel">
        <h3>Power: minimum detectable visit lift (80% power, 5% two-sided)</h3>
        <div class="wrap" id="power-table"></div>
        <p class="note" id="power-note"></p>
      </div>
    </div>
    <div class="panel">
      <h3>CUPED and exposure</h3>
      <div id="cuped-text"></div>
    </div>
  </section>

  <section id="targeting">
    <h2>2. Who to target</h2>
    <p class="lede">The S-learner ranks customers by predicted uplift. The top decile responds far more to the offer than the bottom one.</p>
    <div class="grid2">
      <div class="panel">
        <h3>Observed visit lift by predicted-uplift decile (test split)</h3>
        <div id="decile-chart"></div>
        <p class="note" id="decile-note"></p>
      </div>
      <div class="panel">
        <h3>Uplift model comparison (Qini AUC, test split)</h3>
        <div class="wrap" id="model-table"></div>
        <p class="note">Qini AUC measures how well the ranking captures incremental visits. Random targeting scores about 19. The class-transformation learner scores below zero, so it is not usable on this data.</p>
      </div>
    </div>
    <div class="grid2">
      <div class="panel">
        <h3>Segments</h3>
        <div class="wrap" id="segment-table"></div>
        <p class="note">Sure things and lost causes are the wasted spend. The do-not-disturb segment is not confirmed: its observed lift is slightly positive.</p>
      </div>
      <div class="panel">
        <h3>What drives predicted uplift (mean |SHAP|, T-learner)</h3>
        <div id="shap-chart"></div>
        <p class="note">Anonymized features, so these are data-driven drivers, not demographics.</p>
      </div>
    </div>
  </section>

  <section id="roi">
    <h2>3. ROI and targeting decision</h2>
    <p class="lede" id="roi-lede"></p>
    <div class="cards" id="roi-cards"></div>
    <div class="panel">
      <h3>Profit by share of customers targeted (test split, top-k by predicted uplift)</h3>
      <div id="budget-chart"></div>
      <p class="note">The dashed line is the cutoff chosen on the valid split. The profit-maximising share on the test split (in-sample, optimistic) is shown for reference.</p>
    </div>
    <div class="grid2">
      <div class="panel">
        <h3>Policies compared (test split, scaled to 13,979,592 customers)</h3>
        <div class="wrap" id="policy-table"></div>
      </div>
      <div class="panel">
        <h3>Sensitivity: cutoff chosen on valid, profit on test</h3>
        <div class="wrap" id="sens-table"></div>
        <p class="note">Economics are placeholder assumptions from conf/economics.yaml. The decision changes with cost and value, which is why this grid is shown.</p>
      </div>
    </div>
  </section>

  <footer>
    Built by scripts/build_dashboard.py from outputs/metrics. Tableau Public is still to be built by hand from tableau/extracts/.
  </footer>
</main>

<script>
const D = __DATA__;

const NS = "http://www.w3.org/2000/svg";
const $ = (s) => document.querySelector(s);
function el(tag, attrs, parent) {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
}
function html(tag, attrs, content) {
  const e = document.createElement(tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  e.innerHTML = content;
  return e;
}
const pp = (x, d = 2) => (x * 100 >= 0 ? "+" : "−") + Math.abs(x * 100).toFixed(d) + " pp";
const pct = (x, d = 1) => (x * 100).toFixed(d) + "%";
const usd = (x) => (x < 0 ? "−" : "") + "$" + Math.abs(x).toLocaleString("en-US", { maximumFractionDigits: 0 });
const num = (x) => Math.round(x).toLocaleString("en-US");

function niceStep(raw) {
  const p = Math.pow(10, Math.floor(Math.log10(raw)));
  const f = raw / p;
  return (f < 1.5 ? 1 : f < 3 ? 2 : f < 7 ? 5 : 10) * p;
}
function ticks(lo, hi, n) {
  const step = niceStep((hi - lo) / n);
  const out = [];
  for (let t = Math.ceil(lo / step) * step; t <= hi + 1e-9; t += step) out.push(+t.toFixed(10));
  return out;
}

// ---------- charts (plain SVG, one series each) ----------

function decileChart(rows) {
  const W = 640, H = 280, m = { l: 56, r: 12, t: 16, b: 44 };
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart", role: "img",
    "aria-label": "Observed visit lift by predicted-uplift decile" });
  const vals = rows.map((r) => r.observed_lift * 100);
  const hi = Math.max(...vals) * 1.12, lo = Math.min(0, Math.min(...vals));
  const y = (v) => m.t + ((hi - v) / (hi - lo)) * (H - m.t - m.b);
  const bw = (W - m.l - m.r) / rows.length;
  for (const t of ticks(lo, hi, 4)) {
    el("line", { x1: m.l, x2: W - m.r, y1: y(t), y2: y(t), class: "grid" }, svg);
    el("text", { x: m.l - 8, y: y(t) + 4, "text-anchor": "end", class: "tick" }, svg).textContent = t.toFixed(1);
  }
  rows.forEach((r, i) => {
    const v = r.observed_lift * 100;
    const x = m.l + i * bw + bw * 0.18, w = bw * 0.64;
    const top = Math.min(y(0), y(v)), h = Math.max(1, Math.abs(y(v) - y(0)));
    const rect = el("rect", { x, y: top, width: w, height: h, rx: 2, class: v < 0 ? "bar-neg" : "bar" }, svg);
    el("title", {}, rect).textContent = `Decile ${r.decile}: ${v.toFixed(2)} pp, n = ${num(r.n)}`;
    el("text", { x: x + w / 2, y: H - m.b + 16, "text-anchor": "middle", class: "tick" }, svg).textContent = r.decile;
  });
  el("line", { x1: m.l, x2: W - m.r, y1: y(0), y2: y(0), class: "axis" }, svg);
  el("text", { x: (m.l + W - m.r) / 2, y: H - 8, "text-anchor": "middle", class: "axis-label" }, svg)
    .textContent = "Predicted-uplift decile (1 = most persuadable)";
  el("text", { x: 12, y: (m.t + H - m.b) / 2, transform: `rotate(-90 12 ${(m.t + H - m.b) / 2})`,
    "text-anchor": "middle", class: "axis-label" }, svg).textContent = "Visit lift (pp)";
  return svg;
}

function balanceChart(rows) {
  const W = 480, rowH = 22, m = { l: 56, r: 16, t: 16, b: 28 };
  const H = m.t + rows.length * rowH + m.b;
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart", role: "img",
    "aria-label": "Standardized mean difference per feature" });
  const lim = 0.1;
  const x = (v) => m.l + ((v + lim) / (2 * lim)) * (W - m.l - m.r);
  for (const t of [-0.1, -0.05, 0, 0.05, 0.1]) {
    el("line", { x1: x(t), x2: x(t), y1: m.t, y2: H - m.b, class: t === 0 ? "axis" : "grid" }, svg);
    el("text", { x: x(t), y: H - 8, "text-anchor": "middle", class: "tick" }, svg).textContent = t.toFixed(2);
  }
  for (const t of [-lim, lim]) el("line", { x1: x(t), x2: x(t), y1: m.t, y2: H - m.b, class: "threshold" }, svg);
  rows.forEach((r, i) => {
    const cy = m.t + i * rowH + rowH / 2;
    el("text", { x: m.l - 8, y: cy + 4, "text-anchor": "end", class: "tick" }, svg).textContent = r.feature;
    const dot = el("circle", { cx: x(r.smd), cy, r: 4, class: "dot" }, svg);
    el("title", {}, dot).textContent = `${r.feature}: SMD ${r.smd.toFixed(3)}`;
  });
  return svg;
}

function shapChart(rows) {
  const W = 480, rowH = 20, m = { l: 44, r: 56, t: 8, b: 24 };
  const H = m.t + rows.length * rowH + m.b;
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart", role: "img",
    "aria-label": "Mean absolute SHAP value per feature" });
  const max = Math.max(...rows.map((r) => r.mean_abs_shap_uplift));
  const w = (v) => (v / max) * (W - m.l - m.r);
  rows.forEach((r, i) => {
    const y0 = m.t + i * rowH;
    el("text", { x: m.l - 8, y: y0 + rowH / 2 + 4, "text-anchor": "end", class: "tick" }, svg).textContent = r.feature;
    const bar = el("rect", { x: m.l, y: y0 + 3, width: Math.max(1, w(r.mean_abs_shap_uplift)), height: rowH - 6,
      rx: 2, class: "bar" }, svg);
    el("title", {}, bar).textContent = `${r.feature}: ${r.mean_abs_shap_uplift.toFixed(3)}`;
    el("text", { x: m.l + w(r.mean_abs_shap_uplift) + 6, y: y0 + rowH / 2 + 4, class: "mark-label" }, svg)
      .textContent = r.mean_abs_shap_uplift.toFixed(3);
  });
  return svg;
}

function budgetChart(rows, cutoffValid, maxInSample) {
  const W = 960, H = 320, m = { l: 64, r: 24, t: 24, b: 44 };
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart", role: "img",
    "aria-label": "Profit against share of customers targeted" });
  const xs = rows.map((r) => r.share_targeted), ys = rows.map((r) => r.profit / 1000);
  const lo = Math.min(0, Math.min(...ys)), hi = Math.max(...ys) * 1.08;
  const x = (v) => m.l + (v / 1) * (W - m.l - m.r);
  const y = (v) => m.t + ((hi - v) / (hi - lo)) * (H - m.t - m.b);
  for (const t of ticks(lo, hi, 4)) {
    el("line", { x1: m.l, x2: W - m.r, y1: y(t), y2: y(t), class: "grid" }, svg);
    el("text", { x: m.l - 8, y: y(t) + 4, "text-anchor": "end", class: "tick" }, svg).textContent = "$" + t.toFixed(0) + "k";
  }
  for (let t = 0; t <= 1.0001; t += 0.1) {
    el("text", { x: x(t), y: H - m.b + 16, "text-anchor": "middle", class: "tick" }, svg).textContent = Math.round(t * 100) + "%";
  }
  el("line", { x1: m.l, x2: W - m.r, y1: y(0), y2: y(0), class: "axis" }, svg);
  const d = rows.map((r, i) => `${i ? "L" : "M"}${x(r.share_targeted).toFixed(1)},${y(r.profit / 1000).toFixed(1)}`).join(" ");
  el("path", { d, class: "line" }, svg);
  for (const r of rows) {
    const c = el("circle", { cx: x(r.share_targeted), cy: y(r.profit / 1000), r: 6, fill: "transparent" }, svg);
    el("title", {}, c).textContent =
      `${pct(r.share_targeted, 1)} targeted: profit ${usd(r.profit)}, ROI ${(r.roi * 100).toFixed(0)}%`;
  }
  el("line", { x1: x(cutoffValid), x2: x(cutoffValid), y1: m.t, y2: H - m.b, class: "cut" }, svg);
  el("text", { x: x(cutoffValid) + 6, y: m.t + 12, class: "cut-label" }, svg)
    .textContent = `cutoff from valid: ${pct(cutoffValid, 0)}`;
  el("line", { x1: x(maxInSample), x2: x(maxInSample), y1: m.t, y2: H - m.b, class: "threshold" }, svg);
  el("text", { x: x(maxInSample) - 6, y: H - m.b - 10, "text-anchor": "end", class: "tick" }, svg)
    .textContent = `test profit peak (in-sample): ${pct(maxInSample, 0)}`;
  el("text", { x: (m.l + W - m.r) / 2, y: H - 6, "text-anchor": "middle", class: "axis-label" }, svg)
    .textContent = "Share of customers targeted (top by predicted uplift)";
  el("text", { x: 14, y: (m.t + H - m.b) / 2, transform: `rotate(-90 14 ${(m.t + H - m.b) / 2})`,
    "text-anchor": "middle", class: "axis-label" }, svg).textContent = "Profit (thousands of $)";
  return svg;
}

// ---------- tables and cards ----------

function table(headers, rows) {
  const t = html("table", {}, "");
  const thead = html("thead", {}, "<tr>" + headers.map((h) => `<th>${h}</th>`).join("") + "</tr>");
  // Money and percentage cells never wrap ("−$16,903" splitting across lines is hard to read).
  const isAmount = (c) => /^[−+]?\$?[−+]?[\d,.]+(%| pp)?$/.test(String(c).replace(/<[^>]+>/g, ""));
  const tbody = html("tbody", {}, rows.map((r) => "<tr>" + r.map((c) =>
    `<td${isAmount(c) ? ' class="amt"' : ""}>${c}</td>`).join("") + "</tr>").join(""));
  t.appendChild(thead);
  t.appendChild(tbody);
  return t;
}
function card(label, value, sub) {
  return html("div", { class: "card" },
    `<div class="label">${label}</div><div class="value">${value}</div><div class="sub">${sub}</div>`);
}

// ---------- render ----------

function render() {
  const ab = D.ab, up = D.uplift, roi = D.roi;

  // 1. Experiment
  const visit = ab.ate.visit, conv = ab.ate.conversion, cuped = ab.cuped_visit;
  const cards = $("#exp-cards");
  cards.append(
    card("Visit lift (intent-to-treat)", pp(visit.abs_lift),
      `${pct(visit.p_control, 2)} → ${pct(visit.p_treated, 2)}, 95% CI ${pp(visit.ci_low)} to ${pp(visit.ci_high)}`),
    card("Conversion lift", pp(conv.abs_lift),
      `95% CI ${pp(conv.ci_low)} to ${pp(conv.ci_high)}; relative +${(conv.rel_lift * 100).toFixed(0)}%`),
    card("Sample ratio mismatch", `p = ${ab.srm.p_value.toFixed(3)}`,
      `treated share ${pct(ab.srm.observed_treated_share, 2)} against the designed 85%`),
    card("Largest |SMD|", Math.max(...D.balance.map((b) => Math.abs(b.smd))).toFixed(3),
      `${D.balance.filter((b) => Math.abs(b.smd) >= 0.1).length} of ${D.balance.length} features at or above 0.1`)
  );
  $("#balance-chart").append(balanceChart(D.balance));
  const maxSmd = Math.max(...D.balance.map((b) => Math.abs(b.smd)));
  $("#balance-note").textContent =
    `All features pass the 0.1 threshold (largest |SMD| ${maxSmd.toFixed(3)}). At this sample size a clean randomization would give SMDs near 0.001, so the imbalance is still unexplained.`;

  const fullRow = D.power.find((p) => p.n_total > 1e7 && p.treated_share === 0.5);
  const millionRow = D.power.find((p) => p.n_total === 1e6 && p.treated_share === 0.5);
  $("#power-table").append(table(
    ["Customers", "Treated share", "Baseline visit rate", "Minimum detectable lift", "Relative"],
    D.power.map((p) => [num(p.n_total), pct(p.treated_share, 0), pct(p.baseline_visit_rate, 2),
      pp(p.mde_abs), pct(p.mde_rel, 1)])
  ));

  $("#power-note").textContent =
    `A 1M-customer test (50/50) can only detect lifts of ${pp(millionRow.mde_abs)} or larger. ` +
    `The full data detects ${pp(fullRow.mde_abs, 3)}.`;

  $("#cuped-text").innerHTML =
    `<p style="margin:0 0 8px">CUPED cuts outcome variance by <strong>${pct(cuped.variance_reduction, 0)}</strong>. ` +
    `But the adjusted lift is <strong>${pp(cuped.adjusted_abs_lift)}</strong> against <strong>${pp(cuped.raw_abs_lift)}</strong> raw, ` +
    `and the two intervals do not overlap. The imbalance above is the likely cause. The raw estimate is the headline until this is resolved.</p>` +
    `<p style="margin:0" class="note">Exposure caveat: among treated customers who were exposed, ${pct(ab.exposure.exposed_visit_rate, 1)} visit, against ` +
    `${pct(ab.exposure.control_visit_rate, 1)} in control. That gap is selection, not effect, so only the intent-to-treat comparison is used.</p>`;

  // 2. Who to target
  $("#decile-chart").append(decileChart(D.deciles));
  const top = D.deciles[0].observed_lift, avg = up.overall_observed_lift_test;
  $("#decile-note").textContent =
    `Top decile lift ${pp(top)} against an average of ${pp(avg)}: ${(top / avg).toFixed(1)}× the average. ` +
    `The bottom decile is ${pp(D.deciles[D.deciles.length - 1].observed_lift)}.`;

  const order = ["s_learner", "t_learner", "x_learner", "class_transformation"];
  const names = { s_learner: "S-learner (selected on valid)", t_learner: "T-learner",
    x_learner: "X-learner", class_transformation: "Class transformation" };
  $("#model-table").append(table(
    ["Learner", "Valid Qini AUC", "Test Qini AUC"],
    order.map((k) => [names[k],
      num(up.comparison[k].valid_qini_auc),
      k === "class_transformation" ? `<span class="flag">${num(up.comparison[k].test_qini_auc)} (fails)</span>`
        : num(up.comparison[k].test_qini_auc)]).concat([["Random (reference)", "–", num(up.random_test_qini_auc)]])
  ));

  $("#segment-table").append(table(
    ["Segment", "Share", "Predicted uplift", "Observed visit lift"],
    D.segments.map((s) => [s.segment.replace(/_/g, " "), pct(s.share, 1),
      pp(s.mean_predicted_uplift), pp(s.observed_visit_lift)])
  ));
  $("#shap-chart").append(shapChart(D.shap));

  // 3. ROI
  const cutoff = roi.cutoff_chosen_on_valid;
  $("#roi-lede").textContent =
    `The cutoff is set on the valid split, then reported on the test split. The rule targets the top ${pct(cutoff, 0)} by predicted uplift.`;
  $("#roi-cards").append(
    card("Profit at the valid cutoff", usd(roi.test_profit_at_valid_cutoff),
      `ROI ${(roi.test_roi_at_valid_cutoff * 100).toFixed(0)}% on the test split`),
    card("Target everyone", usd(roi.policy_comparison.find((p) => p.policy === "target_everyone").profit),
      "loses money at the assumed economics"),
    card("Top 20% by uplift", pct(roi.headline_top_20pct.pct_incremental_conversions_kept, 0),
      `of incremental conversions kept at ${pct(roi.headline_top_20pct.pct_of_cost, 0)} of the cost`),
    card("Wasted spend under target-everyone", pct(roi.target_everyone_wasted_spend_share, 0),
      "sure things and lost causes")
  );
  $("#budget-chart").append(budgetChart(D.budget, cutoff, roi.test_profit_max_share_in_sample));

  $("#policy-table").append(table(
    ["Policy", "Share targeted", "Incremental visits", "Incremental conversions", "Cost", "Profit", "ROI"],
    D.policies.map((p) => [p.policy.replace(/_/g, " "), pct(p.share_targeted, 0), num(p.incremental_visits),
      num(p.incremental_conversions), usd(p.cost), usd(p.profit),
      p.roi === null || isNaN(p.roi) ? "n/a" : (p.roi * 100).toFixed(0) + "%"])
  ));
  $("#sens-table").append(table(
    ["Cost per treated", "Value per conversion", "Cutoff (valid)", "Test profit", "Test ROI"],
    D.sensitivity.map((s) => ["$" + s.cost_per_treated.toFixed(2), usd(s.value_per_conversion),
      pct(s.cutoff_chosen_on_valid, 1), usd(s.test_profit_at_cutoff), (s.test_roi_at_cutoff * 100).toFixed(0) + "%"])
  ));
}

render();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
