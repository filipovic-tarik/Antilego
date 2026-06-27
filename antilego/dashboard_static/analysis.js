const palette = ["#f2f2f2", "#7aa2d6", "#d9a65a", "#83b99a", "#b49ac8", "#d47f7f", "#76b9c7", "#b7af72", "#9d9d9d", "#c28ca6"];
const $ = (selector) => document.querySelector(selector);
const money = (value) => value === null || value === undefined ? "Unavailable" : `${value < 0 ? "-" : ""}$${Math.abs(value).toFixed(4)}`;
const percent = (value, digits = 2) => `${(Number(value) * 100).toFixed(digits)}%`;
const time = (value) => new Date(value).toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" });
const escapeHtml = (value) => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");

function drawChart(family, highlightedLabels) {
  const canvas = $("#analysis-chart");
  const rect = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.floor(rect.width * ratio);
  canvas.height = Math.floor(rect.height * ratio);
  const ctx = canvas.getContext("2d");
  ctx.scale(ratio, ratio);
  const width = rect.width;
  const height = rect.height;
  const pad = { left: 62, right: 24, top: 24, bottom: 38 };
  const plotWidth = width - pad.left - pad.right;
  const plotHeight = height - pad.top - pad.bottom;
  const points = family.points || [];
  const probabilityMode = family.chart_mode === "market_probabilities";
  const finite = (value) => value !== null && value !== "" && Number.isFinite(Number(value));
  const values = (family.market_series || []).flatMap((series) => (series.points || []).filter((point) => finite(point.value)).map((point) => Number(point.value)));
  const focusValues = probabilityMode ? (family.market_series || []).filter((series) => highlightedLabels.has(series.label)).flatMap((series) => (series.points || []).flatMap((point) => [point.value, point.buy_value, point.sell_value]).filter(finite).map(Number)) : [];
  const focusMin = focusValues.length ? Math.min(...focusValues) : 0;
  const focusMax = focusValues.length ? Math.max(...focusValues) : 1;
  const focusPadding = probabilityMode ? Math.max(.002, (focusMax - focusMin) * .65) : 0;
  const minValue = probabilityMode ? Math.max(0, focusMin - focusPadding) : 0;
  const maxValue = probabilityMode ? Math.min(1, focusMax + focusPadding) : Math.max(1.05, ...values, ...points.map((point) => Number(point.value) || 0)) * 1.08;
  const x = (index) => pad.left + (points.length <= 1 ? plotWidth / 2 : index * plotWidth / (points.length - 1));
  const y = (value) => pad.top + plotHeight - ((Number(value || 0) - minValue) / Math.max(.0001, maxValue - minValue)) * plotHeight;
  ctx.font = "12px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
  for (let row = 0; row <= 4; row += 1) {
    const py = pad.top + row * plotHeight / 4;
    ctx.strokeStyle = "rgba(255,255,255,.11)";
    ctx.beginPath(); ctx.moveTo(pad.left, py); ctx.lineTo(width - pad.right, py); ctx.stroke();
    const axisValue = maxValue - (maxValue - minValue) * row / 4;
    const label = `${(axisValue * 100).toFixed(probabilityMode ? 1 : 0)}%`;
    ctx.fillStyle = "#858d89";
    ctx.fillText(label, pad.left - ctx.measureText(label).width - 10, py + 4);
  }
  points.forEach((point, index) => {
    if (!point.violating) return;
    const start = index === 0 ? pad.left : (x(index - 1) + x(index)) / 2;
    const end = index === points.length - 1 ? width - pad.right : (x(index) + x(index + 1)) / 2;
    ctx.fillStyle = "rgba(237,106,106,.19)";
    ctx.fillRect(start, pad.top, end - start, plotHeight);
  });
  if (!probabilityMode) {
    const idealY = y(family.ideal_value);
    ctx.save(); ctx.setLineDash([7, 6]); ctx.strokeStyle = "#42dc8f";
    ctx.beginPath(); ctx.moveTo(pad.left, idealY); ctx.lineTo(width - pad.right, idealY); ctx.stroke(); ctx.restore();
  }
  (family.market_series || []).forEach((series, index) => {
    const highlighted = !highlightedLabels.size || highlightedLabels.has(series.label);
    ctx.beginPath();
    let drawing = false;
    (series.points || []).forEach((point, pointIndex) => {
      if (!finite(point.value)) { drawing = false; return; }
      const px = x(Number.isInteger(point.index) ? point.index : pointIndex);
      if (!drawing) { ctx.moveTo(px, y(point.value)); drawing = true; }
      else ctx.lineTo(px, y(point.value));
    });
    ctx.globalAlpha = highlighted ? 1 : .2;
    ctx.strokeStyle = palette[index % palette.length];
    ctx.lineWidth = highlighted ? 3 : 1;
    ctx.stroke();
    ctx.globalAlpha = 1;
  });
  if (points.length) {
    ctx.fillStyle = "#858d89";
    ctx.fillText(time(points[0].timestamp), pad.left, height - 9);
    const end = time(points.at(-1).timestamp);
    ctx.fillText(end, width - pad.right - ctx.measureText(end).width, height - 9);
  }
}

function render(payload) {
  const opportunity = payload.opportunities[0];
  const highlighted = new Set(opportunity.legs.map((leg) => leg.label));
  $("#title").textContent = payload.name;
  $("#subtitle").textContent = `Latest executable violation at ${new Date(payload.timestamp).toLocaleString()}. The enlarged chart emphasizes the contracts used in the best fee-adjusted estimate.`;
  $("#chart-title").textContent = opportunity.summary;
  $("#verdict").textContent = opportunity.verdict;
  $("#gross").textContent = money(opportunity.gross_profit);
  $("#fees").textContent = money(opportunity.estimated_fees);
  $("#net").textContent = money(opportunity.net_profit);
  $("#net").className = opportunity.net_profit > 0 ? "positive" : "negative";
  $("#opportunity-title").textContent = `${opportunity.shares.toFixed(2)} shares per leg`;
  $("#execution-note").textContent = opportunity.inventory_required ? "At least one sell leg is present. The estimate assumes you already hold that position or can construct an equivalent position; it is not starting-flat proof of arbitrage." : "All listed legs are buys at current executable asks.";
  $("#fee-note").textContent = payload.fee_error ? `The current fee schedule could not be retrieved: ${payload.fee_error}` : "Fees use the event's current Polymarket taker-fee schedule. Maker fills may cost less, but are not guaranteed to execute.";
  $("#legs").innerHTML = opportunity.legs.map((leg) => `<div class="leg"><strong class="side ${leg.side}">${leg.side.toUpperCase()}</strong><strong>${escapeHtml(leg.label)}</strong><span>Price<strong>${percent(leg.price)}</strong></span><span>Notional<strong>${money(leg.notional)}</strong></span><span>Est. fee<strong>${money(leg.fee)}</strong></span></div>`).join("");
  $("#legend").innerHTML = (payload.chart.market_series || []).map((series, index) => `<span style="color:${palette[index % palette.length]};opacity:${highlighted.has(series.label) ? 1 : .35}"><i></i>${escapeHtml(series.label)} <strong>${series.points?.at(-1)?.value == null ? "-" : percent(series.points.at(-1).value, 1)}</strong></span>`).join("");
  if (payload.polymarket_url) $("#polymarket-link").href = payload.polymarket_url;
  else $("#polymarket-link").hidden = true;
  $("#report").hidden = false;
  drawChart(payload.chart, highlighted);
  window.addEventListener("resize", () => drawChart(payload.chart, highlighted));
}

async function load() {
  const family = new URLSearchParams(location.search).get("family") || "";
  try {
    const response = await fetch(`/api/analysis?family=${encodeURIComponent(family)}`);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Analysis failed.");
    render(payload);
  } catch (error) {
    $("#error").textContent = error.message;
    $("#error").hidden = false;
    $("#subtitle").textContent = "Antilego could not build this analysis.";
  }
}

load();
