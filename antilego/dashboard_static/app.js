let csrfToken = "";
let latestStatus = null;
let toastTimer = null;
let lastNotificationId = null;
const selectedEventIds = new Set();
const lawDescriptions = {
  deadline_nesting: "For an event that happens by a deadline, an earlier date cannot be more likely than a later date.",
  survival_deadline_nesting: "For an ongoing state, continuing through an earlier date cannot be less likely than continuing through a later date.",
  threshold_chain: "An easier threshold must be at least as likely as every harder threshold after it.",
  exhaustive_outcomes: "Mutually exclusive outcomes that cover every possibility should total 100%, with a 3% tolerance.",
  mutually_exclusive: "Exactly one outcome can occur, so the complete outcome set should total 100%, with a 3% tolerance.",
  complements: "An event and its exact opposite should add to 100%.",
  non_exhaustive_exclusivity: "Outcomes cannot happen together, so their combined probability cannot exceed 100%.",
  logical_implication: "If event A guarantees event B, A cannot be priced as more likely than B.",
};

const $ = (selector) => document.querySelector(selector);

function escapeHtml(value) {
  return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
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
  if (!value) return "Not scheduled";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not scheduled";
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
    if (family.liquidity_status === "illiquid") { label = "Illiquid"; statusClass = "illiquid"; }
    else if (family.data_complete === false) { label = "Incomplete"; statusClass = "incomplete"; }
    else if (family.coherent === true) { label = "Consistent"; statusClass = "good"; }
    else if (family.coherent === false) { label = "Violation"; statusClass = "bad"; }
    const signal = family.coherent === false ? `${family.violation_count} found` :
      family.liquidity_status === "illiquid" ? "Watching" : "-";
    const marketLink = family.polymarket_url
      ? `<a class="market-link" href="${escapeHtml(family.polymarket_url)}" target="_blank" rel="noopener noreferrer" aria-label="Open ${escapeHtml(family.name)} on Polymarket">View ↗</a>`
      : '<span class="market-link unavailable">-</span>';
    return `<div class="market-row" role="row">
      <span class="market-name"><strong>${escapeHtml(family.name)}</strong><small>${Math.round((family.confidence || 0) * 100)}% classification confidence</small></span>
      <span class="law-cell" tabindex="0" aria-label="${escapeHtml(lawDescriptions[family.type] || titleCase(family.type))}">
        <span class="law-name">${escapeHtml(titleCase(family.type))}</span>
        <span class="law-description">${escapeHtml(lawDescriptions[family.type] || "Probability consistency rule.")}</span>
      </span><span>${escapeHtml(family.market_count)}</span>
      <span class="status-pill ${statusClass}">${label}</span>
      <span class="signal ${family.coherent === false ? "bad" : ""}">${signal}</span>
      ${marketLink}
    </div>`;
  }).join("");
}

function renderApprovals(events) {
  const panel = $("#approval-panel");
  panel.hidden = !events.length;
  if (!events.length) return;
  const activeIds = new Set(events.map((event) => String(event.event_id)));
  [...selectedEventIds].forEach((id) => { if (!activeIds.has(id)) selectedEventIds.delete(id); });
  $("#approval-count").textContent = `${events.length} waiting`;
  $("#approval-list").innerHTML = events.map((event) => {
    const id = String(event.event_id);
    const confidence = Math.round((event.confidence || 0) * 100);
    const disabled = event.eligible ? "" : "disabled";
    const checked = selectedEventIds.has(id) ? "checked" : "";
    const warning = !event.eligible ? "No supported relationship" :
      event.requires_review || !event.meets_confidence ? "Review recommended" : "Ready to approve";
    return `<label class="approval-item ${event.eligible ? "" : "disabled"}">
      <input class="approval-checkbox" type="checkbox" value="${escapeHtml(id)}" ${disabled} ${checked} />
      <span class="approval-select" aria-hidden="true"></span>
      <span class="approval-copy"><strong>${escapeHtml(event.title)}</strong>
        <small>${escapeHtml(titleCase(event.law))} · ${event.contract_count} contracts · ${confidence}% confidence</small>
        <em>${escapeHtml(event.reason || "No classification explanation provided.")}</em></span>
      <span class="approval-status">${warning}</span>
    </label>`;
  }).join("");
  document.querySelectorAll(".approval-checkbox").forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) selectedEventIds.add(checkbox.value);
      else selectedEventIds.delete(checkbox.value);
      $("#approve-selected").disabled = selectedEventIds.size === 0;
    });
  });
  $("#approve-selected").disabled = selectedEventIds.size === 0;
  $("#approve-all").disabled = !events.some((event) => event.eligible);
}

function drawChart(canvas, family) {
  const rect = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.floor(rect.width * ratio));
  canvas.height = Math.max(1, Math.floor(rect.height * ratio));
  const ctx = canvas.getContext("2d");
  ctx.scale(ratio, ratio);
  const width = rect.width;
  const height = rect.height;
  const pad = { left: 42, right: 16, top: 20, bottom: 28 };
  const plotWidth = Math.max(1, width - pad.left - pad.right);
  const plotHeight = Math.max(1, height - pad.top - pad.bottom);
  const points = family.points || [];
  const probabilityMode = family.chart_mode === "market_probabilities";
  const multiSeriesMode = probabilityMode || family.chart_mode === "basket_totals";
  const isFiniteValue = (value) => value !== null && value !== "" && Number.isFinite(Number(value));
  const idealValue = Number(family.ideal_value) || 0;
  const seriesValues = (family.market_series || []).flatMap((series) => (series.points || []).filter((point) => isFiniteValue(point.value)).map((point) => Number(point.value)));
  const maxValue = probabilityMode ? 1 : Math.max(0.01, idealValue, ...points.map((point) => Number(point.value) || 0), ...seriesValues) * 1.12;
  const x = (index) => pad.left + (points.length <= 1 ? plotWidth / 2 : index * plotWidth / (points.length - 1));
  const y = (value) => pad.top + plotHeight - ((Number(value) || 0) / maxValue) * plotHeight;

  ctx.strokeStyle = "rgba(214,238,225,.12)";
  ctx.fillStyle = "#7f9187";
  ctx.font = "11px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
  for (let row = 0; row <= 3; row += 1) {
    const py = pad.top + row * plotHeight / 3;
    ctx.beginPath(); ctx.moveTo(pad.left, py); ctx.lineTo(width - pad.right, py); ctx.stroke();
  }
  if (!probabilityMode) {
    if (family.chart_mode === "basket_totals" && Number.isFinite(Number(family.lower_bound)) && Number.isFinite(Number(family.upper_bound))) {
      const bandTop = y(family.upper_bound);
      const bandBottom = y(family.lower_bound);
      ctx.fillStyle = "rgba(66,220,143,.08)";
      ctx.fillRect(pad.left, bandTop, plotWidth, bandBottom - bandTop);
    }
    const idealY = y(idealValue);
    ctx.save();
    ctx.setLineDash([6, 5]);
    ctx.strokeStyle = "#42dc8f";
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(pad.left, idealY); ctx.lineTo(width - pad.right, idealY); ctx.stroke();
    ctx.restore();
    ctx.fillStyle = "#42dc8f";
    const idealText = `${(idealValue * 100).toFixed(0)}% ideal`;
    ctx.fillText(idealText, width - pad.right - ctx.measureText(idealText).width, Math.max(pad.top + 11, idealY - 6));
  }
  points.forEach((point, index) => {
    if (!point.violating) return;
    const start = index === 0 ? pad.left : (x(index - 1) + x(index)) / 2;
    const end = index === points.length - 1 ? width - pad.right : (x(index) + x(index + 1)) / 2;
    ctx.fillStyle = "rgba(237,106,106,.20)";
    ctx.fillRect(start, pad.top, end - start, plotHeight);
  });
  if (multiSeriesMode) {
    const palette = ["#f2f2f2", "#7aa2d6", "#d9a65a", "#83b99a", "#b49ac8", "#d47f7f", "#76b9c7", "#b7af72", "#9d9d9d", "#c28ca6"];
    (family.market_series || []).forEach((series, seriesIndex) => {
      if (!series.points?.length) return;
      if (probabilityMode) {
        let segment = [];
        const paintBand = () => {
          if (!segment.length) return;
          ctx.beginPath();
          segment.forEach((point, index) => {
            const px = x(Number.isInteger(point.index) ? point.index : index);
            if (index === 0) ctx.moveTo(px, y(point.buy_value)); else ctx.lineTo(px, y(point.buy_value));
          });
          [...segment].reverse().forEach((point, reverseIndex) => {
            const index = segment.length - 1 - reverseIndex;
            ctx.lineTo(x(Number.isInteger(point.index) ? point.index : index), y(point.sell_value));
          });
          ctx.closePath();
          ctx.globalAlpha = .12;
          ctx.fillStyle = palette[seriesIndex % palette.length];
          ctx.fill();
          ctx.globalAlpha = 1;
          segment = [];
        };
        series.points.forEach((point) => {
          if (isFiniteValue(point.buy_value) && isFiniteValue(point.sell_value)) segment.push(point);
          else paintBand();
        });
        paintBand();
      }
      ctx.beginPath();
      let drawing = false;
      series.points.forEach((point, index) => {
        if (!isFiniteValue(point.value)) { drawing = false; return; }
        const px = x(Number.isInteger(point.index) ? point.index : index);
        if (!drawing) { ctx.moveTo(px, y(point.value)); drawing = true; }
        else ctx.lineTo(px, y(point.value));
      });
      ctx.strokeStyle = palette[seriesIndex % palette.length];
      ctx.lineWidth = seriesIndex === 0 ? 2 : 1.5;
      ctx.stroke();
    });
  } else if (points.length) {
    ctx.beginPath();
    points.forEach((point, index) => {
      if (index === 0) ctx.moveTo(x(index), y(point.value));
      else ctx.lineTo(x(index), y(point.value));
    });
    ctx.strokeStyle = "#ffffff"; ctx.lineWidth = 2; ctx.stroke();
  }
  ctx.fillStyle = "#7f9187";
  ctx.fillText(probabilityMode ? "100%" : `${(maxValue * 100).toFixed(1)}%`, 4, pad.top + 4);
  if (probabilityMode) ctx.fillText("50%", 9, pad.top + plotHeight / 2 + 4);
  ctx.fillText("0%", 15, pad.top + plotHeight + 4);
  if (points.length) {
    ctx.fillText(formatTime(points[0].timestamp), pad.left, height - 7);
    const endLabel = formatTime(points[points.length - 1].timestamp);
    const textWidth = ctx.measureText(endLabel).width;
    ctx.fillText(endLabel, width - pad.right - textWidth, height - 7);
  }
}

function renderLiveCharts(history) {
  const container = $("#graph-grid");
  const families = history?.families || [];
  if (!families.length) {
    container.innerHTML = '<div class="empty-state">The live charts will appear after the first snapshot.</div>';
    return;
  }
  const signature = families.map((family) => `${family.name}:${family.points.length}:${family.market_series?.length || 0}:${family.points.at(-1)?.timestamp}`).join("|");
  if (container.dataset.signature === signature) return;
  container.dataset.signature = signature;
  container.innerHTML = families.map((family, index) => {
    const latest = family.points.at(-1) || {};
    const chartLabel = latest.complete === false ? "No executable quote" : latest.violating ? "Violation" : "Consistent";
    const chartClass = latest.complete === false ? "illiquid" : latest.violating ? "bad" : "good";
    const probabilityMode = family.chart_mode === "market_probabilities";
    const multiSeriesMode = probabilityMode || family.chart_mode === "basket_totals";
    const palette = ["#f2f2f2", "#7aa2d6", "#d9a65a", "#83b99a", "#b49ac8", "#d47f7f", "#76b9c7", "#b7af72", "#9d9d9d", "#c28ca6"];
    const legendSeries = multiSeriesMode ? (family.market_series || []) : [{ label: family.metric_label, points: family.points || [] }];
    const legend = `<div class="chart-legend">${legendSeries.map((series, seriesIndex) => {
      const last = series.points?.at(-1);
      const value = last && last.value !== null && last.value !== "" && Number.isFinite(Number(last.value)) ? `${(Number(last.value) * 100).toFixed(1)}%` : "-";
      const colorClass = `series-${seriesIndex % palette.length}`;
      return `<span class="${colorClass}"><i></i>${escapeHtml(series.label)} <b>${value}</b></span>`;
    }).join("")}</div>`;
    const latestText = multiSeriesMode ? family.ideal_label : `latest ${((Number(latest.value) || 0) * 100).toFixed(1)}%`;
    const crossings = probabilityMode ? (family.latest_violations || []).filter((item) => item.left && item.right).map((item) => `${item.left} ↔ ${item.right} (${(Number(item.magnitude) * 100).toFixed(1)}%)`) : [];
    const crossingNote = crossings.length ? `<p class="chart-alert">Executable crossing: ${escapeHtml(crossings.join(", "))}</p>` : "";
    return `<article class="live-chart-card">
      <div><strong>${escapeHtml(family.name)}</strong><span class="status-pill ${chartClass}">${chartLabel}</span></div>
      <small>${escapeHtml(titleCase(family.law))} · ${escapeHtml(family.metric_label)} · ${escapeHtml(latestText)}</small>
      ${legend}
      ${crossingNote}
      <canvas data-chart-index="${index}" aria-label="${probabilityMode ? "Contract probability" : "Violation"} history for ${escapeHtml(family.name)}"></canvas>
      ${latest.violating && latest.complete !== false ? `<div class="chart-actions"><a class="analyze-button" href="/analysis.html?family=${encodeURIComponent(family.name)}" target="_blank" rel="noopener">Analyze <span>↗</span></a></div>` : ""}
    </article>`;
  }).join("");
  container.querySelectorAll("canvas").forEach((canvas) => drawChart(canvas, families[Number(canvas.dataset.chartIndex)]));
}

function renderNotifications(notifications) {
  if (!notifications?.length) return;
  const newest = notifications[notifications.length - 1];
  if (lastNotificationId === null) { lastNotificationId = newest.id; return; }
  const fresh = notifications.filter((item) => item.id > lastNotificationId);
  fresh.forEach((item) => {
    showToast(item.message, true);
    if ("Notification" in window && Notification.permission === "granted") {
      new Notification(item.title, { body: item.message });
    }
  });
  lastNotificationId = newest.id;
}

function render(status) {
  latestStatus = status;
  csrfToken = status.csrf_token || csrfToken;
  const running = status.monitor.state === "running";
  const discovering = status.discovery.state === "running";
  const errors = [status.discovery.state, status.monitor.state, status.graphs.state].includes("error");
  const connected = Boolean(status.chatgpt?.connected);
  document.body.classList.toggle("is-running", running || discovering);
  document.body.classList.toggle("has-error", errors);
  $("#hero-status").textContent = errors ? "Action needed" : running ? "Monitoring live" : discovering ? "Discovering" : connected ? "Ready" : "Connect ChatGPT";
  $("#hero-message").textContent = status.monitor.state === "error" ? status.monitor.message : status.discovery.state === "error" ? status.discovery.message : running ? status.monitor.message : status.discovery.message;
  const monitorLabel = titleCase(status.monitor.state);
  const monitorIcon = running
    ? '<span class="monitor-wave" aria-hidden="true"><i></i><i></i><i></i></span>'
    : status.monitor.state === "stopped"
      ? '<i class="monitor-stop-icon" aria-hidden="true"></i>'
      : "";
  $("#metric-monitor").innerHTML = `<span>${escapeHtml(monitorLabel)}</span>${monitorIcon}`;
  $("#metric-families").textContent = status.family_count;
  $("#metric-snapshot").textContent = formatTime(status.latest_snapshot_at);
  $("#metric-violations").textContent = status.latest_violation_count;
  $("#account-state").textContent = connected ? "Plan connected" : "Not connected";
  $("#account-state").classList.toggle("neutral", !connected);
  $("#account-message").textContent = status.chatgpt?.message || "Connect ChatGPT to enable discovery.";
  $("#account-email").textContent = connected && status.chatgpt.email ? `Connected as ${status.chatgpt.email} using ${status.chatgpt.model_display_name || status.chatgpt.model || "an account-selected model"}. Credentials are stored privately on this Mac.` : "No ChatGPT account connected.";
  $("#connect-chatgpt").disabled = connected || discovering;
  $("#disconnect-chatgpt").disabled = !connected || discovering;

  const active = discovering || status.discovery.state === "error" ? status.discovery : status.monitor;
  $("#activity-state").textContent = titleCase(active.state);
  $("#activity-message").textContent = active.message;
  const progress = discovering && status.discovery.total ? (status.discovery.processed / status.discovery.total) * 100 : discovering ? 18 : running ? 100 : 0;
  $("#activity-progress").style.width = `${progress}%`;
  $("#next-snapshot").textContent = formatTime(status.monitor.next_snapshot_at);
  $("#next-discovery").textContent = formatTime(status.discovery_schedule?.next_discovery_at);
  $("#data-location").textContent = status.archive_path.split("/").slice(-2).join("/");

  const nextReview = status.discovery_schedule?.next_discovery_at ? new Date(status.discovery_schedule.next_discovery_at) : null;
  const aiCooldown = nextReview && !Number.isNaN(nextReview.getTime()) && nextReview > new Date();
  $("#discover").disabled = discovering || !connected || status.pending_events.length > 0 || aiCooldown;
  $("#start-monitor").disabled = running || discovering || !status.family_count;
  $("#stop-monitor").disabled = !running;
  $("#clear-all").disabled = running || discovering;
  renderApprovals(status.pending_events || []);
  renderMarkets(status.monitored_families);
  renderLiveCharts(status.history);
  renderNotifications(status.notifications);
}

async function refresh() {
  try { render(await request("/api/status")); }
  catch (error) { showToast(error.message, true); }
}

async function action(path, body, successMessage) {
  try {
    const payload = await request(path, { method: "POST", body: JSON.stringify(body || {}) });
    render({ ...payload.status, csrf_token: csrfToken });
    if (successMessage) showToast(successMessage);
    return true;
  } catch (error) { showToast(error.message, true); return null; }
}

$("#connect-chatgpt").addEventListener("click", async () => {
  try {
    const payload = await request("/api/chatgpt/connect", { method: "POST", body: "{}" });
    window.location.assign(payload.authorization_url);
  } catch (error) { showToast(error.message, true); }
});
$("#disconnect-chatgpt").addEventListener("click", () => action("/api/chatgpt/disconnect", {}, "ChatGPT disconnected from Antilego."));
$("#discover").addEventListener("click", () => action("/api/discover", { limit: Number($("#discovery-limit").value), minimum_confidence: Number($("#confidence").value) }, "Discovery started. Results will wait for your approval."));
$("#start-monitor").addEventListener("click", () => action("/api/monitor/start", { interval_minutes: Number($("#interval").value) }, "Monitoring started on a fixed three-minute cadence."));
$("#stop-monitor").addEventListener("click", () => action("/api/monitor/stop", {}, "Monitoring is stopping."));
$("#approve-selected").addEventListener("click", async () => {
  if (await action("/api/discovery/approve", { event_ids: [...selectedEventIds] }, "Approval review complete. Families without executable quotes were skipped.")) selectedEventIds.clear();
});
$("#approve-all").addEventListener("click", () => action("/api/discovery/approve-all", {}, "Approval review complete. Families without executable quotes were skipped."));
$("#dismiss-approval").addEventListener("click", () => action("/api/discovery/dismiss", {}, "Remaining discoveries dismissed."));
$("#enable-notifications").addEventListener("click", async () => {
  if (!("Notification" in window)) { showToast("Browser notifications are not supported here.", true); return; }
  const permission = await Notification.requestPermission();
  $("#enable-notifications").textContent = permission === "granted" ? "Browser alerts enabled" : "Enable browser alerts";
  showToast(permission === "granted" ? "Browser violation alerts enabled." : "Notification permission was not granted.", permission !== "granted");
});
$("#clear-all").addEventListener("click", async () => {
  const confirmed = window.confirm(
    "Reset discovered events, monitored markets, and the live dashboard? Existing snapshots, reports, and graph files will remain in the archive folder."
  );
  if (!confirmed) return;
  selectedEventIds.clear();
  await action("/api/clear-all", {}, "Dashboard reset. Existing archive files were preserved.");
});
$("#open-folder").addEventListener("click", () => action("/api/open-folder", {}, "Opened the weekly data folder."));
$("#quit-app").addEventListener("click", async () => {
  await action("/api/quit", {}, "Antilego has stopped. You may close this tab.");
  setTimeout(() => { document.body.innerHTML = '<main style="padding:12vh 8vw"><p class="eyebrow">Antilego stopped</p><h1>You can close this tab.</h1></main>'; }, 300);
});

if ("Notification" in window && Notification.permission === "granted") $("#enable-notifications").textContent = "Browser alerts enabled";
refresh();
setInterval(refresh, 2000);
