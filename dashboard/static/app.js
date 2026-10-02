/* Read-only dashboard client: polls /api/dashboard and renders. It never sends anything but GET requests. */
"use strict";

const state = { tab: "overview", tradeFilter: "all", data: null, lastOk: null, refreshMs: 3000 };
const $ = (id) => document.getElementById(id);
const NA = '<span class="na">N/A</span>';

// ---------------------------------------------------------------------------------------------- format
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const isNum = (v) => typeof v === "number" && isFinite(v);
function money(v, signed = false) {
  if (!isNum(v)) return NA;
  const s = Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return (v < 0 ? "−$" : signed && v > 0 ? "+$" : "$") + s;
}
function price(v) {
  if (!isNum(v)) return NA;
  const d = Math.abs(v) >= 100 ? 2 : Math.abs(v) >= 1 ? 4 : 6;
  return "$" + v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
}
function pct(v, signed = true, d = 2) {
  if (!isNum(v)) return NA;
  return (v > 0 && signed ? "+" : v < 0 ? "−" : "") + Math.abs(v * 100).toFixed(d) + "%";
}
const qty = (v) => (isNum(v) ? v.toLocaleString("en-US", { maximumSignificantDigits: 6 }) : NA);
const cls = (v) => (!isNum(v) ? "na" : v > 0 ? "pos" : v < 0 ? "neg" : "");
const signed = (v, f) => `<span class="${cls(v)}">${f(v)}</span>`;
const tm = (v) => (v ? `<span class="nowrap">${esc(String(v).replace(/:00 UTC$/, "").replace(/ UTC$/, ""))}</span>` : NA);
const txt = (v) => (v === null || v === undefined || v === "" ? NA : esc(v));
const yes = (v) => (v === true ? "yes" : v === false ? "no" : NA);
const sideBadge = (s) => (s ? `<span class="badge ${esc(s)}">${esc(s.toUpperCase())}</span>` : NA);

// ------------------------------------------------------------------------------------------------ charts
const tip = $("tooltip");
function showTip(e, html) { tip.innerHTML = html; tip.classList.remove("hidden");
  const x = Math.min(e.clientX + 14, window.innerWidth - tip.offsetWidth - 8); tip.style.left = x + "px"; tip.style.top = (e.clientY + 14) + "px"; }
function hideTip() { tip.classList.add("hidden"); }

function emptyChart(el, msg) { el.innerHTML = `<div class="empty">${esc(msg)}</div>`; }

function lineChart(el, pts, opts = {}) {
  if (!pts || pts.length < 2) return emptyChart(el, "N/A – not enough data recorded yet");
  const W = el.clientWidth || 600, H = el.clientHeight || 240, m = { l: 62, r: 12, t: 10, b: 26 };
  const xs = pts.map((p) => Date.parse(p[0].replace(" UTC", "Z").replace(" ", "T")));
  const ys = pts.map((p) => p[1]);
  let lo = Math.min(...ys, opts.zero ? 0 : Infinity), hi = Math.max(...ys, opts.zero ? 0 : -Infinity);
  if (hi === lo) { hi += Math.abs(hi) * 0.01 || 1; lo -= Math.abs(lo) * 0.01 || 1; }
  const pad = (hi - lo) * 0.08; lo -= pad; hi += pad;
  const X = (t) => m.l + ((t - xs[0]) / Math.max(xs[xs.length - 1] - xs[0], 1)) * (W - m.l - m.r);
  const Y = (v) => m.t + ((hi - v) / (hi - lo)) * (H - m.t - m.b);
  const color = opts.color || "var(--series-1)";
  let g = "";
  for (let i = 0; i <= 4; i++) {
    const v = lo + ((hi - lo) * i) / 4, y = Y(v);
    g += `<line x1="${m.l}" x2="${W - m.r}" y1="${y}" y2="${y}" stroke="var(--grid)"/>` +
      `<text class="axis-label" x="${m.l - 8}" y="${y + 4}" text-anchor="end">${esc(opts.axis ? opts.axis(v) : v.toFixed(2))}</text>`;
  }
  const t0 = new Date(xs[0]), t1 = new Date(xs[xs.length - 1]);
  const fmtD = (d) => d.toISOString().slice(5, 16).replace("T", " ");
  g += `<text class="axis-label" x="${m.l}" y="${H - 6}">${fmtD(t0)}</text><text class="axis-label" x="${W - m.r}" y="${H - 6}" text-anchor="end">${fmtD(t1)} UTC</text>`;
  const path = pts.map((p, i) => `${i ? "L" : "M"}${X(xs[i]).toFixed(1)},${Y(ys[i]).toFixed(1)}`).join("");
  let area = "";
  if (opts.fill) area = `<path d="${path}L${X(xs[xs.length - 1])},${Y(Math.max(lo, Math.min(0, hi)))}L${X(xs[0])},${Y(Math.max(lo, Math.min(0, hi)))}Z" fill="${opts.fill}" opacity="0.25"/>`;
  if (opts.zero && lo < 0 && hi > 0) g += `<line x1="${m.l}" x2="${W - m.r}" y1="${Y(0)}" y2="${Y(0)}" stroke="var(--axis)"/>`;
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">${g}${area}<path d="${path}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round"/>` +
    `<line class="xh" x1="0" x2="0" y1="${m.t}" y2="${H - m.b}" stroke="var(--muted)" stroke-dasharray="3 3" visibility="hidden"/>` +
    `<circle class="xd" r="4" fill="${color}" stroke="var(--surface)" stroke-width="2" visibility="hidden"/>` +
    `<rect x="${m.l}" y="0" width="${W - m.l - m.r}" height="${H}" fill="transparent" class="hit"/></svg>`;
  const svg = el.querySelector("svg"), xh = svg.querySelector(".xh"), xd = svg.querySelector(".xd");
  svg.querySelector(".hit").addEventListener("mousemove", (e) => {
    const r = svg.getBoundingClientRect(), px = ((e.clientX - r.left) / r.width) * W;
    let best = 0, bd = Infinity;
    xs.forEach((t, i) => { const d = Math.abs(X(t) - px); if (d < bd) { bd = d; best = i; } });
    xh.setAttribute("x1", X(xs[best])); xh.setAttribute("x2", X(xs[best])); xh.setAttribute("visibility", "visible");
    xd.setAttribute("cx", X(xs[best])); xd.setAttribute("cy", Y(ys[best])); xd.setAttribute("visibility", "visible");
    showTip(e, `${esc(pts[best][0])}<br><b>${opts.tipf ? opts.tipf(ys[best]) : ys[best]}</b>`);
  });
  svg.querySelector(".hit").addEventListener("mouseleave", () => { hideTip(); xh.setAttribute("visibility", "hidden"); xd.setAttribute("visibility", "hidden"); });
}

function barChart(el, rows, opts = {}) {
  if (!rows || !rows.length) return emptyChart(el, "N/A – no completed days recorded yet");
  const W = el.clientWidth || 600, H = el.clientHeight || 240, m = { l: 62, r: 12, t: 10, b: 26 };
  const vals = rows.map((r) => r.v);
  let lo = Math.min(0, ...vals), hi = Math.max(0, ...vals);
  if (hi === lo) hi = lo + 1;
  const pad = (hi - lo) * 0.08; hi += hi > 0 ? pad : 0; lo -= lo < 0 ? pad : 0;
  const Y = (v) => m.t + ((hi - v) / (hi - lo)) * (H - m.t - m.b);
  const bw = (W - m.l - m.r) / rows.length, gap = Math.min(4, bw * 0.2);
  let g = "";
  for (let i = 0; i <= 4; i++) {
    const v = lo + ((hi - lo) * i) / 4, y = Y(v);
    g += `<line x1="${m.l}" x2="${W - m.r}" y1="${y}" y2="${y}" stroke="var(--grid)"/><text class="axis-label" x="${m.l - 8}" y="${y + 4}" text-anchor="end">${esc(opts.axis(v))}</text>`;
  }
  g += `<line x1="${m.l}" x2="${W - m.r}" y1="${Y(0)}" y2="${Y(0)}" stroke="var(--axis)"/>`;
  rows.forEach((r, i) => {
    const x = m.l + i * bw + gap / 2, y0 = Y(0), y1 = Y(r.v), h = Math.max(Math.abs(y1 - y0), 1);
    const color = r.v >= 0 ? "var(--pos)" : "var(--neg)";
    g += `<rect class="bar" data-i="${i}" x="${x}" y="${Math.min(y0, y1)}" width="${Math.max(bw - gap, 1)}" height="${h}" rx="${Math.min(4, (bw - gap) / 2)}" fill="${color}"/>`;
  });
  if (rows.length <= 14) rows.forEach((r, i) => { g += `<text class="axis-label" x="${m.l + i * bw + bw / 2}" y="${H - 6}" text-anchor="middle">${esc(r.label.slice(5))}</text>`; });
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">${g}</svg>`;
  el.querySelectorAll(".bar").forEach((b) => {
    b.addEventListener("mousemove", (e) => { const r = rows[+b.dataset.i]; showTip(e, `${esc(r.label)}<br><b>${opts.tipf(r)}</b>`); });
    b.addEventListener("mouseleave", hideTip);
  });
}

// ---------------------------------------------------------------------------------------------- render
function kpi(label, value, sub = "", small = false) { return `<div class="kpi"><div class="label">${esc(label)}</div><div class="value${small ? " small" : ""}">${value}</div>${sub ? `<div class="sub">${sub}</div>` : ""}</div>`; }
function table(cols, rows, empty) {
  if (!rows.length) return `<div class="empty">${esc(empty)}</div>`;
  return `<table><thead><tr>${cols.map((c) => `<th class="${c.num ? "num" : ""}">${esc(c.h)}</th>`).join("")}</tr></thead><tbody>` +
    rows.map((r) => `<tr>${cols.map((c) => `<td class="${c.num ? "num" : ""} ${c.cls || ""}">${c.f(r)}</td>`).join("")}</tr>`).join("") + "</tbody></table>";
}
function botBadge(b) {
  const k = { RUNNING: "run", STALE: "stale", STOPPED: "stop" }[b?.state] || "stale";
  return `<span class="badge ${k}">${esc(b?.state || "N/A")}</span>`;
}

function renderOverview(d) {
  const o = d.overview;
  $("kpis").innerHTML = [
    kpi("Paper account balance (equity)", money(o.equity), `starting balance ${money(o.start_equity)}`),
    kpi("Total P&L", signed(o.total_pnl, (v) => money(v, true)), signed(o.total_pnl_pct, pct)),
    kpi("Today's P&L (UTC)", signed(o.today_pnl, (v) => money(v, true)), signed(o.today_pnl_pct, pct)),
    kpi("This month's P&L", signed(o.month_pnl, (v) => money(v, true)), signed(o.month_pnl_pct, pct)),
    kpi("Available cash", money(o.cash), "not committed to positions"),
    kpi("Invested capital", money(o.invested_capital), "entry notional of open positions"),
    kpi("Gross exposure", money(o.gross_exposure), `${pct(o.gross_exposure_pct, false, 1)} of equity (max 100%)`),
    kpi("Open positions / closed trades", `${o.open_positions} / ${o.closed_trades}`),
    kpi("Current drawdown", signed(o.current_drawdown, pct), "from equity peak"),
    kpi("Bot status", botBadge(o.bot_status), esc(o.bot_status?.detail || "")),
    kpi("Last market-data update", txt(o.last_market_data_update), "", true),
    kpi("Next strategy decision", txt(o.next_decision), "", true),
    kpi("Data error count", `<span class="${o.error_count ? "neg" : ""}">${txt(o.error_count)}</span>`),
  ].join("");
  $("eq-note").textContent = o.start_equity_source ? `start: ${o.start_equity_source}` : "";
  lineChart($("ov-equity"), d.performance.equity_curve, { axis: (v) => "$" + v.toFixed(2), tipf: (v) => money(v) });
  $("pnl-breakdown").innerHTML = `<dl class="kv">
    <dt>Realized P&amp;L (closed trades, net of fees)</dt><dd>${signed(o.realized_pnl, (v) => money(v, true))}</dd>
    <dt>Unrealized P&amp;L (open, before exit costs)</dt><dd>${signed(o.unrealized_pnl, (v) => money(v, true))}</dd>
    <dt>Entry fees on open positions</dt><dd>${isNum(o.open_position_costs) ? signed(-o.open_position_costs, (v) => money(v, true)) : NA}</dd>
    <dt>= Total P&amp;L</dt><dd>${signed(o.total_pnl, (v) => money(v, true))}</dd>
    <dt>Runner status</dt><dd>${txt(o.status_text)}</dd>
    <dt>State recorded at</dt><dd>${txt(o.state_time)}</dd></dl>`;
}

function renderPositions(d) {
  $("positions").innerHTML = table([
    { h: "Symbol", f: (r) => `<b>${esc(r.symbol)}</b>` }, { h: "Side", f: (r) => sideBadge(r.side) },
    { h: "Entry time (UTC)", f: (r) => tm(r.entry_time) },
    { h: "Entry price (open)", num: 1, f: (r) => price(r.entry_price) }, { h: "Entry fill", num: 1, f: (r) => price(r.entry_fill) },
    { h: "Current price", num: 1, f: (r) => `<span title="${esc(r.price_source)}">${price(r.current_price)}</span>` },
    { h: "Size (units)", num: 1, f: (r) => qty(r.qty) }, { h: "Market value", num: 1, f: (r) => money(r.market_value) },
    { h: "Allocation", num: 1, f: (r) => pct(r.allocation_pct, false, 1) },
    { h: "Unrealized $", num: 1, f: (r) => signed(r.unrealized_pnl, (v) => money(v, true)) },
    { h: "Unrealized %", num: 1, f: (r) => signed(r.unrealized_pct, pct) },
    { h: "40d return", num: 1, f: (r) => signed(r.ret40, pct) }, { h: "EMA200", num: 1, f: (r) => price(r.ema200) },
    { h: "BTC regime", f: (r) => txt(r.btc_regime) }, { h: "Why entered", cls: "reason", f: (r) => esc(r.entry_reason) },
  ], d.positions, "No open paper positions.");
}

function renderTrades(d) {
  const rows = d.trades.filter((t) => state.tradeFilter === "all" || t.status === state.tradeFilter);
  $("trades").innerHTML = table([
    { h: "Status", f: (r) => `<span class="badge ${r.status.toLowerCase()}">${r.status}</span>` },
    { h: "Symbol", f: (r) => `<b>${esc(r.symbol)}</b>` }, { h: "Side", f: (r) => sideBadge(r.side) },
    { h: "Entry time (UTC)", f: (r) => tm(r.entry_time) }, { h: "Entry fill", num: 1, f: (r) => price(r.entry_fill) },
    { h: "Exit time (UTC)", f: (r) => tm(r.exit_time) }, { h: "Exit fill", num: 1, f: (r) => price(r.exit_fill) },
    { h: "Size (units)", num: 1, f: (r) => qty(r.qty) }, { h: "Notional", num: 1, f: (r) => money(r.notional) },
    { h: "Fees", num: 1, f: (r) => money(r.fees) }, { h: "Slippage", num: 1, f: (r) => money(r.slippage) },
    { h: "Gross P&L", num: 1, f: (r) => signed(r.gross_pnl, (v) => money(v, true)) },
    { h: "Net P&L", num: 1, f: (r) => r.status === "OPEN" ? `<span title="unrealized">${signed(r.unrealized_pnl, (v) => money(v, true))} <span class="muted">unrl.</span></span>` : signed(r.net_pnl, (v) => money(v, true)) },
    { h: "Return", num: 1, f: (r) => signed(r.return_pct, pct) },
    { h: "Entry reason", cls: "reason", f: (r) => esc(r.entry_reason) }, { h: "Exit reason", cls: "reason", f: (r) => txt(r.exit_reason) },
  ], rows, state.tradeFilter === "CLOSED" ? "No closed paper trades yet." : "No paper trades recorded yet.");
}

function renderStrategy(d) {
  $("rules").innerHTML = d.strategy.rules.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("");
  $("sig-source").textContent = "Source: " + d.strategy.signals_source + ". A signal is NOT an order: the engine acts on it only at the next 00:00 UTC open, subject to the 10% / 100% caps.";
  $("signals").innerHTML = table([
    { h: "Symbol", f: (r) => `<b>${esc(r.symbol)}</b>` }, { h: "Candle", f: (r) => tm(r.candle) },
    { h: "40d return", num: 1, f: (r) => signed(r.ret40, pct) }, { h: "EMA200", num: 1, f: (r) => price(r.ema200) },
    { h: "Close", num: 1, f: (r) => price(r.close) }, { h: "Current price", num: 1, f: (r) => price(r.price) },
    { h: "Long eligible", f: (r) => yes(r.long_eligible) }, { h: "Short eligible", f: (r) => yes(r.short_eligible) },
    { h: "BTC regime", f: (r) => txt(r.btc_regime) }, { h: "Position", f: (r) => sideBadge(r.position) },
    { h: "Current signal", f: (r) => `<b>${esc(r.signal)}</b>` }, { h: "Reason", cls: "reason", f: (r) => txt(r.reason) },
  ], d.strategy.signals, "N/A");
}

function renderPerformance(d) {
  const p = d.performance, s = p.stats;
  $("perf-kpis").innerHTML = [
    kpi("Closed trades", String(s.trades)), kpi("Win rate", pct(s.win_rate, false, 1)),
    kpi("Profit factor", isNum(s.profit_factor) ? s.profit_factor.toFixed(2) : NA),
    kpi("Average win", signed(s.avg_win, (v) => money(v, true))), kpi("Average loss", signed(s.avg_loss, (v) => money(v, true))),
    kpi("Best trade", s.best ? signed(s.best.net_pnl, (v) => money(v, true)) : NA, s.best ? `${esc(s.best.symbol)} ${esc(s.best.side)}` : ""),
    kpi("Worst trade", s.worst ? signed(s.worst.net_pnl, (v) => money(v, true)) : NA, s.worst ? `${esc(s.worst.symbol)} ${esc(s.worst.side)}` : ""),
  ].join("");
  lineChart($("pf-equity"), p.equity_curve, { axis: (v) => "$" + v.toFixed(2), tipf: (v) => money(v) });
  lineChart($("pf-cum"), p.cumulative, { zero: true, axis: (v) => (v < 0 ? "−$" : "$") + Math.abs(v).toFixed(2), tipf: (v) => money(v, true) });
  lineChart($("pf-dd"), p.drawdown, { zero: true, color: "var(--neg)", fill: "var(--neg)", axis: (v) => (v * 100).toFixed(1) + "%", tipf: (v) => pct(v) });
  barChart($("pf-daily"), p.daily.map((r) => ({ label: r.date, v: r.pnl, pct: r.pnl_pct })),
    { axis: (v) => (v < 0 ? "−$" : "$") + Math.abs(v).toFixed(2), tipf: (r) => `${money(r.v, true)} (${pct(r.pct)})` });
  $("monthly").innerHTML = table([
    { h: "Month", f: (r) => esc(r.month) }, { h: "End equity", num: 1, f: (r) => money(r.equity) },
    { h: "P&L", num: 1, f: (r) => signed(r.pnl, (v) => money(v, true)) }, { h: "Return", num: 1, f: (r) => signed(r.pnl_pct, pct) },
  ], p.monthly, "N/A – no equity history yet");
  const sides = Object.entries(s.by_side || {}).map(([k, v]) => ({ side: k, ...v }));
  $("byside").innerHTML = table([
    { h: "Side", f: (r) => sideBadge(r.side) }, { h: "Trades", num: 1, f: (r) => r.trades },
    { h: "Win rate", num: 1, f: (r) => pct(r.win_rate, false, 1) },
    { h: "Profit factor", num: 1, f: (r) => (isNum(r.profit_factor) ? r.profit_factor.toFixed(2) : NA) },
    { h: "Net P&L", num: 1, f: (r) => signed(r.net_pnl, (v) => money(v, true)) },
  ], sides, "N/A – no closed trades yet");
}

function renderStatus(d) {
  const s = d.status;
  $("hero-orders").innerHTML = `<span class="hero-label">PAPER ORDERS (FILLED) / LIVE ORDERS</span><span class="hero-value">${txt(s.paper_orders)} / ${s.live_orders}</span><span class="muted">${esc(s.paper_orders_source)}</span>`;
  const oe = s.order_endpoint_called === false ? "NO" : s.order_endpoint_called === true ? "YES – REFUSED" : "N/A";
  const he = $("hero-endpoint"); he.className = "hero-item " + (s.order_endpoint_called === false ? "good" : s.order_endpoint_called === true ? "off" : "");
  he.innerHTML = `<span class="hero-label">ORDER ENDPOINT CALLED</span><span class="hero-value">${oe}</span><span class="muted">${esc(s.order_endpoint_source)}</span>`;
  $("status-kv").innerHTML = `
    <dt>Paper mode</dt><dd><b class="pos">${esc(s.paper_mode)}</b> <span class="muted">(${esc(s.paper_mode_basis)})</span></dd>
    <dt>Live trading</dt><dd><b>${esc(s.live_trading)}</b></dd>
    <dt>Bot</dt><dd>${botBadge(s.bot)} <span class="muted">${esc(s.bot?.detail || "")}</span></dd>
    <dt>Runner status</dt><dd>${txt(s.status_text)}</dd>
    <dt>Data feed</dt><dd>${txt(s.data_feed)}</dd>
    <dt>Last successful refresh</dt><dd>${txt(s.last_successful_refresh)}</dd>
    <dt>Next decision</dt><dd>${txt(s.next_decision)}</dd>
    <dt>Data errors</dt><dd>${txt(s.data_errors)}</dd>
    <dt>Session started</dt><dd>${txt(s.started_at)}</dd>
    <dt>Available symbols</dt><dd>${s.available_symbols ? esc(Object.keys(s.available_symbols).join(", ")) : NA}</dd>
    <dt>Unavailable symbols</dt><dd>${s.unavailable_symbols ? (Object.keys(s.unavailable_symbols).length ? esc(Object.entries(s.unavailable_symbols).map(([k, v]) => `${k}: ${v}`).join("; ")) : "none") : NA}</dd>
    <dt>Records</dt><dd class="muted">${txt(s.session_dir)}</dd>`;
  const pl = s.pipeline;
  $("pipeline").innerHTML = `
    <dt>Strategy signals logged</dt><dd>${pl.signals}</dd>
    <dt>Signals rejected</dt><dd>${pl.signals_rejected} <span class="muted">(counted at every daily decision while blocked) ${esc(Object.entries(pl.rejections_by_reason).map(([k, v]) => `${k}: ${v}`).join("; "))}</span></dd>
    <dt>Simulated paper orders (filled)</dt><dd>${txt(pl.paper_orders_filled)} <span class="muted">(${pl.entry_fills} entries, ${pl.exit_fills} exits)</span></dd>
    <dt>Open paper positions</dt><dd>${pl.open_positions}</dd>
    <dt>Closed paper trades</dt><dd>${pl.closed_trades}</dd>
    <dt>Live orders</dt><dd><b>0</b> <span class="muted">(no live order path exists)</span></dd>`;
  $("errors").innerHTML = s.recent_errors.length ? s.recent_errors.slice().reverse().map((e) => `<div class="err-line">${esc(e)}</div>`).join("") : '<div class="empty">No data errors recorded.</div>';
}

function render() {
  const d = state.data;
  const banner = $("banner");
  if (!d) return;
  if (!d.available) {
    banner.className = "banner warn"; banner.textContent = d.source?.error || "No paper-trading session found.";
    return;
  }
  const b = d.overview.bot_status;
  if (d.source.stale_read) { banner.className = "banner warn"; banner.textContent = "Showing the last good read: state.json could not be read just now (" + (d.source.error || "") + ")."; }
  else if (b.state === "STALE") { banner.className = "banner warn"; banner.textContent = "Runner looks STALE: " + b.detail; }
  else if (String(d.overview.status_text || "").includes("WARNING")) { banner.className = "banner crit"; banner.textContent = d.overview.status_text; }
  else banner.className = "banner hidden";
  ({ overview: renderOverview, positions: renderPositions, trades: renderTrades, strategy: renderStrategy,
     performance: renderPerformance, status: renderStatus })[state.tab](d);
}

// ------------------------------------------------------------------------------------------------ loop
async function poll() {
  try {
    const r = await fetch("/api/dashboard", { cache: "no-store" });
    if (!r.ok) throw new Error("HTTP " + r.status);
    state.data = await r.json();
    state.lastOk = Date.now();
    state.refreshMs = state.data.refresh_ms || 3000;
    $("conn").className = "conn";
    render();
  } catch (e) {
    $("conn").className = "conn err";
    $("conn").textContent = "dashboard API unreachable: " + e.message;
  }
  setTimeout(poll, state.refreshMs);
}
setInterval(() => {
  if (state.lastOk && !$("conn").classList.contains("err")) $("conn").textContent = `updated ${Math.round((Date.now() - state.lastOk) / 1000)}s ago · auto-refresh ${state.refreshMs / 1000}s`;
}, 1000);

function selectTab(name) {
  const t = document.querySelector(`.tab[data-tab="${name}"]`);
  if (!t) return;
  document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === t));
  state.tab = name;
  document.querySelectorAll(".tabpanel").forEach((p) => p.classList.toggle("hidden", p.id !== "tab-" + name));
  if (location.hash !== "#" + name) history.replaceState(null, "", "#" + name);
  render();
}
document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => selectTab(t.dataset.tab)));
if (location.hash) selectTab(location.hash.slice(1));
document.querySelectorAll("#trade-filter button").forEach((b) => b.addEventListener("click", () => {
  document.querySelectorAll("#trade-filter button").forEach((x) => x.classList.toggle("active", x === b));
  state.tradeFilter = b.dataset.f; render();
}));
let rz; window.addEventListener("resize", () => { clearTimeout(rz); rz = setTimeout(render, 150); });
poll();
