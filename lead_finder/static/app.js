"use strict";
// Lead Finder UI. All provider-sourced strings are inserted as text nodes, never as HTML.

const $ = (sel) => document.querySelector(sel);
const state = { view: null, providers: null, filters: {} };

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else if (k === "href") { if (/^https?:\/\//i.test(v)) { node.href = v; node.target = "_blank"; node.rel = "noopener noreferrer"; } }
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    method: opts.method || "GET", credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-Requested-With": "LeadFinder" },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (res.status === 401 && path !== "/api/auth/login") { showLogin(); throw new Error("Not authenticated"); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : `Request failed (${res.status})`);
  return data;
}

function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.classList.remove("hidden");
  clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.add("hidden"), 3500);
}

// ---------------------------------------------------------------- formatting
const money = (v) => v === null || v === undefined ? "Holdings unavailable" : "$" + Math.round(v).toLocaleString();
function ago(ts) {
  if (!ts) return "No recent activity data";
  const d = (Date.now() - new Date(ts).getTime()) / 86400000;
  if (isNaN(d)) return "Unknown";
  if (d < 1) return "Active today";
  const n = Math.round(d);
  return `Active ${n} day${n === 1 ? "" : "s"} ago`;
}
const when = (ts) => ts ? new Date(ts).toLocaleString() : "—";
const chainName = (k) => (state.providers?.provider_chains || []).find((c) => c.key === k)?.name || k;
const confBadge = (v) => el("span", { class: "badge " + ({ High: "b-green", Medium: "b-violet", Low: "b-amber" }[v] || "b-gray") }, v || "None");
function verifBadge(v) {
  if (!v) return el("span", { class: "badge b-gray" }, "—");
  return el("span", { class: "badge " + ({ Verified: "b-green", "Self-published": "b-violet", Risky: "b-amber", Invalid: "b-red" }[v] || "b-gray") }, v);
}
const kv = (k, v) => el("div", {}, el("div", { class: "k" }, k), el("div", { class: "v" }, v));

// ------------------------------------------------------------------ auth
function showLogin() { $("#app").classList.add("hidden"); $("#login").classList.remove("hidden"); }
$("#loginForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  try {
    await api("/api/auth/login", { method: "POST", body: { email: f.get("email"), password: f.get("password") } });
    $("#loginError").classList.add("hidden");
    boot();
  } catch (err) { $("#loginError").textContent = err.message; $("#loginError").classList.remove("hidden"); }
});
$("#logout").addEventListener("click", async () => { await api("/api/auth/logout", { method: "POST" }).catch(() => {}); showLogin(); });

// ------------------------------------------------------------- providers
const PROVIDER_LABEL = { "ENS (Ethereum RPC)": "ENS", "Public website": "Website" };
function dotClass(status) {
  if (status === "Connected") return "ok";
  if (status === "Not Configured" || status === "Configured (not yet used)") return "";
  if (status === "Rate limited") return "warn";
  return "bad";
}
function renderProviders(view) {
  state.providers = view;
  const box = $("#providers"); box.replaceChildren();
  for (const p of view.providers) {
    box.append(el("div", { class: "prov", title: [p.message, p.checked_at && `checked ${when(p.checked_at)}`].filter(Boolean).join(" · ") },
      el("span", { class: "dot " + dotClass(p.status) }), el("b", {}, PROVIDER_LABEL[p.provider] || p.provider), el("span", { class: "muted" }, p.status)));
  }
  const sel = $("#chainSelect"); const cur = sel.value; sel.replaceChildren(el("option", { value: "" }, "All verified chains"));
  if (!view.chains.length) sel.append(el("option", { value: "", disabled: true }, "No chain verified by provider yet"));
  for (const c of view.chains) sel.append(el("option", { value: c.key }, c.name));
  sel.value = cur;
}
async function loadProviders(check = false) {
  renderProviders(await api(check ? "/api/providers/check" : "/api/providers", { method: check ? "POST" : "GET" }));
}

// -------------------------------------------------------------- pipeline
async function loadPipeline() {
  const c = await api("/api/pipeline");
  const stages = [["Discovered Wallets", c.discovered], ["Qualified Wallets", c.qualified], ["Identified Individuals", c.identified],
    ["Contactable Individuals", c.contactable, "hl"], ["Saved Leads", c.saved], ["CRM", c.crm], ["Unattributed", c.unattributed, "side"]];
  $("#pipeline").replaceChildren(...stages.map(([label, val, cls]) =>
    el("div", { class: "stage " + (cls || "") }, el("div", { class: "label" }, label), el("div", { class: "val" }, (val ?? 0).toLocaleString()))));
  $("#savedCount").textContent = c.saved || "";
}

// ---------------------------------------------------------------- filters
function readFilters() {
  const out = {};
  for (const input of $("#filters").querySelectorAll("input, select")) {
    if (input.type === "checkbox") { if (input.checked) out[input.name] = true; }
    else if (input.value.trim() !== "") out[input.name] = input.type === "number" ? Number(input.value) : input.value.trim();
  }
  return out;
}
$("#filters").addEventListener("submit", (e) => { e.preventDefault(); state.view = null; $("#searchMeta").classList.add("hidden"); loadLeads(); });
$("#clearFilters").addEventListener("click", () => { $("#filters").reset(); state.view = null; $("#searchMeta").classList.add("hidden"); loadLeads(); });

// ----------------------------------------------------------------- leads
async function loadLeads() {
  const params = new URLSearchParams(Object.entries(readFilters()).map(([k, v]) => [k, String(v)]));
  const [c, o] = await Promise.all([api(`/api/leads?category=contactable&${params}`), api(`/api/leads?category=opportunity&${params}`)]);
  renderResults(c.leads, o.leads);
}

function emptyState() {
  const prov = Object.fromEntries((state.providers?.providers || []).map((p) => [p.provider, p.status]));
  const items = [];
  if (prov.Nansen === "Not Configured") items.push("Nansen is not configured: no wallets can be discovered or qualified (set NANSEN_API_KEY).");
  else if (prov.Nansen && !["Connected", "Configured (not yet used)"].includes(prov.Nansen)) items.push(`Nansen: ${prov.Nansen}. No wallet data is being substituted.`);
  if (prov["ENS (Ethereum RPC)"] === "Not Configured") items.push("ENS lookups are not configured (set ETH_RPC_URL): wallets cannot be attributed to people.");
  if (prov.Apollo === "Not Configured" && prov.Hunter === "Not Configured") items.push("Apollo and Hunter are not configured: only contacts the wallet owner published themselves can be used.");
  return el("div", { class: "empty" }, el("h3", {}, "No contactable leads yet"),
    el("div", {}, "Leads appear here only when a real person has publicly linked the wallet to themselves and published a way to contact them."),
    items.length ? el("ul", {}, items.map((i) => el("li", {}, i))) : null);
}

function leadCard(l) {
  const card = el("div", { class: "card lead" },
    el("div", { class: "lead-top" },
      el("div", {}, el("div", { class: "lead-name" }, l.name || "Unknown"),
        el("div", { class: "lead-sub" }, [l.title, l.company].filter(Boolean).join(" · ") || "Title / company not published")),
      el("div", { class: `score ${l.score_class}` }, el("div", { class: "num" }, l.lead_score), el("div", { class: "small muted" }, l.score_class))),
    el("div", { class: "kv" },
      kv("Wallet", el("span", { class: "mono", title: l.wallet_address }, l.wallet_display)),
      kv("Chain", chainName(l.chain)),
      kv("Estimated Holdings", l.holdings_display),
      kv("Activity", ago(l.last_active_at)),
      kv("Email", l.email || "—"),
      kv("Phone", l.phone || "—"),
      kv("Identity Confidence", confBadge(l.identity_confidence)),
      kv("Wallet Attribution", confBadge(l.wallet_attribution_confidence)),
      kv("Email Verification", verifBadge(l.email_verification_status)),
      kv("Funding Interest", l.funding_interest)),
    el("div", { class: "src" }, "Source: ", [l.wallet_source, "Nansen", l.contact_source].filter(Boolean).join(" / ")),
    l.other_wallets?.length ? el("div", { class: "src" }, `Also holds ${l.other_wallets.length} other attributed wallet(s)`) : null,
    el("div", { class: "lead-actions" },
      el("button", { class: "btn primary sm", disabled: l.saved, onclick: () => saveLead(l.id) }, l.saved ? "Saved" : "Save"),
      el("button", { class: "btn ghost sm", onclick: () => viewLead(l.id) }, "View"),
      el("button", { class: "btn ghost sm", onclick: () => notesModal(l.id) }, `Notes${l.notes_count ? ` (${l.notes_count})` : ""}`)));
  return card;
}

function renderResults(contactable, opportunities) {
  $("#contactableCount").textContent = contactable.length;
  $("#leadGrid").replaceChildren(...(contactable.length ? contactable.map(leadCard) : [emptyState()]));
  $("#oppCount").textContent = opportunities.length;
  $("#oppTable tbody").replaceChildren(...opportunities.map((o) => el("tr", {},
    el("td", {}, el("span", { class: "mono", title: o.wallet_address }, o.wallet_display)),
    el("td", {}, chainName(o.chain)),
    el("td", {}, o.holdings_display),
    el("td", {}, o.recent_activity === null ? "Unknown" : `${o.recent_activity} trades / 90d`),
    el("td", {}, o.name || el("span", { class: "muted" }, o.classification === "entity" ? "Entity" : "Unidentified")),
    el("td", {}, confBadge(o.wallet_attribution_confidence)),
    el("td", {}, el("div", { class: "reasons" }, (o.opportunity_reasons || []).join(" · ") || "—")),
    el("td", {}, el("button", { class: "btn ghost sm", onclick: () => viewLead(o.id) }, "View")))));
}

async function saveLead(id) {
  try {
    const r = await api(`/api/leads/${id}/save`, { method: "POST" });
    toast(r.created ? "Lead saved to Saved Leads / CRM" : "Already saved — existing record kept");
    refreshView();
  } catch (err) { toast(err.message); }
}

// ---------------------------------------------------------------- search
$("#searchForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $("#searchBtn"); btn.disabled = true; btn.replaceChildren(el("span", { class: "spinner" }), "Searching…");
  try {
    const r = await api("/api/searches", { method: "POST", body: { query: $("#q").value, filters: readFilters() } });
    showSearch(r);
  } catch (err) { toast(err.message); }
  finally { btn.disabled = false; btn.textContent = "Search Leads"; loadProviders(); loadPipeline(); }
});
$("#refreshBtn").addEventListener("click", async () => { await loadProviders(true).catch((e) => toast(e.message)); refreshView(); });

function showSearch(r) {
  state.view = r.search.id;
  switchTab("leads");
  const s = r.search; const meta = $("#searchMeta"); meta.classList.remove("hidden");
  const errs = Object.entries(s.provider_report?.providers || {}).flatMap(([p, v]) =>
    Object.entries(v.errors || {}).map(([st, n]) => `${p}: ${st} ×${n}`));
  meta.replaceChildren(...[
    el("span", {}, `Search #${s.id}`), el("span", {}, `Discovered ${s.discovered}`), el("span", {}, `Qualified ${s.qualified}`),
    el("span", {}, `Identified ${s.identified}`), el("span", {}, `Contactable ${s.contactable}`), el("span", {}, `Unattributed ${s.unattributed}`),
    s.reused ? el("span", {}, `${s.reused} untouched lead(s) from earlier runs shown first`) : null,
    s.failed ? el("span", { class: "warn" }, `Failed ${s.failed}`) : null,
    ...errs.map((x) => el("span", { class: "warn" }, x)),
    ...(s.provider_report?.failures || []).slice(0, 5).map((f) => el("span", { class: "warn" }, `${f.input}: ${f.reason}`)),
    el("button", { class: "btn ghost sm", onclick: () => { state.view = null; meta.classList.add("hidden"); loadLeads(); } }, "Show all leads"),
  ].filter(Boolean));
  renderResults(r.contactable, r.opportunities);
}

async function refreshView() {
  await loadPipeline();
  if (state.view) showSearch(await api(`/api/searches/${state.view}`)); else await loadLeads();
  if (!$("#tab-saved").classList.contains("hidden")) loadSaved();
  if (!$("#tab-searches").classList.contains("hidden")) loadSearches();
}

// ----------------------------------------------------------------- modal
function openModal(...children) { $("#modalBody").replaceChildren(...children); $("#modal").classList.remove("hidden"); }
function closeModal() { $("#modal").classList.add("hidden"); }
$("#modalClose").addEventListener("click", closeModal);
$("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") closeModal(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });

async function setStatus(id, status) {
  try { await api(`/api/leads/${id}`, { method: "PATCH", body: { status } }); toast(`Lead marked ${status.replace(/_/g, " ")}`); closeModal(); refreshView(); }
  catch (err) { toast(err.message); }
}

async function viewLead(id) {
  const d = await api(`/api/leads/${id}`);
  const w = d.wallet || {}; const i = d.identity || {};
  const ev = (d.sources || []).map((s) => el("div", {}, el("b", {}, `${s.kind} · ${s.provider}: `), s.detail || "",
    s.url ? el("span", {}, " — ", el("a", { href: s.url }, s.url)) : null));
  const breakdown = Object.entries(d.score_breakdown || {}).map(([k, v]) => kv(k.replace(/_/g, " "), String(v)));
  openModal(el("div", { class: "detail" },
    el("div", { class: "lead-top" },
      el("div", {}, el("h2", {}, d.name || "Unidentified wallet"),
        el("div", { class: "muted" }, [d.title, d.company, i.location_text].filter(Boolean).join(" · ") || "No published title/company")),
      el("div", { class: `score ${d.score_class}` }, el("div", { class: "num" }, d.lead_score), el("div", { class: "small muted" }, `${d.score_class} · ${d.category}`))),
    d.opportunity_reasons?.length ? el("div", { class: "src" }, "Not contactable: ", d.opportunity_reasons.join(" · ")) : null,
    el("div", { class: "detail-grid kv" },
      kv("Wallet", el("span", { class: "mono" }, w.address || d.wallet_address)), kv("Chain", chainName(d.chain)),
      kv("Estimated holdings", money(w.estimated_portfolio_value) + (w.holdings_status === "Partial" ? " (partial)" : "")),
      kv("Native balance", w.native_balance === null || w.native_balance === undefined ? "Unknown" : `${w.native_balance} ${w.native_symbol}`),
      kv("Assets", w.asset_count ?? "Unknown"), kv("Activity", w.recent_activity_count === null || w.recent_activity_count === undefined ? "Unknown" : `${w.recent_activity_count}${w.activity?.truncated ? "+" : ""} DEX trades / ${w.activity?.window_days || 90}d`),
      kv("Last active", w.last_active_at ? when(w.last_active_at) : "Unknown"), kv("Contract", w.is_contract === null || w.is_contract === undefined ? "Unknown" : w.is_contract ? "Yes" : "No (EOA)"),
      kv("Funding interest", d.funding_interest),
      kv("Email", d.email || "—"), kv("Phone", d.phone || "—"), kv("LinkedIn", d.linkedin ? el("a", { href: d.linkedin }, "Profile") : "—"),
      kv("Identity confidence", confBadge(d.identity_confidence)), kv("Wallet attribution", confBadge(d.wallet_attribution_confidence)),
      kv("Email verification", verifBadge(d.email_verification_status)),
      kv("Classification", d.classification), kv("Public prominence", d.public_prominence),
      kv("Apollo / Hunter", `${d.apollo_status || "Not run"} / ${d.hunter_status || "Not run"}`)),
    w.provider_labels?.length ? el("div", { class: "chips" }, w.provider_labels.map((p) => el("span", { class: "badge b-gray" }, p.label))) : null,
    el("h3", {}, "Evidence & sources"), el("div", { class: "ev" }, ev.length ? ev : el("div", {}, "No evidence recorded")),
    el("h3", {}, "Score breakdown"), el("div", { class: "kv" }, breakdown),
    el("h3", {}, "Actions"),
    el("div", { class: "lead-actions" },
      d.category === "contactable" ? el("button", { class: "btn primary sm", disabled: d.saved, onclick: () => saveLead(d.id).then(closeModal) }, d.saved ? "Saved" : "Save") : null,
      el("button", { class: "btn ghost sm", onclick: () => setStatus(d.id, "contacted") }, "Mark contacted"),
      el("button", { class: "btn ghost sm", onclick: () => setStatus(d.id, "suppressed") }, "Suppress"),
      el("button", { class: "btn danger sm", onclick: () => setStatus(d.id, "do_not_contact") }, "Do Not Contact"),
      el("button", { class: "btn danger sm", onclick: async () => { await api(`/api/leads/${d.id}`, { method: "DELETE" }); toast("Lead deleted"); closeModal(); refreshView(); } }, "Delete"))));
}

async function notesModal(id) {
  const { notes } = await api(`/api/leads/${id}/notes`);
  const ta = el("textarea", { rows: 4, maxlength: 5000, placeholder: "Add a note…" });
  openModal(el("h2", {}, "Notes"), el("div", { class: "notes-list" },
    notes.length ? notes.map((n) => el("div", { class: "note" }, el("div", { class: "small muted" }, `${n.author} · ${when(n.created_at)}`), el("div", {}, n.body)))
      : el("div", { class: "muted" }, "No notes yet.")),
    ta, el("div", { class: "mt" }, el("button", { class: "btn primary", onclick: async () => {
      if (!ta.value.trim()) return;
      await api(`/api/leads/${id}/notes`, { method: "POST", body: { body: ta.value } });
      toast("Note added"); notesModal(id); refreshView();
    } }, "Add note")));
}

// ------------------------------------------------------------ saved/CRM
async function loadSaved() {
  const { saved } = await api("/api/saved");
  $("#savedTable tbody").replaceChildren(...(saved.length ? saved.map((s) => {
    const snap = s.snapshot; const l = s.lead || {};
    const sel = el("select", { onchange: async (e) => { await api(`/api/saved/${s.id}`, { method: "PATCH", body: { crm_stage: e.target.value } }); toast("Stage updated"); loadPipeline(); } },
      el("option", { value: "saved" }, "Saved"), el("option", { value: "crm" }, "CRM"));
    sel.value = s.crm_stage;
    return el("tr", {},
      el("td", {}, el("div", {}, snap.name || "—"), el("div", { class: "small muted" }, [snap.title, snap.company].filter(Boolean).join(" · "))),
      el("td", {}, el("span", { class: "mono" }, l.wallet_display || snap.wallet_address), el("div", { class: "small muted" }, chainName(snap.chain))),
      el("td", {}, money(snap.estimated_holdings_usd)),
      el("td", {}, snap.email || "—"), el("td", {}, l.phone || "—"),
      el("td", {}, `${snap.lead_score} (${snap.score_class})`),
      el("td", {}, when(s.saved_at)), el("td", {}, sel),
      el("td", {}, el("button", { class: "btn ghost sm", onclick: () => viewLead(s.lead_id) }, "View"), " ",
        el("button", { class: "btn ghost sm", onclick: () => notesModal(s.lead_id) }, `Notes${s.notes.length ? ` (${s.notes.length})` : ""}`)));
  }) : [el("tr", {}, el("td", { colspan: 9, class: "muted" }, "No saved leads yet."))]));
}

// --------------------------------------------------------- recent searches
async function loadSearches() {
  const { searches } = await api("/api/searches");
  $("#searchTable tbody").replaceChildren(...(searches.length ? searches.map((s) => el("tr", {},
    el("td", {}, when(s.created_at)), el("td", {}, s.query || el("span", { class: "muted" }, "(discovery)")),
    el("td", { class: "small" }, Object.entries(s.filters).map(([k, v]) => `${k}=${v}`).join(", ") || "—"),
    el("td", {}, s.discovered), el("td", {}, s.qualified), el("td", {}, s.identified), el("td", {}, s.contactable), el("td", {}, s.reused),
    el("td", {}, s.status),
    el("td", {}, el("button", { class: "btn ghost sm", onclick: async () => showSearch(await api(`/api/searches/${s.id}`)) }, "Open"), " ",
      el("button", { class: "btn primary sm", onclick: async (e) => {
        e.target.disabled = true;
        try { showSearch(await api(`/api/searches/${s.id}/rerun`, { method: "POST" })); } catch (err) { toast(err.message); }
        loadPipeline(); loadProviders();
      } }, "Rerun"))))
    : [el("tr", {}, el("td", { colspan: 10, class: "muted" }, "No searches yet."))]));
}

// ------------------------------------------------------------------ tabs
function switchTab(name) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  for (const n of ["leads", "saved", "searches"]) $(`#tab-${n}`).classList.toggle("hidden", n !== name);
  if (name === "saved") loadSaved();
  if (name === "searches") loadSearches();
}
document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => switchTab(t.dataset.tab)));

async function boot() {
  try {
    const me = await api("/api/me");
    $("#whoFirm").textContent = me.firm; $("#whoEmail").textContent = me.email;
    $("#login").classList.add("hidden"); $("#app").classList.remove("hidden");
    await loadProviders(); await loadPipeline(); await loadLeads();
  } catch (_) { showLogin(); }
}
boot();
