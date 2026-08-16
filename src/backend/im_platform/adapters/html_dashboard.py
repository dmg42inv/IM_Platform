"""Generates a single self-contained HTML dashboard from the V1 Output Pack
data (Portfolio_Snapshot, Returns_Summary, Pipeline_and_Lifecycle,
Data_Quality_Exceptions). No build step, no server - open the file directly
in a browser. Charts use Chart.js from a CDN; everything else is vanilla
HTML/CSS/JS so the file stays a single artifact.
"""

from __future__ import annotations

import json
from datetime import date

import pandas as pd


def _records(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> JSON-safe list of dicts (NaN/NaT -> None)."""
    if df is None or len(df) == 0:
        return []
    clean = df.astype(object).where(pd.notnull(df), None)
    return clean.to_dict("records")


def build_dashboard_html(
    snapshot: pd.DataFrame,
    returns: pd.DataFrame,
    pipeline_lifecycle: pd.DataFrame,
    issues: pd.DataFrame,
    as_of_date: str | None = None,
) -> str:
    as_of_date = as_of_date or date.today().isoformat()

    positions = snapshot.merge(
        returns[["investment_id", "PaidIn", "Distributed", "ResidualValue", "TVPI", "DPI", "MOIC", "IRR"]],
        on="investment_id",
        how="left",
    )

    total_invested = float(snapshot["invested_cost_base"].sum()) if len(snapshot) else 0.0
    total_fv = float(snapshot["latest_fair_value_base"].sum()) if len(snapshot) else 0.0
    total_unrealized = float(snapshot["unrealized_gain_loss_base"].sum()) if len(snapshot) else 0.0
    live_count = int((snapshot["lifecycle_state"] == "Live").sum()) if len(snapshot) else 0

    lifecycle_row = pipeline_lifecycle.iloc[0].to_dict() if len(pipeline_lifecycle) else {}

    top_movers = returns.dropna(subset=["TVPI"]).sort_values("TVPI", ascending=False).head(10) if len(returns) else pd.DataFrame()
    bottom_movers = returns.dropna(subset=["TVPI"]).sort_values("TVPI", ascending=True).head(10) if len(returns) else pd.DataFrame()

    data = {
        "as_of_date": as_of_date,
        "generated": date.today().isoformat(),
        "kpis": {
            "total_invested": total_invested,
            "total_fair_value": total_fv,
            "total_unrealized": total_unrealized,
            "live_count": live_count,
            "total_count": int(len(snapshot)),
        },
        "lifecycle": lifecycle_row,
        "positions": _records(positions),
        "top_movers": _records(top_movers[["investment_id", "TVPI", "DPI", "PaidIn"]]) if len(top_movers) else [],
        "bottom_movers": _records(bottom_movers[["investment_id", "TVPI", "DPI", "PaidIn"]]) if len(bottom_movers) else [],
        "issues": _records(issues),
    }
    data_json = json.dumps(data, default=str)

    return _HTML_TEMPLATE.replace("__DATA_JSON__", data_json)


_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>IM Platform - V1 Portfolio Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
  :root {
    --bg: #0f172a; --panel: #1e293b; --panel-2: #16213a; --text: #e2e8f0; --muted: #94a3b8;
    --accent: #38bdf8; --green: #4ade80; --red: #f87171; --border: #334155;
  }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif; background: var(--bg); color: var(--text); overflow-x: hidden; }
  header { padding: 20px 28px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; }
  header h1 { font-size: 18px; margin: 0; font-weight: 600; }
  header .meta { color: var(--muted); font-size: 12px; }
  nav { display: flex; gap: 4px; padding: 0 28px; border-bottom: 1px solid var(--border); }
  nav button { background: none; border: none; color: var(--muted); padding: 12px 16px; cursor: pointer; font-size: 13px; border-bottom: 2px solid transparent; }
  nav button.active { color: var(--accent); border-bottom-color: var(--accent); }
  main { padding: 24px 28px; }
  .tab { display: none; }
  .tab.active { display: block; }
  .kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin-bottom: 24px; }
  .kpi-card { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }
  .kpi-card .label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.03em; }
  .kpi-card .value { font-size: 22px; font-weight: 600; margin-top: 6px; }
  .pos { color: var(--green); } .neg { color: var(--red); }
  .panel { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 18px; margin-bottom: 20px; }
  .panel h2 { font-size: 14px; margin: 0 0 14px 0; color: var(--muted); text-transform: uppercase; letter-spacing: 0.03em; }
  .chart-row { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
  .chart-box { position: relative; height: 320px; }
  @media (max-width: 900px) { .chart-row { grid-template-columns: 1fr; } }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { padding: 8px 10px; text-align: right; border-bottom: 1px solid var(--border); white-space: nowrap; }
  th:first-child, td:first-child { text-align: left; }
  th { color: var(--muted); font-weight: 500; cursor: pointer; user-select: none; position: sticky; top: 0; background: var(--panel); }
  th:hover { color: var(--accent); }
  tbody tr:hover { background: var(--panel-2); }
  input.filter { background: var(--panel-2); border: 1px solid var(--border); color: var(--text); padding: 8px 10px; border-radius: 6px; font-size: 13px; width: 260px; margin-bottom: 12px; }
  .table-wrap { max-height: 560px; overflow: auto; }
  .badge { padding: 2px 8px; border-radius: 10px; font-size: 11px; }
  .badge.Live { background: #14532d; color: #86efac; }
  .badge.Exited { background: #1e3a5f; color: #93c5fd; }
  .badge.PartiallyExited { background: #713f12; color: #fde68a; }
</style>
</head>
<body>

<header>
  <h1>IM Platform &mdash; V1 Portfolio Dashboard</h1>
  <div class="meta">As-of <span id="asOfDate"></span> &middot; Generated <span id="genDate"></span></div>
</header>

<nav>
  <button class="tab-btn active" data-tab="overview">Overview</button>
  <button class="tab-btn" data-tab="positions">Positions</button>
  <button class="tab-btn" data-tab="returns">Returns</button>
  <button class="tab-btn" data-tab="lifecycle">Pipeline &amp; Lifecycle</button>
  <button class="tab-btn" data-tab="quality">Data Quality</button>
</nav>

<main>

  <section id="overview" class="tab active">
    <div class="kpi-grid">
      <div class="kpi-card"><div class="label">Total Invested (USD)</div><div class="value" id="kpiInvested"></div></div>
      <div class="kpi-card"><div class="label">Total Fair Value (USD)</div><div class="value" id="kpiFairValue"></div></div>
      <div class="kpi-card"><div class="label">Unrealized Gain/(Loss)</div><div class="value" id="kpiUnrealized"></div></div>
      <div class="kpi-card"><div class="label">Live Positions</div><div class="value" id="kpiLive"></div></div>
    </div>
    <div class="chart-row">
      <div class="panel"><h2>Top 10 by Fair Value</h2><div class="chart-box"><canvas id="chartTopFv"></canvas></div></div>
      <div class="panel"><h2>Lifecycle Distribution</h2><div class="chart-box"><canvas id="chartLifecycle"></canvas></div></div>
    </div>
  </section>

  <section id="positions" class="tab">
    <div class="panel">
      <h2>Portfolio Snapshot</h2>
      <input class="filter" id="positionsFilter" placeholder="Filter by name...">
      <div class="table-wrap"><table id="positionsTable"></table></div>
    </div>
  </section>

  <section id="returns" class="tab">
    <div class="chart-row">
      <div class="panel"><h2>Top 10 by TVPI</h2><div class="chart-box"><canvas id="chartTopTvpi"></canvas></div></div>
      <div class="panel"><h2>Bottom 10 by TVPI</h2><div class="chart-box"><canvas id="chartBottomTvpi"></canvas></div></div>
    </div>
    <div class="panel">
      <h2>Returns Summary</h2>
      <input class="filter" id="returnsFilter" placeholder="Filter by name...">
      <div class="table-wrap"><table id="returnsTable"></table></div>
    </div>
  </section>

  <section id="lifecycle" class="tab">
    <div class="panel">
      <h2>Pipeline &amp; Lifecycle Counts</h2>
      <div class="table-wrap"><table id="lifecycleTable"></table></div>
    </div>
  </section>

  <section id="quality" class="tab">
    <div class="panel">
      <h2>Data Quality Exceptions</h2>
      <div class="table-wrap"><table id="qualityTable"></table></div>
    </div>
  </section>

</main>

<script>
const DATA = __DATA_JSON__;

function fmtUsd(v) {
  if (v === null || v === undefined || v === "") return "";
  const n = Number(v);
  if (Number.isNaN(n)) return v;
  return n.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 });
}
function fmtNum(v, digits) {
  if (v === null || v === undefined || v === "") return "";
  const n = Number(v);
  if (Number.isNaN(n)) return v;
  return n.toFixed(digits === undefined ? 2 : digits);
}
function fmtX(v) {
  if (v === null || v === undefined || v === "") return "";
  const n = Number(v);
  if (Number.isNaN(n)) return v;
  return n.toFixed(2) + "x";
}

document.getElementById("asOfDate").textContent = DATA.as_of_date;
document.getElementById("genDate").textContent = DATA.generated;
document.getElementById("kpiInvested").textContent = fmtUsd(DATA.kpis.total_invested);
document.getElementById("kpiFairValue").textContent = fmtUsd(DATA.kpis.total_fair_value);
const kpiUnrealizedEl = document.getElementById("kpiUnrealized");
kpiUnrealizedEl.textContent = fmtUsd(DATA.kpis.total_unrealized);
kpiUnrealizedEl.className = "value " + (DATA.kpis.total_unrealized >= 0 ? "pos" : "neg");
document.getElementById("kpiLive").textContent = DATA.kpis.live_count + " / " + DATA.kpis.total_count;

// Tabs
document.querySelectorAll(".tab-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(btn.dataset.tab).classList.add("active");
  });
});

// Generic sortable/filterable table renderer
function renderTable(el, rows, columns, filterInputEl) {
  let sortCol = null, sortDir = 1;
  function draw(data) {
    let html = "<thead><tr>";
    columns.forEach(c => html += `<th data-key="${c.key}">${c.label}</th>`);
    html += "</tr></thead><tbody>";
    data.forEach(row => {
      html += "<tr>";
      columns.forEach(c => {
        let v = row[c.key];
        let display = c.fmt ? c.fmt(v) : (v === null || v === undefined ? "" : v);
        if (c.key === "lifecycle_state" && v) {
          display = `<span class="badge ${v}">${v}</span>`;
        }
        html += `<td>${display}</td>`;
      });
      html += "</tr>";
    });
    html += "</tbody>";
    el.innerHTML = html;
    el.querySelectorAll("th").forEach(th => {
      th.addEventListener("click", () => {
        const key = th.dataset.key;
        sortDir = (sortCol === key) ? -sortDir : 1;
        sortCol = key;
        const sorted = [...data].sort((a, b) => {
          let av = a[key], bv = b[key];
          if (av === null || av === undefined) av = -Infinity;
          if (bv === null || bv === undefined) bv = -Infinity;
          if (typeof av === "string" || typeof bv === "string") {
            return String(av).localeCompare(String(bv)) * sortDir;
          }
          return (av - bv) * sortDir;
        });
        draw(sorted);
      });
    });
  }
  draw(rows);
  if (filterInputEl) {
    filterInputEl.addEventListener("input", () => {
      const q = filterInputEl.value.toLowerCase();
      const filtered = rows.filter(r => JSON.stringify(r).toLowerCase().includes(q));
      draw(filtered);
    });
  }
}

renderTable(document.getElementById("positionsTable"), DATA.positions, [
  { key: "investment_id", label: "Investment" },
  { key: "company_name", label: "Entity" },
  { key: "fund_vehicle", label: "Fund Vehicle" },
  { key: "instrument_type", label: "Type" },
  { key: "lifecycle_state", label: "Status" },
  { key: "invested_cost_base", label: "Invested (USD)", fmt: fmtUsd },
  { key: "latest_fair_value_base", label: "Fair Value (USD)", fmt: fmtUsd },
  { key: "unrealized_gain_loss_base", label: "Unrealized G/L", fmt: fmtUsd },
  { key: "TVPI", label: "TVPI", fmt: fmtX },
  { key: "IRR", label: "IRR", fmt: v => v === null ? "" : (Number(v) * 100).toFixed(1) + "%" },
], document.getElementById("positionsFilter"));

renderTable(document.getElementById("returnsTable"), DATA.positions, [
  { key: "investment_id", label: "Investment" },
  { key: "PaidIn", label: "Paid In", fmt: fmtUsd },
  { key: "Distributed", label: "Distributed", fmt: fmtUsd },
  { key: "ResidualValue", label: "Residual Value", fmt: fmtUsd },
  { key: "TVPI", label: "TVPI", fmt: fmtX },
  { key: "DPI", label: "DPI", fmt: fmtX },
  { key: "MOIC", label: "MOIC", fmt: fmtX },
  { key: "IRR", label: "IRR", fmt: v => v === null ? "" : (Number(v) * 100).toFixed(1) + "%" },
], document.getElementById("returnsFilter"));

renderTable(document.getElementById("lifecycleTable"), [DATA.lifecycle], Object.keys(DATA.lifecycle || {}).map(k => ({ key: k, label: k })));

renderTable(document.getElementById("qualityTable"), DATA.issues, [
  { key: "dataset_name", label: "Dataset" },
  { key: "record_key", label: "Record" },
  { key: "issue_type", label: "Issue Type" },
  { key: "issue_description", label: "Description" },
  { key: "severity", label: "Severity" },
]);
if (DATA.issues.length === 0) {
  document.getElementById("qualityTable").innerHTML = "<tbody><tr><td style='text-align:left;color:#94a3b8;'>No data quality exceptions in this run.</td></tr></tbody>";
}

// Charts
const topFv = [...DATA.positions].filter(p => p.latest_fair_value_base != null).sort((a, b) => b.latest_fair_value_base - a.latest_fair_value_base).slice(0, 10);
new Chart(document.getElementById("chartTopFv"), {
  type: "bar",
  data: {
    labels: topFv.map(p => p.investment_id),
    datasets: [{ label: "Fair Value (USD)", data: topFv.map(p => p.latest_fair_value_base), backgroundColor: "#38bdf8" }]
  },
  options: { responsive: true, maintainAspectRatio: false, indexAxis: "y", plugins: { legend: { display: false } }, scales: { x: { ticks: { color: "#94a3b8" } }, y: { ticks: { color: "#e2e8f0" } } } }
});

const lc = DATA.lifecycle || {};
const lcLabels = ["sourced_count", "approved_count", "live_count", "partially_exited_count", "exited_count", "dropped_count"];
new Chart(document.getElementById("chartLifecycle"), {
  type: "doughnut",
  data: {
    labels: lcLabels.map(k => k.replace("_count", "")),
    datasets: [{ data: lcLabels.map(k => lc[k] || 0), backgroundColor: ["#64748b", "#38bdf8", "#4ade80", "#fbbf24", "#93c5fd", "#f87171"] }]
  },
  options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { labels: { color: "#e2e8f0" } } } }
});

new Chart(document.getElementById("chartTopTvpi"), {
  type: "bar",
  data: {
    labels: DATA.top_movers.map(p => p.investment_id),
    datasets: [{ label: "TVPI", data: DATA.top_movers.map(p => p.TVPI), backgroundColor: "#4ade80" }]
  },
  options: { responsive: true, maintainAspectRatio: false, indexAxis: "y", plugins: { legend: { display: false } }, scales: { x: { ticks: { color: "#94a3b8" } }, y: { ticks: { color: "#e2e8f0" } } } }
});
new Chart(document.getElementById("chartBottomTvpi"), {
  type: "bar",
  data: {
    labels: DATA.bottom_movers.map(p => p.investment_id),
    datasets: [{ label: "TVPI", data: DATA.bottom_movers.map(p => p.TVPI), backgroundColor: "#f87171" }]
  },
  options: { responsive: true, maintainAspectRatio: false, indexAxis: "y", plugins: { legend: { display: false } }, scales: { x: { ticks: { color: "#94a3b8" } }, y: { ticks: { color: "#e2e8f0" } } } }
});
</script>

</body>
</html>
"""
