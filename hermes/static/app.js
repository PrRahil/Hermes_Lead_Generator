const money = (n) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(n || 0);

const charts = {};
let selectedLeadId = null;

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json();
}

function scoreClass(score) {
  if (score >= 75) return "high";
  if (score < 45) return "low";
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
    `${state} · cycle ${r.cycle || 0} · ${r.message || "Start with python -m hermes run"}` +
    (r.current_query ? ` · topic: ${r.current_query}` : "");
}

function renderKpis(data) {
  const t = data.totals || {};
  const c = data.conversion || {};
  const cards = [
    ["Strong leads", `${t.strong_leads ?? 0} / ${t.strong_lead_target ?? 50}`, `Score ≥ ${t.strong_lead_min_score ?? 70}`],
    ["Active leads", t.active_leads ?? t.leads ?? 0, `${t.companies || 0} companies`],
    ["Hot leads (75+)", t.hot_leads ?? 0, `Avg fit ${t.avg_fit_score ?? 0}`],
    ["ICP revenue-fit", `${t.icp_pass_rate ?? 0}%`, `${t.revenue_fit ?? 0} passed income gate`],
    ["Pipeline value", money(t.pipeline_value), `Weighted ${money(t.weighted_pipeline)}`],
    ["Avg deal size", money(t.avg_deal_value), `${t.open_deals || 0} open deals`],
    ["Ready to send", t.ready_to_send ?? t.outreach_drafts ?? 0, "Template drafts (min LLM)"],
    ["Won revenue", money(t.won_value), `${t.won_deals || 0} closed · reply→won ${c.reply_to_won || 0}%`],
  ];
  document.getElementById("kpi-grid").innerHTML = cards
    .map(
      ([label, value, hint]) => `
      <div class="kpi">
        <div class="label">${label}</div>
        <div class="value">${value}</div>
        <div class="hint">${hint}</div>
      </div>`
    )
    .join("");
}

function renderActionQueue(items) {
  const el = document.getElementById("action-queue");
  if (!items || !items.length) {
    el.innerHTML = `<div class="muted">No prioritized actions yet — leave continuous hunt running.</div>`;
    return;
  }
  el.innerHTML = items
    .map(
      (l) => `
      <div class="action-row" data-id="${l.id}">
        <span class="score-pill ${scoreClass(l.fit_score)}">${l.fit_score}</span>
        <div>
          <strong>${l.company?.name || "Unknown"}</strong>
          <div class="muted">${l.contact?.title || "—"} · ${l.company?.revenue_band || "rev?"}</div>
        </div>
        <div>${(l.project_summary || l.source_title || "").slice(0, 110)}</div>
        <span class="badge">${l.source_platform}</span>
        <span class="badge">${l.stage}</span>
        <strong>${money(l.estimated_deal_value)}</strong>
      </div>`
    )
    .join("");
  el.querySelectorAll(".action-row").forEach((row) => {
    row.addEventListener("click", () => openLead(Number(row.dataset.id)));
  });
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
    data: {
      labels: platforms,
      datasets: [{ data: platforms.map((p) => data.platforms[p]), backgroundColor: palette }],
    },
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
  if (!scans.length) {
    el.innerHTML = `<div class="muted">No cycles yet.</div>`;
    return;
  }
  el.innerHTML = scans
    .map(
      (s) => `
      <div class="scan-row">
        <strong>#${s.id}</strong>
        <div>${s.status} · ${s.signals_found} signals · ${s.leads_created} new · ${s.qualified} qualified · ${s.outreach_drafted} drafts</div>
        <div class="muted">${s.started_at ? new Date(s.started_at).toLocaleString() : ""}</div>
      </div>`
    )
    .join("");
}

async function loadLeads() {
  const stage = document.getElementById("filter-stage").value;
  const platform = document.getElementById("filter-platform").value;
  const minScore = document.getElementById("min-score").value || 0;
  const revenueOnly = document.getElementById("revenue-only").checked;
  const params = new URLSearchParams({
    min_score: String(minScore),
    revenue_fit_only: String(revenueOnly),
  });
  if (stage) params.set("stage", stage);
  if (platform) params.set("platform", platform);
  const data = await api(`/api/leads?${params.toString()}`);
  const tbody = document.querySelector("#leads-table tbody");
  if (!data.items.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="muted">No leads yet — start continuous hunt.</td></tr>`;
    return;
  }
  tbody.innerHTML = data.items
    .map((l) => {
      const req = (l.project_summary || l.source_title || "").slice(0, 90);
      return `
      <tr data-id="${l.id}" class="${selectedLeadId === l.id ? "active" : ""}">
        <td><span class="score-pill ${scoreClass(l.fit_score)}">${l.fit_score}</span></td>
        <td>
          <div>${l.company?.name || "—"}</div>
          <div class="muted">${l.contact?.title || ""} ${l.company?.revenue_band ? "· " + l.company.revenue_band : ""}</div>
        </td>
        <td>${req}</td>
        <td><span class="badge">${l.source_platform}</span></td>
        <td>${l.stage}</td>
        <td>${money(l.estimated_deal_value)}</td>
        <td><button class="btn tiny ghost">Open</button></td>
      </tr>`;
    })
    .join("");

  tbody.querySelectorAll("tr").forEach((tr) => {
    tr.addEventListener("click", () => openLead(Number(tr.dataset.id)));
  });
}

async function openLead(id) {
  selectedLeadId = id;
  const lead = await api(`/api/leads/${id}`);
  const body = document.getElementById("detail-body");
  const outreach = (lead.outreach && lead.outreach[0]) || null;
  body.innerHTML = `
    <div class="company">${lead.company?.name || "Unknown"}</div>
    <div class="muted">${lead.company?.industry || ""} · ${lead.company?.location || "—"} · emp ${lead.company?.employee_count ?? "?"} · rev ${lead.company?.revenue_usd != null ? money(lead.company.revenue_usd) : "unknown"}</div>
    <p>${lead.project_summary || lead.source_snippet || ""}</p>
    <div><span class="badge">${lead.source_platform}</span> <span class="badge">${lead.stage}</span> <span class="badge">${lead.confidence}</span></div>
    ${lead.source_url ? `<p><a href="${lead.source_url}" target="_blank" rel="noreferrer" style="color:#3db8a0">Source post</a></p>` : ""}

    <h3>Staff / buyer</h3>
    <p>${lead.contact?.full_name || "—"} · ${lead.contact?.title || "—"}<br/>
    <span class="muted">${lead.contact?.email || "no email"} (${lead.contact?.email_status || "n/a"})</span></p>

    <h3>Why this scored</h3>
    <ul class="reasons">${(lead.score_reasons || []).map((r) => `<li>${r}</li>`).join("") || "<li class='muted'>No reasons</li>"}</ul>

    <h3>Deal desk</h3>
    <p>${lead.deal ? `${money(lead.deal.value_usd)} · p=${Math.round((lead.deal.probability || 0) * 100)}% · ${lead.deal.next_step || ""}` : "No deal yet"}</p>

    <h3>Outreach draft</h3>
    ${
      outreach
        ? `<div class="muted">A/B subjects</div>
           <div><strong>A:</strong> ${outreach.subject_a || ""}</div>
           <div><strong>B:</strong> ${outreach.subject_b || ""}</div>
           <div class="outreach">${outreach.body || ""}</div>`
        : `<p class="muted">No draft yet.</p>`
    }

    <div class="stage-actions">
      ${["qualified", "outreach", "replied", "negotiation", "won", "lost"]
        .map((s) => `<button class="btn tiny" data-stage="${s}">Mark ${s}</button>`)
        .join("")}
    </div>
  `;

  body.querySelectorAll("[data-stage]").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      await api(`/api/leads/${id}/stage`, {
        method: "POST",
        body: JSON.stringify({ stage: btn.dataset.stage, note: `Dashboard moved to ${btn.dataset.stage}` }),
      });
      await refresh();
      await openLead(id);
    });
  });

  document.querySelectorAll("#leads-table tr").forEach((tr) => {
    tr.classList.toggle("active", Number(tr.dataset.id) === id);
  });
}

async function runScan() {
  const status = document.getElementById("scan-status");
  status.hidden = false;
  status.textContent = "One-shot scan…";
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
    status.textContent =
      `Done — ${result.signals_found} signals, ${result.leads_created} new, ` +
      `${result.leads_skipped_existing || 0} dupes · strong ${result.strong_leads ?? "?"} ` +
      (result.hint || "");
    await refresh();
  } catch (err) {
    status.textContent = `Scan failed: ${err.message}`;
  }
}

async function cleanupLeads() {
  const mode = window.confirm("Delete ALL leads (recommended before a real 24h hunt)?\nOK = wipe all\nCancel = abort")
    ? "all"
    : null;
  if (!mode) return;
  const again = window.confirm("Final confirm: wipe the local CRM database leads?");
  if (!again) return;
  const status = document.getElementById("scan-status");
  status.hidden = false;
  status.textContent = "Cleaning…";
  try {
    const result = await api("/api/cleanup", {
      method: "POST",
      body: JSON.stringify({ mode }),
    });
    status.textContent = `Cleanup done: ${JSON.stringify(result.deleted)}`;
    selectedLeadId = null;
    document.getElementById("detail-body").innerHTML = "";
    await refresh();
  } catch (err) {
    status.textContent = `Cleanup failed: ${err.message}`;
  }
}

async function refresh() {
  const [health, kpis] = await Promise.all([api("/api/health"), api("/api/kpis")]);
  const llm = health.llm_enabled
    ? `${health.llm_provider || "llm"} key present (outreach rewrite OFF unless enabled)`
    : "templates only";
  document.getElementById("health-line").textContent =
    `${health.app} v${health.version} · ${llm} · refreshed ${new Date().toLocaleTimeString()}`;
  renderRunner(health);
  document.getElementById("empty-state").hidden = !kpis.empty;
  renderKpis(kpis);
  renderActionQueue(kpis.action_queue || kpis.top_leads || []);
  renderCharts(kpis);
  renderScans(kpis.recent_scans || []);
  await loadLeads();
}

document.getElementById("btn-refresh").addEventListener("click", refresh);
document.getElementById("btn-scan").addEventListener("click", runScan);
document.getElementById("btn-cleanup").addEventListener("click", cleanupLeads);
["filter-stage", "filter-platform", "min-score", "revenue-only"].forEach((id) => {
  document.getElementById(id).addEventListener("change", loadLeads);
});

refresh().catch((err) => {
  document.getElementById("scan-status").hidden = false;
  document.getElementById("scan-status").textContent = `Failed to load: ${err.message}`;
});

// Live desk: pull new leads every minute while page is open
setInterval(() => {
  refresh().catch(() => {});
}, 60_000);
