// A file:// page has an empty hostname, not "localhost" — so this must also
// catch that case, or every fetch silently points at the wrong place.
const API_BASE = (window.location.protocol === "file:" ||
                   window.location.hostname === "localhost" ||
                   window.location.hostname === "127.0.0.1")
  ? "http://127.0.0.1:8000"
  : ""; // same-origin if the frontend is ever served behind the API

const actionColor = { auto_close: "var(--teal)", review: "var(--amber)", escalate: "var(--coral)", abstain: "var(--slate)" };
const actionBg    = { auto_close: "var(--teal-bg)", review: "var(--amber-bg)", escalate: "var(--coral-bg)", abstain: "var(--slate-bg)" };

// --- Precedence trace (client-side, since it's a fixed rulebook, not per-case data) ---
const PRECEDENCE = [
  "missing_record", "duplicate_record", "partial_settlement",
  "multiple_possible_matches", "amount_issue", "date_issue",
  "exact_match", "other_conflicting",
];

function buildTrace(category) {
  const fireIdx = PRECEDENCE.indexOf(category);
  return PRECEDENCE.map((name, i) => ({
    name,
    state: i < fireIdx ? "skip" : (i === fireIdx ? "fire" : "reach"),
  }));
}

let currentAction = "all";

async function api(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

function showView(view) {
  document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t.dataset.view === view));
  document.getElementById("queue-view").classList.toggle("hidden", view !== "queue");
  document.getElementById("detail-view").classList.toggle("hidden", view !== "detail");
  document.getElementById("benchmark-view").classList.toggle("hidden", view !== "benchmark");
}

async function loadContextStrip() {
  const summary = await api("/api/queue/summary");
  const by = summary.by_action;
  document.getElementById("context-strip").innerHTML = `
    <span><b>${summary.total_cases}</b> cases</span>
    <span><b>₹${summary.value_in_exceptions.toLocaleString("en-IN")}</b> in exceptions</span>
    <span>${by.auto_close || 0} auto-closed</span>
    <span>${by.review || 0} review</span>
    <span>${by.escalate || 0} escalate</span>
    <span>${by.abstain || 0} abstain</span>
  `;
}

async function loadQueue(action = "all") {
  currentAction = action;
  const chips = ["all", "auto_close", "review", "escalate", "abstain"];
  document.getElementById("action-filters").innerHTML = chips.map(a => `
    <div class="filter-chip ${a === action ? "active" : ""}" data-action="${a}">${a.replace("_", " ")}</div>
  `).join("");
  document.querySelectorAll(".filter-chip").forEach(el => {
    el.onclick = () => loadQueue(el.dataset.action);
  });

  const cases = await api(action === "all" ? "/api/cases" : `/api/cases?action=${action}`);
  document.getElementById("queue-list").innerHTML = cases.map(c => `
    <div class="queue-row" data-order-id="${c.order_id || ''}">
      <span class="id mono">${c.order_id || '(orphan settlement)'}</span>
      <span class="cat">${c.predicted_category}</span>
      <span class="amt">₹${c.settled_amount.toLocaleString("en-IN")}</span>
      <span class="pill ${c.action}">${c.action.replace('_',' ')}</span>
    </div>
  `).join("");
  document.querySelectorAll(".queue-row").forEach(row => {
    row.onclick = () => row.dataset.orderId && openCase(row.dataset.orderId);
  });
}

async function openCase(orderId) {
  const detail = await api(`/api/cases/${orderId}`);
  showView("detail");
  renderDetail(detail);
}

function renderDetail(detail) {
  const { order, settlements, verdict } = detail;
  const action = verdict.action;

  document.getElementById("left").innerHTML = `
    <div class="back-link" id="back-to-queue">&larr; Back to queue</div>
    <div class="case-head">
      <div>
        <div class="ids mono">${order.order_id}</div>
        <div class="customer">${order.customer_name}</div>
      </div>
      <span class="pill ${action}">${action.replace('_',' ')}</span>
    </div>
    <div class="ledger">
      <div class="col">
        <h4>Order</h4>
        <div class="row"><span class="k">Amount</span><span class="v mono">₹${order.order_amount.toLocaleString("en-IN")}</span></div>
        <div class="row"><span class="k">Date</span><span class="v mono">${order.order_date}</span></div>
        <div class="row"><span class="k">Currency</span><span class="v mono">${order.currency}</span></div>
        <div class="row"><span class="k">Status</span><span class="v mono">${order.order_status}</span></div>
      </div>
      <div class="col">
        <h4>Settlement${settlements.length !== 1 ? 's' : ''}</h4>
        ${settlements.length === 0
          ? `<div class="row"><span class="k">—</span><span class="v">No settlement found</span></div>`
          : settlements.map(s => `
              <div class="row"><span class="k">${s.txn_id}</span><span class="v mono">₹${s.gross_amount.toLocaleString("en-IN")} · ${s.settlement_date}</span></div>
            `).join('')}
      </div>
    </div>
    <div class="verdict">
      <div class="verdict-top">
        <span class="verdict-cat mono">${verdict.predicted_category}</span>
        <div class="confidence-track"><div class="confidence-fill" style="width:${(verdict.confidence||0)*100}%; background:${actionColor[action]}"></div></div>
        <span class="confidence-label">${Math.round((verdict.confidence||0)*100)}% conf.</span>
      </div>
      <div class="reason">${verdict.reason}</div>
    </div>
  `;
  document.getElementById("back-to-queue").onclick = () => { showView("queue"); loadQueue(currentAction); };

  const trace = buildTrace(verdict.predicted_category);
  document.getElementById("trace").innerHTML = `
    <div class="trace-title">Precedence trace</div>
    <div class="trace-sub">Rules checked top to bottom; the first match wins.</div>
    ${trace.map((r, i) => `
      <div class="rule ${r.state === 'fire' ? 'fired' : ''}" ${r.state === 'fire' ? `style="background:${actionBg[action]}"` : ''}>
        <div class="num mono">${i+1}</div>
        <div>
          <div class="name">${r.name}</div>
          ${r.state === 'fire' ? `<div class="note">${verdict.reason}</div>` : ''}
        </div>
      </div>
    `).join('')}
    <div class="footnote" style="margin-top:16px; font-size:12px; color:var(--muted2);">
      Deterministic rules engine — see RULES_ENGINE_SPEC.md
    </div>
  `;
}

async function loadBenchmark() {
  const result = await api("/api/benchmark");
  const cats = Object.entries(result.per_category_accuracy).sort();
  document.getElementById("benchmark-content").innerHTML = `
    <div class="bench-grid">
      <div class="bench-stat"><div class="num">${(result.category_accuracy*100).toFixed(1)}%</div><div class="label">Category accuracy</div></div>
      <div class="bench-stat"><div class="num">${(result.hallucination_rate*100).toFixed(1)}%</div><div class="label">Hallucination rate</div></div>
      <div class="bench-stat"><div class="num">${(result.action_policy_miss_rate*100).toFixed(1)}%</div><div class="label">Action-policy misses</div></div>
    </div>
    <div class="trace-title">Per-category accuracy (${result.n_cases} cases)</div>
    ${cats.map(([cat, acc]) => `
      <div class="bench-cat-row">
        <span class="mono">${cat}</span>
        <div class="bar-track"><div class="bar-fill" style="width:${acc*100}%"></div></div>
        <span class="mono">${(acc*100).toFixed(1)}%</span>
      </div>
    `).join('')}
  `;
}

document.querySelectorAll(".tab").forEach(tab => {
  tab.onclick = () => {
    const view = tab.dataset.view;
    showView(view);
    if (view === "benchmark") loadBenchmark();
    if (view === "queue") loadQueue(currentAction);
  };
});

loadContextStrip().catch(showApiError);
loadQueue().catch(showApiError);

function showApiError(err) {
  console.error(err);
  document.getElementById("context-strip").innerHTML =
    `<span style="color:var(--coral)">Can't reach the API at ${API_BASE}. ` +
    `Is <code>uvicorn backend.main:app --reload</code> running?</span>`;
  document.getElementById("queue-list").innerHTML = "";
}
