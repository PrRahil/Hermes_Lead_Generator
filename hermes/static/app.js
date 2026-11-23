const money = (n) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(n || 0);

const charts = {};
let selectedLeadId = null;
let activePlatform = "";
let activeKind = "";
let lastPlatforms = {};

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  if (!res.ok) throw new Error(await res.text() || res.statusText);
  return res.json();
}

function scoreClass(score) {
  if (score >= 65) return "high";
  if (score < 40) return "low";
  return "";
}

function renderRunner(health) {
  const r = health.runner || {};
  const strong = health.strong_leads ?? 0;
  const target = health.strong_lead_target ?? 50;
  const pct = Math.min(100, Math.round((strong / Math.max(1, target)) * 100));
  document.getElementById("strong-progress-text").textContent = `${strong} / ${target}`;
  document.getElementById("strong-progress-fill").style.width = `${pct}%`;
  const state = r.running ? "HUNTING" : "IDLE";
  document.getElementById("runner-status").textContent =
    `${state} · cycle ${r.cycle || 0} · threshold ≥${health.strong_lead_min_score ?? 45} · ${r.message || "python -m hermes run"}` +
    (r.current_query ? ` · ${r.current_query}` : "");
}

function renderKpis(data) {
  const t = data.totals || {};
  const c = data.conversion || {};
  const cards = [
    ["Active listings", t.listings ?? 0, `${t.expired || 0} expired · TTL ${t.listing_ttl_days || 21}d`],
    ["Engaged leads", t.leads ?? 0, `Listing→lead ${c.listing_to_lead || 0}%`],
    ["Strong fit", `${t.strong_leads ?? 0} / ${t.strong_lead_target ?? 50}`, `Score ≥ ${t.strong_lead_min_score ?? 45}`],
    ["Drafts ready", t.drafts_ready ?? 0, `${t.missing_drafts || 0} missing`],
    ["Pipeline $", money(t.pipeline_value), `Avg ${money(t.avg_deal_value)}`],
    ["Awaiting reply", t.awaiting_reply ?? 0, `${t.in_negotiation || 0} in negotiation`],
    ["Won revenue", money(t.won_value), `${t.won_deals || 0} closed`],
    ["Avg fit", t.avg_fit_score ?? 0, `${t.companies || 0} companies`],
  ];
  document.getElementById("kpi-grid").innerHTML = cards
    .map(
      ([label, value, hint]) => `
      <div class="kpi"><div class="label">${label}</div><div class="value">${value}</div><div class="hint">${hint}</div></div>`
    )
    .join("");
}

function renderPlatformChips(platforms) {
  lastPlatforms = platforms || {};
  const el = document.getElementById("platform-chips");
  const entries = Object.entries(lastPlatforms).sort((a, b) => b[1] - a[1]);
  el.innerHTML =
    `<button class="chip ${activePlatform === "" ? "active" : ""}" data-platform="">All sources</button>` +
    entries
      .map(
        ([p, n]) =>
          `<button class="chip ${activePlatform === p ? "active" : ""}" data-platform="${p}">${p} <span class="muted">${n}</span></button>`
      )
      .join("");
  el.querySelectorAll("[data-platform]").forEach((btn) => {
    btn.addEventListener("click", () => {
      activePlatform = btn.dataset.platform;
      renderPlatformChips(lastPlatforms);
      loadLeads();
    });
  });
}

function renderActionQueue(items) {
  const el = document.getElementById("action-queue");
  if (!items?.length) {
    el.innerHTML = `<div class="muted">No actions yet.</div>`;
    return;
  }
  el.innerHTML = items
    .map(
      (l) => `
      <div class="action-row" data-id="${l.id}">
        <span class="score-pill ${scoreClass(l.fit_score)}">${l.fit_score}</span>
        <div><strong>${l.company?.name || "Unknown"}</strong><div class="muted">${l.record_kind} · ${l.contact?.title || "—"}</div></div>
        <div>${(l.project_summary || l.source_title || "").slice(0, 100)}</div>
        <span class="badge">${l.source_platform}</span>
        <span class="badge">${l.stage}</span>
        <strong>${money(l.estimated_deal_value)}</strong>
      </div>`
    )
    .join("");
  el.querySelectorAll(".action-row").forEach((row) =>
    row.addEventListener("click", () => openLead(Number(row.dataset.id)))
  );
}

function upsertChart(id, type, config) {
  const ctx = document.getElementById(id);
  if (!ctx) return;
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart(ctx, { type, ...config });
}

function renderCharts(data) {
  const palette = ["#d08a4c", "#3db8a0", "#7bc47f", "#6ea8d9", "#c4a35a", "#d96b6b", "#9b8cff", "#e0e0e0"];
  const axis = {
    x: { ticks: { color: "#93a0b4" }, grid: { color: "rgba(255,255,255,0.04)" } },
    y: { ticks: { color: "#93a0b4" }, grid: { color: "rgba(255,255,255,0.04)" } },
  };
  upsertChart("funnelChart", "bar", {
    data: {
      labels: (data.funnel || []).map((f) => f.stage),
      datasets: [{ data: (data.funnel || []).map((f) => f.count), backgroundColor: "#d08a4c", borderRadius: 8 }],
    },
    options: { plugins: { legend: { display: false } }, scales: axis },
  });
  const platforms = Object.keys(data.platforms || {});
  upsertChart("platformChart", "doughnut", {
    data: { labels: platforms, datasets: [{ data: platforms.map((p) => data.platforms[p]), backgroundColor: palette }] },
    options: { plugins: { legend: { labels: { color: "#93a0b4" } } } },
  });
  const bands = Object.keys(data.revenue_bands || {});
  upsertChart("revenueChart", "bar", {
    data: {
      labels: bands,
      datasets: [{ data: bands.map((b) => data.revenue_bands[b]), backgroundColor: "#3db8a0", borderRadius: 8 }],
    },
    options: { plugins: { legend: { display: false } }, scales: axis },
  });
  const values = data.platform_pipeline_value || {};
  const vKeys = Object.keys(values);
  upsertChart("valueChart", "bar", {
    data: {
      labels: vKeys,
      datasets: [{ data: vKeys.map((k) => values[k]), backgroundColor: "#6ea8d9", borderRadius: 8 }],
    },
    options: { plugins: { legend: { display: false } }, scales: axis },
  });
}

function renderScans(scans) {
  const el = document.getElementById("scans");
  if (!scans?.length) {
    el.innerHTML = `<div class="muted">No cycles yet.</div>`;
    return;
  }
  el.innerHTML = scans
    .map(
      (s) => `
      <div class="scan-row">
        <strong>#${s.id}</strong>
        <div>${s.status} · ${s.signals_found} signals · ${s.leads_created} new · ${s.outreach_drafted} drafts</div>
        <div class="muted">${s.started_at ? new Date(s.started_at).toLocaleString() : ""}</div>
      </div>`
    )
    .join("");
}

function renderIntegrations(items) {
  const el = document.getElementById("integrations");
  if (!items?.length) {
    el.innerHTML = "";
    return;
  }
  el.innerHTML = items
    .map(
      (i) => `
      <div class="integ-row">
        <strong>${i.name}</strong>
        <span class="badge">${i.status}</span>
        <span class="badge">${i.type}</span>
        <div class="muted">${i.role} — ${i.notes}</div>
      </div>`
    )
    .join("");
}

async function loadLeads() {
  const stage = document.getElementById("filter-stage").value;
  const minScore = document.getElementById("min-score").value || 0;
  const revenueOnly = document.getElementById("revenue-only").checked;
  const params = new URLSearchParams({
    min_score: String(minScore),
    revenue_fit_only: String(revenueOnly),
  });
  if (stage) params.set("stage", stage);
  if (activePlatform) params.set("platform", activePlatform);
  if (activeKind) params.set("record_kind", activeKind);
  const data = await api(`/api/leads?${params.toString()}`);
  document.getElementById("desk-count").textContent = `(${data.items.length}, latest first)`;
  const tbody = document.querySelector("#leads-table tbody");
  if (!data.items.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="muted">No rows for this filter.</td></tr>`;
    return;
  }
  tbody.innerHTML = data.items
    .map((l) => {
      const req = (l.project_summary || l.source_title || "").slice(0, 80);
      return `
      <tr data-id="${l.id}" class="${selectedLeadId === l.id ? "active" : ""}">
        <td><span class="score-pill ${scoreClass(l.fit_score)}">${l.fit_score}</span></td>
        <td><span class="badge">${l.record_kind || "listing"}</span></td>
        <td><div>${l.company?.name || "—"}</div><div class="muted">${l.contact?.title || ""}</div></td>
        <td>${req}</td>
        <td><span class="badge">${l.source_platform}</span></td>
        <td>${l.stage}</td>
        <td>${money(l.estimated_deal_value)}</td>
      </tr>`;
    })
    .join("");
  tbody.querySelectorAll("tr").forEach((tr) =>
    tr.addEventListener("click", () => openLead(Number(tr.dataset.id)))
  );
}

async function openLead(id) {
  selectedLeadId = id;
  const lead = await api(`/api/leads/${id}`);
  const body = document.getElementById("detail-body");
  const outreach = (lead.outreach && lead.outreach[0]) || null;
  const mailto = lead.send?.mailto;
  const tel = lead.send?.tel;
  body.innerHTML = `
    <div class="company">${lead.company?.name || "Unknown"}</div>
    <div class="muted">${lead.record_kind} · ${lead.source_platform} · ${lead.stage} · score ${lead.fit_score}
      ${lead.expires_at ? ` · expires ${new Date(lead.expires_at).toLocaleDateString()}` : ""}</div>
    <p>${lead.project_summary || lead.source_snippet || ""}</p>
    ${lead.source_url ? `<p><a href="${lead.source_url}" target="_blank" rel="noreferrer" style="color:#3db8a0">Source</a></p>` : ""}
    <h3>Buyer</h3>
    <p>${lead.contact?.full_name || "—"} · ${lead.contact?.title || "—"}<br/>
    <span class="muted">${lead.contact?.email || "no email"} · ${lead.contact?.phone || lead.phone_captured || "no phone"}</span></p>
    <h3>Why scored</h3>
    <ul class="reasons">${(lead.score_reasons || []).map((r) => `<li>${r}</li>`).join("")}</ul>
    <h3>Intellytics cold draft</h3>
    ${
      outreach
        ? `<div><strong>A:</strong> ${outreach.subject_a || ""}</div>
           <div><strong>B:</strong> ${outreach.subject_b || ""}</div>
           <textarea id="draft-body" class="outreach-edit">${outreach.body || ""}</textarea>`
        : `<p class="muted">No draft — click Backfill drafts.</p>`
    }
    <div class="stage-actions">
      ${mailto ? `<a class="btn tiny primary" id="btn-mailto" href="${mailto}">Open email client</a>` : ""}
      ${tel ? `<a class="btn tiny" href="${tel}">Call</a>` : ""}
      <button class="btn tiny" id="btn-send-mark">Mark sent → lead</button>
      <button class="btn tiny" data-stage="replied">Replied</button>
      <button class="btn tiny" data-stage="negotiation">Negotiation</button>
      <button class="btn tiny" data-stage="won">Won</button>
      <button class="btn tiny" data-stage="lost">Lost</button>
    </div>
  `;
  const sendBtn = document.getElementById("btn-send-mark");
  if (sendBtn) {
    sendBtn.addEventListener("click", async () => {
      await api(`/api/leads/${id}/send`, {
        method: "POST",
        body: JSON.stringify({ subject_variant: "a", mark_sent: true, use_smtp: false }),
      });
      await refresh();
      await openLead(id);
    });
  }
  body.querySelectorAll("[data-stage]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await api(`/api/leads/${id}/stage`, {
        method: "POST",
        body: JSON.stringify({ stage: btn.dataset.stage }),
      });
      await refresh();
      await openLead(id);
    });
  });
}

async function runScan() {
  const status = document.getElementById("scan-status");
  status.hidden = false;
  status.textContent = "Scanning…";
  try {
    const result = await api("/api/scan", {
      method: "POST",
      body: JSON.stringify({
        query: document.getElementById("scan-query").value,
        use_demo: document.getElementById("use-demo").checked,
        use_reddit: document.getElementById("use-reddit").checked,
        use_web: document.getElementById("use-web").checked,
        limit_per_source: 25,
        use_llm: false,
      }),
    });
    status.textContent = `Done — ${result.signals_found} signals, ${result.listings_created ?? result.leads_created} listings, ${result.outreach_drafted} drafts, ${result.expired || 0} expired. Strong ${result.strong_leads}`;
    await refresh();
  } catch (err) {
    status.textContent = `Scan failed: ${err.message}`;
  }
}

async function cleanupLeads() {
  if (!confirm("Wipe ALL listings/leads?")) return;
  if (!confirm("Final confirm?")) return;
  const status = document.getElementById("scan-status");
  status.hidden = false;
  const result = await api("/api/cleanup", { method: "POST", body: JSON.stringify({ mode: "all" }) });
  status.textContent = `Cleanup: ${JSON.stringify(result.deleted || result)}`;
  selectedLeadId = null;
  document.getElementById("detail-body").innerHTML = "";
  await refresh();
}

async function expireStale() {
  const status = document.getElementById("scan-status");
  status.hidden = false;
  const result = await api("/api/expire", { method: "POST", body: "{}" });
  status.textContent = `Expiry pass: ${JSON.stringify(result)}`;
  await refresh();
}

async function backfillDrafts() {
  const status = document.getElementById("scan-status");
  status.hidden = false;
  const result = await api("/api/backfill-drafts", { method: "POST", body: "{}" });
  status.textContent = `Backfilled ${result.drafts_created} drafts`;
  await refresh();
}

async function refresh() {
  const [health, kpis, integ] = await Promise.all([
    api("/api/health"),
    api("/api/kpis"),
    api("/api/integrations"),
  ]);
  document.getElementById("health-line").textContent =
    `${health.app} v${health.version} · ${health.brand || "Intellytics"} · Camoufox ${health.camoufox_enabled ? "on" : "off"} · ${new Date().toLocaleTimeString()}`;
  renderRunner(health);
  document.getElementById("empty-state").hidden = !kpis.empty;
  renderKpis(kpis);
  renderPlatformChips(kpis.platforms || {});
  renderActionQueue(kpis.action_queue || []);
  renderCharts(kpis);
  renderScans(kpis.recent_scans || []);
  renderIntegrations(integ.items || []);
  await loadLeads();
}

document.getElementById("btn-refresh").addEventListener("click", refresh);
document.getElementById("btn-scan").addEventListener("click", runScan);
document.getElementById("btn-cleanup").addEventListener("click", cleanupLeads);
document.getElementById("btn-expire").addEventListener("click", expireStale);
document.getElementById("btn-backfill").addEventListener("click", backfillDrafts);
["filter-stage", "min-score", "revenue-only"].forEach((id) => {
  document.getElementById(id).addEventListener("change", loadLeads);
});
document.querySelectorAll(".kind-tabs .chip").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".kind-tabs .chip").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    activeKind = btn.dataset.kind || "";
    loadLeads();
  });
});

refresh().catch((err) => {
  document.getElementById("scan-status").hidden = false;
  document.getElementById("scan-status").textContent = `Failed: ${err.message}`;
});
setInterval(() => refresh().catch(() => {}), 60_000);
