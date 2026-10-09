let csrfToken = "";
let latestStatus = null;
let toastTimer = null;

const $ = (selector) => document.querySelector(selector);

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function titleCase(value) {
  return String(value || "unknown").replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function showToast(message, error = false) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.toggle("error", error);
  toast.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("visible"), 3600);
}

async function request(path, options = {}) {
  const init = { ...options, headers: { "Content-Type": "application/json", ...(options.headers || {}) } };
  if (init.method === "POST") init.headers["X-Antilego-Token"] = csrfToken;
  const response = await fetch(path, init);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "Antilego could not complete that action.");
  return payload;
}

function formatTime(value) {
  if (!value) return "None yet";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "None yet";
  return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" });
}

function renderMarkets(families) {
  const container = $("#market-rows");
  if (!families.length) {
    container.innerHTML = '<div class="empty-state">No approved families yet. Discover markets to begin.</div>';
    return;
  }
  container.innerHTML = families.map((family) => {
    let label = "Waiting";
    let statusClass = "";
    if (family.data_complete === false) { label = "Incomplete"; statusClass = "incomplete"; }
    else if (family.coherent === true) { label = "Consistent"; statusClass = "good"; }
    else if (family.coherent === false) { label = "Violation"; statusClass = "bad"; }
    const signal = family.coherent === false ? `${family.violation_count} found` : "-";
    const signalClass = family.coherent === false ? "signal bad" : "signal";
    return `
      <div class="market-row" role="row">
        <span class="market-name"><strong>${escapeHtml(family.name)}</strong><small>${Math.round((family.confidence || 0) * 100)}% classification confidence</small></span>
        <span>${escapeHtml(titleCase(family.type))}</span>
        <span>${escapeHtml(family.market_count)}</span>
        <span class="status-pill ${statusClass}">${label}</span>
        <span class="${signalClass}">${signal}</span>
      </div>`;
  }).join("");
}

function renderGraphs(graphs) {
  $("#graphs-message").textContent = graphs.message;
  const container = $("#graph-grid");
  container.innerHTML = graphs.items.map((figure) => `
    <figure class="graph-card">
      <a href="${escapeHtml(figure.url)}" target="_blank" rel="noreferrer"><img src="${escapeHtml(figure.url)}" alt="${escapeHtml(figure.name)}" /></a>
      <figcaption>${escapeHtml(figure.name)}</figcaption>
    </figure>`).join("");
}

function render(status) {
  latestStatus = status;
  csrfToken = status.csrf_token || csrfToken;
  const running = status.monitor.state === "running";
  const discovering = status.discovery.state === "running";
  const graphing = status.graphs.state === "running";
  const discoveryError = status.discovery.state === "error";
  const monitorError = status.monitor.state === "error";
  const graphError = status.graphs.state === "error";
  const connected = Boolean(status.chatgpt?.connected);
  document.body.classList.toggle("is-running", running || discovering || graphing);
  document.body.classList.toggle("has-error", discoveryError || monitorError || graphError);

  $("#hero-status").textContent = discoveryError || monitorError || graphError
    ? "Action needed"
    : running ? "Monitoring live" : discovering ? "Discovering" : connected ? "Ready" : "Connect ChatGPT";
  $("#hero-message").textContent = discoveryError
    ? status.discovery.message
    : monitorError ? status.monitor.message
      : graphError ? status.graphs.message
        : running ? status.monitor.message : status.discovery.message;
  $("#metric-monitor").textContent = titleCase(status.monitor.state);
  $("#metric-families").textContent = status.family_count;
  $("#metric-snapshot").textContent = formatTime(status.latest_snapshot_at);
  $("#metric-violations").textContent = status.latest_violation_count;
  $("#account-state").textContent = connected ? "Plan connected" : "Not connected";
  $("#account-state").classList.toggle("neutral", !connected);
  $("#account-message").textContent = status.chatgpt?.message || "Connect ChatGPT to enable discovery.";
  $("#account-email").textContent = connected && status.chatgpt.email
    ? `Connected as ${status.chatgpt.email} using ${status.chatgpt.model_display_name || status.chatgpt.model || "an account-selected model"}. Credentials are stored privately on this Mac.`
    : "No ChatGPT account connected.";
  $("#connect-chatgpt").disabled = connected || discovering;
  $("#disconnect-chatgpt").disabled = !connected || discovering;

  const active = discovering || discoveryError
    ? status.discovery
    : graphing || graphError ? status.graphs : status.monitor;
  $("#activity-state").textContent = titleCase(active.state);
  $("#activity-message").textContent = active.message;
  const progress = discovering && status.discovery.total
    ? (status.discovery.processed / status.discovery.total) * 100
    : (discovering || graphing ? 18 : running ? 100 : 0);
  $("#activity-progress").style.width = `${progress}%`;
  $("#next-snapshot").textContent = status.monitor.next_snapshot_at ? formatTime(status.monitor.next_snapshot_at) : "Not scheduled";
  $("#data-location").textContent = status.archive_path.split("/").slice(-2).join("/");

  $("#discover").disabled = discovering || graphing || !connected;
  $("#start-monitor").disabled = running || discovering || graphing || !status.family_count;
  $("#stop-monitor").disabled = !running;
  $("#generate-graphs").disabled = graphing || !status.latest_snapshot_at;

  renderMarkets(status.monitored_families);
  renderGraphs(status.graphs);
}

async function refresh() {
  try {
    const status = await request("/api/status");
    render(status);
  } catch (error) {
    showToast(error.message, true);
  }
}

async function action(path, body, successMessage) {
  try {
    const payload = await request(path, { method: "POST", body: JSON.stringify(body || {}) });
    render({ ...payload.status, csrf_token: csrfToken });
    if (successMessage) showToast(successMessage);
  } catch (error) {
    showToast(error.message, true);
    return null;
  }
  return true;
}

$("#connect-chatgpt").addEventListener("click", async () => {
  try {
    const payload = await request("/api/chatgpt/connect", { method: "POST", body: "{}" });
    window.location.assign(payload.authorization_url);
  } catch (error) {
    showToast(error.message, true);
  }
});

$("#disconnect-chatgpt").addEventListener("click", () => action(
  "/api/chatgpt/disconnect",
  {},
  "ChatGPT disconnected from Antilego.",
));

$("#discover").addEventListener("click", () => action("/api/discover", {
  limit: Number($("#discovery-limit").value),
  minimum_confidence: Number($("#confidence").value),
}, "Discovery started. You can leave this page open."));

$("#start-monitor").addEventListener("click", () => action("/api/monitor/start", {
  interval_minutes: Number($("#interval").value),
}, "Monitoring started."));

$("#stop-monitor").addEventListener("click", () => action("/api/monitor/stop", {}, "Monitoring is stopping."));
$("#generate-graphs").addEventListener("click", () => action("/api/graphs", {}, "Graph generation started."));
$("#open-folder").addEventListener("click", () => action("/api/open-folder", {}, "Opened the weekly data folder."));
$("#quit-app").addEventListener("click", async () => {
  await action("/api/quit", {}, "Antilego has stopped. You may close this tab.");
  setTimeout(() => { document.body.innerHTML = '<main style="padding:12vh 8vw"><p class="eyebrow">Antilego stopped</p><h1>You can close this tab.</h1></main>'; }, 300);
});

refresh();
setInterval(refresh, 2000);
