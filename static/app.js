"use strict";

// All user-controlled text is placed through textContent (not innerHTML).
// This local demonstration has no sign-in and should not be internet-facing.
const state = { selectedId: null, status: "", severity: "", search: "" };
const STATUSES = ["open", "investigating", "mitigated", "resolved"];
const PRIORITIES = ["P1", "P2", "P3", "P4"];
const TRANSITIONS = {
  open: ["investigating", "resolved"],
  investigating: ["mitigated", "resolved"],
  mitigated: ["investigating", "resolved"],
  resolved: ["investigating"],
};
const $ = (id) => document.getElementById(id);

async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    let error = data.detail || ("Request failed with HTTP " + response.status);
    if (Array.isArray(error)) error = error.map((item) => item.msg).join("; ");
    throw new Error(String(error));
  }
  return data;
}

function node(tag, className = "", content = "") {
  const element = document.createElement(tag);
  if (className) element.className = className;
  element.textContent = String(content);
  return element;
}

function localTime(value) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? "—"
    : parsed.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

let toastTimeout;
function toast(message) {
  const element = $("toast");
  element.textContent = message;
  element.classList.add("show");
  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => element.classList.remove("show"), 3200);
}

function renderBreakdown(target, values, labels, classes) {
  const parent = $(target);
  parent.replaceChildren();
  const total = Object.values(values).reduce((a, b) => a + Number(b || 0), 0);
  labels.forEach((label, index) => {
    const value = Number(values[label] || 0);
    const row = node("div", "breakdown-row");
    const name = node("label", "", label);
    const track = node("div", "track");
    const fill = node("div", "fill " + classes[index]);
    fill.style.width = (total > 0 ? (value / total) * 100 : 0) + "%";
    track.appendChild(fill);
    row.append(name, track, node("strong", "", value));
    parent.appendChild(row);
  });
}

function renderMetrics(data) {
  $("metricTotal").textContent = data.total;
  $("metricActive").textContent = data.active;
  $("metricResolved").textContent = data.resolved;
  $("metricMttr").textContent = data.mean_time_to_resolve_hours === null
    ? "—" : data.mean_time_to_resolve_hours + "h";
  renderBreakdown("statusBreakdown", data.by_status, STATUSES, STATUSES);

  const parent = $("priorityBreakdown");
  parent.replaceChildren();
  PRIORITIES.forEach((p) => {
    const card = node("div", "priority-box " + p.toLowerCase());
    card.append(node("strong", "", data.by_severity[p] || 0), node("small", "", p));
    parent.appendChild(card);
  });
}

function pill(value) {
  return node("span", "pill " + value.toLowerCase(), value);
}

function renderIncidents(data) {
  const body = $("incidentRows");
  body.replaceChildren();
  if (!data.items.length) {
    const tr = node("tr", "empty-row");
    const td = node("td", "empty", "No incidents match your filters. Create one to get started.");
    td.colSpan = 7;
    tr.appendChild(td);
    body.appendChild(tr);
  }

  data.items.forEach((item) => {
    const row = document.createElement("tr");
    const info = node("td");
    info.append(node("span", "incident-title", item.title), node("div", "incident-id", "INC-" + String(item.id).padStart(4, "0")));
    row.appendChild(info);
    row.appendChild(node("td", "", item.service));
    const severity = node("td");
    severity.appendChild(pill(item.severity));
    row.appendChild(severity);
    const status = node("td");
    status.appendChild(pill(item.status));
    row.appendChild(status);
    row.appendChild(node("td", "", item.owner || "Unassigned"));
    row.appendChild(node("td", "", localTime(item.created_at)));
    const action = node("td");
    const button = node("button", "row-open", "View ↗");
    button.type = "button";
    button.addEventListener("click", (event) => { event.stopPropagation(); openIncident(item.id); });
    action.appendChild(button);
    row.appendChild(action);
    row.tabIndex = 0;
    row.setAttribute("aria-label", "View incident " + item.id + ": " + item.title);
    row.addEventListener("click", () => openIncident(item.id));
    row.addEventListener("keydown", (event) => {
      if (event.target === row && (event.key === "Enter" || event.key === " ")) {
        event.preventDefault();
        openIncident(item.id);
      }
    });
    body.appendChild(row);
  });
  $("queueCount").textContent = data.total + " incident" + (data.total === 1 ? "" : "s") + " found";
}

async function refresh() {
  const params = new URLSearchParams();
  if (state.status) params.set("status", state.status);
  if (state.severity) params.set("severity", state.severity);
  if (state.search) params.set("q", state.search);
  try {
    const [metrics, incidents] = await Promise.all([
      request("/api/metrics"), request("/api/incidents?" + params.toString()),
    ]);
    renderMetrics(metrics);
    renderIncidents(incidents);
  } catch (error) {
    $("incidentRows").replaceChildren();
    const row = node("tr");
    const td = node("td", "empty", "Unable to load incidents: " + error.message);
    td.colSpan = 7;
    row.appendChild(td);
    $("incidentRows").appendChild(row);
    toast("Could not connect to the local dashboard API");
  }
}

async function openIncident(id) {
  state.selectedId = id;
  $("detailError").textContent = "";
  $("noteError").textContent = "";
  try {
    const [item, events] = await Promise.all([
      request("/api/incidents/" + id), request("/api/incidents/" + id + "/events"),
    ]);
    if (state.selectedId !== id) return;
    $("detailId").textContent = "INC-" + String(id).padStart(4, "0");
    $("detailTitle").textContent = item.title;
    $("detailDescription").textContent = item.description || "No description provided.";
    $("detailOwner").value = item.owner;
    $("detailService").value = item.service;
    $("detailSeverity").value = item.severity;

    const statusSelect = $("detailStatus");
    statusSelect.replaceChildren();
    [item.status, ...TRANSITIONS[item.status]].forEach((status) => {
      const option = node("option", "", status[0].toUpperCase() + status.slice(1));
      option.value = status;
      statusSelect.appendChild(option);
    });
    statusSelect.value = item.status;
    renderTimeline(events.items);
    $("detailDialog").showModal();
  } catch (error) {
    toast("Unable to load incident: " + error.message);
  }
}

function renderTimeline(events) {
  const parent = $("incidentTimeline");
  parent.replaceChildren();
  events.forEach((event) => {
    const entry = node("div", "timeline-item");
    entry.append(
      node("strong", "", event.event_type),
      node("p", "", event.detail),
      node("small", "", localTime(event.created_at)),
    );
    parent.appendChild(entry);
  });
  if (!events.length) parent.appendChild(node("p", "description", "No activity recorded yet."));
}

async function refreshIncidentDetail() {
  const id = state.selectedId;
  if (id === null) return;
  // Refresh the timeline and data without reopening an existing modal.
  const [item, events] = await Promise.all([
    request("/api/incidents/" + id), request("/api/incidents/" + id + "/events"),
  ]);
  $("detailStatus").replaceChildren();
  [item.status, ...TRANSITIONS[item.status]].forEach((status) => {
    const option = node("option", "", status[0].toUpperCase() + status.slice(1));
    option.value = status;
    $("detailStatus").appendChild(option);
  });
  $("detailStatus").value = item.status;
  $("detailSeverity").value = item.severity;
  $("detailOwner").value = item.owner;
  $("detailService").value = item.service;
  renderTimeline(events.items);
  await refresh();
}

document.querySelectorAll("[data-close]").forEach((button) => {
  button.addEventListener("click", () => $(button.dataset.close).close());
});

$("newIncident").addEventListener("click", () => {
  $("createError").textContent = "";
  $("createDialog").showModal();
});

$("createForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.currentTarget));
  const error = $("createError");
  error.textContent = "";
  try {
    const created = await request("/api/incidents", {
      method: "POST", body: JSON.stringify(data),
    });
    $("createForm").reset();
    $("createDialog").close();
    toast("Incident INC-" + String(created.id).padStart(4, "0") + " created");
    await refresh();
  } catch (exc) {
    error.textContent = exc.message;
  }
});

$("detailForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const id = state.selectedId;
  const changes = Object.fromEntries(new FormData(event.currentTarget));
  $("detailError").textContent = "";
  try {
    await request("/api/incidents/" + id, {
      method: "PATCH", body: JSON.stringify(changes),
    });
    toast("Incident updated");
    await refreshIncidentDetail();
  } catch (exc) {
    $("detailError").textContent = exc.message;
  }
});

$("noteForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const note = $("noteInput").value.trim();
  $("noteError").textContent = "";
  try {
    await request("/api/incidents/" + state.selectedId + "/notes", {
      method: "POST", body: JSON.stringify({ note }),
    });
    $("noteInput").value = "";
    await refreshIncidentDetail();
    toast("Timeline note added");
  } catch (exc) {
    $("noteError").textContent = exc.message;
  }
});

$("statusFilter").addEventListener("change", (event) => { state.status = event.target.value; refresh(); });
$("severityFilter").addEventListener("change", (event) => { state.severity = event.target.value; refresh(); });
let searchTimer;
$("searchInput").addEventListener("input", (event) => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => { state.search = event.target.value.trim(); refresh(); }, 250);
});
$("exportCsv").addEventListener("click", () => { window.location.href = "/api/export.csv"; });
refresh();
