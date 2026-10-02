/* UI kit: DOM helpers, formatters, toasts, modals, loading/empty states, SVG charts.
   Everything is hand-rolled — no external chart or icon library, so the app works offline
   and inside sandboxed previews that block third-party requests. */
const UI = (() => {
  const esc = (s) => String(s === null || s === undefined ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");

  const pct = (v, digits = 0) => (v === null || v === undefined || isNaN(v)) ? "—"
    : (v * 100).toFixed(digits) + "%";
  const num = (v, digits = 1) => (v === null || v === undefined || isNaN(v)) ? "—" : Number(v).toFixed(digits);
  const dt = (iso) => {
    if (!iso) return "—";
    const d = new Date(iso);
    if (isNaN(d)) return iso;
    return d.toLocaleString(undefined, { year: "numeric", month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  };
  const dOnly = (iso) => {
    if (!iso) return "—";
    const d = new Date(iso);
    return isNaN(d) ? iso : d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "2-digit" });
  };
  const human = (v) => String(v === null || v === undefined ? "—" : v).replace(/_/g, " ");
  const titleCase = (v) => human(v).replace(/\b\w/g, (c) => c.toUpperCase());

  // ---------------------------------------------------------------- toasts
  function toast(message, kind = "info", ms = 4200) {
    const host = document.getElementById("toasts");
    const el = document.createElement("div");
    el.className = "toast " + kind;
    el.innerHTML = `<span>${esc(message)}</span>`;
    host.appendChild(el);
    setTimeout(() => { el.style.opacity = "0"; el.style.transform = "translateY(6px)";
      el.style.transition = ".2s"; setTimeout(() => el.remove(), 220); }, ms);
  }

  // ---------------------------------------------------------------- modal
  function modal({ title, body, footer, wide = false, onMount }) {
    const root = document.getElementById("modal-root");
    const wrap = document.createElement("div");
    wrap.className = "modal-backdrop";
    wrap.innerHTML = `
      <div class="modal ${wide ? "wide" : ""}" role="dialog" aria-modal="true">
        <div class="modal-head"><h3>${esc(title || "")}</h3>
          <button class="icon-btn" data-close aria-label="Close">✕</button></div>
        <div class="modal-body">${body || ""}</div>
        ${footer ? `<div class="modal-foot">${footer}</div>` : ""}
      </div>`;
    root.appendChild(wrap);
    const close = () => wrap.remove();
    wrap.addEventListener("click", (e) => {
      if (e.target === wrap || e.target.closest("[data-close]")) close();
    });
    document.addEventListener("keydown", function onEsc(e) {
      if (e.key === "Escape") { close(); document.removeEventListener("keydown", onEsc); }
    });
    if (onMount) onMount(wrap.querySelector(".modal"), close);
    return close;
  }

  function confirmDialog({ title, message, confirmLabel, danger = false }) {
    return new Promise((resolve) => {
      modal({
        title,
        body: `<p>${esc(message)}</p>`,
        footer: `<button class="btn" data-close>${esc(t("common.cancel"))}</button>
                 <button class="btn ${danger ? "danger" : "primary"}" data-yes>${esc(confirmLabel || t("common.confirm"))}</button>`,
        onMount(node, close) {
          node.querySelector("[data-yes]").addEventListener("click", () => { close(); resolve(true); });
          node.querySelector("[data-close]").addEventListener("click", () => resolve(false));
        }
      });
      // backdrop/Esc dismissal resolves false
      const root = document.getElementById("modal-root");
      const obs = new MutationObserver(() => {
        if (!root.querySelector(".modal-backdrop")) { resolve(false); obs.disconnect(); }
      });
      obs.observe(root, { childList: true });
    });
  }

  // ---------------------------------------------------------------- states
  const skeleton = (rows = 3, withCards = true) => `
    <div class="grid">
      ${withCards ? `<div class="grid cols-3">${Array.from({ length: 3 }, () => `<div class="skeleton sk-card"></div>`).join("")}</div>` : ""}
      <div class="card">
        ${Array.from({ length: rows }, () => `<div class="skeleton sk-line"></div>`).join("")}
      </div>
    </div>`;

  const empty = (title, body, actionHtml = "", icon = "leaf") => `
    <div class="empty">
      ${emptyIcon(icon)}
      <h4>${esc(title)}</h4>
      <p class="muted">${esc(body)}</p>
      ${actionHtml}
    </div>`;

  function emptyIcon(kind) {
    const paths = {
      leaf: `<path d="M46 74c0-26 8-40 30-50-4 24-12 40-30 50z" fill="#cbe8d8"/><path d="M46 74C24 68 16 52 18 30c16 6 26 20 28 44z" fill="#e6f4ec"/>`,
      table: `<rect x="14" y="22" width="64" height="52" rx="6" fill="#eef4f1" stroke="#cbe8d8"/><path d="M14 36h64M32 22v52M52 22v52" stroke="#d8e8e0"/>`,
      chart: `<rect x="18" y="46" width="12" height="28" rx="3" fill="#cbe8d8"/><rect x="38" y="32" width="12" height="42" rx="3" fill="#9ed3b8"/><rect x="58" y="22" width="12" height="52" rx="3" fill="#6fbf98"/>`,
      search: `<circle cx="42" cy="42" r="18" fill="#eef4f1" stroke="#cbe8d8"/><path d="M55 55l12 12" stroke="#9ed3b8" stroke-width="4" stroke-linecap="round"/>`,
      lock: `<rect x="28" y="40" width="36" height="30" rx="6" fill="#eef4f1" stroke="#cbe8d8"/><path d="M36 40v-8a10 10 0 0120 0v8" stroke="#9ed3b8" stroke-width="4" fill="none"/>`
    };
    return `<svg viewBox="0 0 90 90" aria-hidden="true">${paths[kind] || paths.leaf}</svg>`;
  }

  // ---------------------------------------------------------------- charts
  function hbars(items, { format = (v) => num(v, 3), max = null } = {}) {
    const top = max || Math.max(...items.map((i) => i.value), 0.0001);
    return `<div>${items.map((i) => `
      <div class="hbar">
        <span class="muted small nowrap" title="${esc(i.label)}">${esc(i.label)}</span>
        <span class="track"><span class="fill" style="width:${Math.max(2, (i.value / top) * 100)}%"></span></span>
        <span class="val">${esc(format(i.value))}</span>
      </div>`).join("")}</div>`;
  }

  function vbars(items, { height = 160, format = (v) => String(v) } = {}) {
    const w = Math.max(320, items.length * 34);
    const max = Math.max(...items.map((i) => i.value), 1);
    const bw = w / items.length;
    const bars = items.map((i, idx) => {
      const h = (i.value / max) * (height - 38);
      const x = idx * bw + bw * 0.18;
      return `<g><rect x="${x.toFixed(1)}" y="${(height - 24 - h).toFixed(1)}" width="${(bw * 0.64).toFixed(1)}"
        height="${h.toFixed(1)}" rx="3" fill="${i.color || "#1f8c60"}"><title>${esc(i.label)}: ${esc(format(i.value))}</title></rect>
        <text x="${(x + bw * 0.32).toFixed(1)}" y="${height - 8}" text-anchor="middle"
          transform="rotate(-52 ${(x + bw * 0.32).toFixed(1)} ${height - 8})">${esc(String(i.label).slice(0, 14))}</text></g>`;
    }).join("");
    return `<svg class="chart" viewBox="0 0 ${w} ${height}" height="${height}" role="img">${bars}</svg>`;
  }

  function histogram(bins, counts, { height = 150, unit = "mm" } = {}) {
    const w = 620, max = Math.max(...counts, 1);
    const bw = w / counts.length;
    const bars = counts.map((c, i) => {
      const h = (c / max) * (height - 34);
      return `<rect x="${(i * bw + 2).toFixed(1)}" y="${(height - 22 - h).toFixed(1)}"
        width="${(bw - 4).toFixed(1)}" height="${h.toFixed(1)}" rx="2" fill="#2f9e6f">
        <title>${bins[i]}–${bins[i + 1]} ${unit}: ${c} rows</title></rect>
        <text x="${(i * bw + bw / 2).toFixed(1)}" y="${height - 6}" text-anchor="middle">${bins[i]}</text>`;
    }).join("");
    return `<svg class="chart" viewBox="0 0 ${w} ${height}" height="${height}" role="img">${bars}</svg>`;
  }

  function donut(items, { size = 168, thickness = 26 } = {}) {
    const total = items.reduce((s, i) => s + i.value, 0) || 1;
    const r = (size - thickness) / 2, c = 2 * Math.PI * r;
    let offset = 0;
    const colors = ["#1f8c60", "#d9a13b", "#2b6cb0", "#7a5af8", "#c0392b", "#0f766e"];
    const arcs = items.map((i, idx) => {
      const frac = i.value / total;
      const seg = `<circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none"
        stroke="${colors[idx % colors.length]}" stroke-width="${thickness}"
        stroke-dasharray="${(frac * c).toFixed(1)} ${(c - frac * c).toFixed(1)}"
        stroke-dashoffset="${(-offset * c).toFixed(1)}" transform="rotate(-90 ${size / 2} ${size / 2})">
        <title>${esc(i.label)}: ${i.value} (${pct(frac, 1)})</title></circle>`;
      offset += frac;
      return seg;
    }).join("");
    const legend = items.map((i, idx) => `<span><i style="background:${colors[idx % colors.length]}"></i>${esc(i.label)} · ${i.value}</span>`).join("");
    return `<div style="display:flex;gap:16px;align-items:center;flex-wrap:wrap">
      <svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}" role="img">${arcs}
        <text x="${size / 2}" y="${size / 2 + 4}" text-anchor="middle" style="font-size:13px;fill:#5b6a78">${total}</text></svg>
      <div class="legend" style="display:grid">${legend}</div></div>`;
  }

  function heatmap(labels, matrix) {
    const max = Math.max(...matrix.flat(), 1);
    const head = `<div></div>` + labels.map((l) => `<div class="hlabel-rot">${esc(l)}</div>`).join("");
    const body = matrix.map((row, ri) => `<div class="hlabel">${esc(labels[ri])}</div>` +
      row.map((v, ci) => {
        const a = v === 0 ? 0 : 0.18 + 0.82 * (v / max);
        return `<div class="hcell ${v ? "on" : ""}" title="${esc(labels[ri])} → ${esc(labels[ci])}: ${v}"
          style="background:${v ? `rgba(19,95,69,${a.toFixed(2)})` : "#f2f5f7"}">${v || ""}</div>`;
      }).join("")).join("");
    return `<div class="heat-grid" style="grid-template-columns:minmax(74px,auto) repeat(${labels.length}, minmax(16px, 1fr))">
      ${head}${body}</div>`;
  }

  // ---------------------------------------------------------------- forms
  function readForm(formEl) {
    const out = {};
    new FormData(formEl).forEach((v, k) => { out[k] = typeof v === "string" ? v.trim() : v; });
    formEl.querySelectorAll('input[type="checkbox"]').forEach((cb) => { out[cb.name] = cb.checked; });
    return out;
  }

  function options(list, selected, { valueKey = "value", labelKey = "label", knKey = "label_kn" } = {}) {
    return list.map((o) => {
      const kn = knKey && o[knKey] ? ` · ${o[knKey]}` : "";
      return `<option value="${esc(o[valueKey])}" ${String(o[valueKey]) === String(selected) ? "selected" : ""}>${esc(o[labelKey])}${esc(kn)}</option>`;
    }).join("");
  }

  const statusBadge = (status) => {
    const map = { approved: "green", pending: "amber", rejected: "red" };
    return `<span class="badge ${map[status] || "grey"}">${esc(t(status === "approved" ? "surv.approved" : status === "pending" ? "surv.pending" : status === "rejected" ? "surv.rejected" : status))}</span>`;
  };
  const outcomeBadge = (o) => {
    const map = { excellent: "green", good: "green", average: "amber", poor: "red" };
    return o ? `<span class="badge ${map[o] || "grey"}">${esc(titleCase(o))}</span>` : `<span class="muted">—</span>`;
  };

  const scoreClass = (score) => score >= 0.55 ? "green" : score >= 0.35 ? "amber" : "grey";

  return { esc, pct, num, dt, dOnly, human, titleCase, toast, modal, confirmDialog, skeleton, empty,
    hbars, vbars, histogram, donut, heatmap, readForm, options, statusBadge, outcomeBadge, scoreClass };
})();

window.UI = UI;
