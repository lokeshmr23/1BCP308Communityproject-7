/* Pages: Recommend, My History, Primary Dataset Survey. */
const Pages = window.Pages || {};

/* ==========================================================================
   RECOMMEND
   ========================================================================== */
Pages.recommend = {
  lastResult: null,
  async render(view) {
    const meta = App.meta;
    view.innerHTML = `
      <div class="grid cols-4" id="rec-stats"></div>
      <div class="rec-grid" style="margin-top:16px">
        <div class="card" id="rec-form-card">
          <div class="card-head"><h3>${UI.esc(t("rec.title"))}</h3></div>
          <p class="muted small">${UI.esc(t("rec.intro"))}</p>
          <form id="predict-form" class="form">
            <label class="field"><span>${UI.esc(t("rec.soil"))} *</span>
              <select name="soil_type">${UI.options(App.meta.soil_types, "laterite")}</select>
            </label>
            <label class="field"><span>${UI.esc(t("rec.season"))} *</span>
              <select name="season">${UI.options(App.meta.seasons, "Kharif")}</select>
            </label>
            <label class="field"><span>${UI.esc(t("rec.rainfall"))} *</span>
              <input type="number" name="rainfall_mm" min="0" max="1000" step="5" value="220" required />
              <span class="hint">${UI.esc(t("rec.rainfallHint"))}</span>
            </label>
            <div class="chips" id="rain-presets">
              ${App.meta.rainfall_presets.map((p) => `<button type="button" class="chip" data-rain="${p.value}">${UI.esc(p.label)} · ${p.value} mm</button>`).join("")}
            </div>
            <label class="field"><span>${UI.esc(t("rec.water"))} *</span>
              <select name="water_availability">${UI.options(App.meta.water_levels, "medium")}</select>
            </label>
            <label class="field"><span>${UI.esc(t("rec.irrigation"))} <span class="muted small">(${UI.esc(t("common.optional"))})</span></span>
              <select name="irrigation_source"><option value="">—</option>${UI.options(App.meta.irrigation_sources, "")}</select>
              <span class="hint">${UI.esc(t("rec.irrigationHint"))}</span>
            </label>
            <label class="field"><span>${UI.esc(t("common.taluk"))}</span>
              <select name="taluk">${UI.options(App.meta.taluks, "")}</select>
            </label>
            <label class="checkbox">
              <input type="checkbox" name="regional_tuning" checked />
              <span>${UI.esc(t("rec.regional"))}<span class="hint" style="display:block">${UI.esc(t("rec.regionalHint"))}</span></span>
            </label>
            <label class="checkbox">
              <input type="checkbox" name="save" ${App.user ? "checked" : ""} ${App.user ? "" : "disabled"} />
              <span>${UI.esc(t("rec.saveToHistory"))}${App.user ? "" : ` — <span class="hint">${UI.esc(t("rec.needLogin"))}</span>`}</span>
            </label>
            <button class="btn primary block" type="submit" id="rec-submit">${UI.esc(t("rec.generate"))}</button>
            <p class="form-error" id="rec-error" role="alert"></p>
          </form>
        </div>
        <div id="rec-results"></div>
      </div>`;

    view.querySelector("#rain-presets").addEventListener("click", (e) => {
      const btn = e.target.closest("[data-rain]");
      if (btn) view.querySelector('[name="rainfall_mm"]').value = btn.dataset.rain;
    });
    // irrigation source sets water availability automatically (matches the API rule)
    view.querySelector('[name="irrigation_source"]').addEventListener("change", (e) => {
      const src = App.meta.irrigation_sources.find((s) => s.value === e.target.value);
      if (src) view.querySelector('[name="water_availability"]').value = src.level;
    });
    view.querySelector("#predict-form").addEventListener("submit", (e) => {
      e.preventDefault();
      this.submit(view);
    });

    this.renderStats(view);
    this.renderEmpty(view);
  },

  async renderStats(view) {
    const host = view.querySelector("#rec-stats");
    try {
      const s = await Api.summary();
      host.innerHTML = `
        <div class="stat"><div class="label">${UI.esc(t("nav.history"))}</div>
          <div class="value">${s.cards.predictions}</div>
          <div class="sub">${s.cards.predictions_with_feedback} with outcome feedback</div></div>
        <div class="stat"><div class="label">${UI.esc(t("nav.surveys"))}</div>
          <div class="value">${s.cards.survey_entries}</div>
          <div class="sub">${s.cards.approved_survey_rows} approved for training</div></div>
        <div class="stat"><div class="label">${UI.esc(t("model.best"))}</div>
          <div class="value">${UI.pct(s.model.test_accuracy, 1)}</div>
          <div class="sub">${UI.esc(s.model.label || "")} · top-3 ${UI.pct(s.model.top3_accuracy, 1)}</div></div>
        <div class="stat"><div class="label">District rainfall (annual)</div>
          <div class="value">${s.district_reference.rainfall_normal_annual_mm}<span style="font-size:.85rem"> mm</span></div>
          <div class="sub">normal — 2023 actual ${s.district_reference.rainfall_2023_actual_mm} mm (KVK DK)</div></div>`;
    } catch (err) {
      host.innerHTML = `<div class="card"><p class="muted small">Dashboard summary unavailable: ${UI.esc(err.message)}</p></div>`;
    }
  },

  renderEmpty(view) {
    view.querySelector("#rec-results").innerHTML = `
      <div class="card">${UI.empty(t("rec.emptyTitle"), t("rec.emptyBody"),
        `<button class="btn primary" id="rec-empty-go">${UI.esc(t("rec.generate"))}</button>`, "search")}</div>`;
    const go = view.querySelector("#rec-empty-go");
    if (go) go.addEventListener("click", () => view.querySelector("#predict-form").requestSubmit());
  },

  async submit(view) {
    const form = view.querySelector("#predict-form");
    const err = view.querySelector("#rec-error");
    err.textContent = "";
    const data = UI.readForm(form);
    const payload = { ...data, rainfall_mm: Number(data.rainfall_mm), top_k: 3 };
    if (!payload.irrigation_source) delete payload.irrigation_source;
    if (!payload.taluk) delete payload.taluk;
    delete payload.save;                       // saving is a separate, explicit action

    const btn = view.querySelector("#rec-submit");
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner"></span> ${UI.esc(t("rec.loading"))}`;
    const results = view.querySelector("#rec-results");
    results.innerHTML = UI.skeleton(4);

    try {
      const res = await Api.predict(payload);
      this.lastResult = { res, payload, saved: false };
      this.renderResult(view, this.lastResult);
      UI.toast(`${res.recommendations.length} recommendations ready`, "ok", 2200);
    } catch (e) {
      err.textContent = e.details && e.details.length ? `${e.message}: ${e.details.join("; ")}` : e.message;
      results.innerHTML = `<div class="card"><div class="callout danger"><strong>Could not get a recommendation</strong>${UI.esc(e.message)}</div>
        <button class="btn" id="rec-retry">${UI.esc(t("common.retry"))}</button></div>`;
      const retry = view.querySelector("#rec-retry");
      if (retry) retry.addEventListener("click", () => this.submit(view));
    } finally {
      btn.disabled = false;
      btn.textContent = t("rec.generate");
    }
  },

  renderResult(view, state) {
    const { res, payload } = state;
    const recs = res.recommendations;
    const host = view.querySelector("#rec-results");
    const canSave = !!App.user && !state.saved;
    host.innerHTML = `
      ${res.low_confidence ? `<div class="callout warn" style="margin-bottom:14px">
        <strong>${UI.esc(t("rec.lowConfidence"))}</strong>${UI.esc(t("rec.lowConfidenceBody"))}</div>` : ""}
      <div class="card-head" style="padding:0 2px">
        <h3>${UI.esc(t("rec.results"))}</h3><span class="spacer"></span>
        ${canSave ? `<button class="btn small primary" id="rec-save">${UI.esc(t("rec.saveToHistory"))}</button>`
                  : state.saved ? `<span class="pill">✓ ${UI.esc(t("rec.savedOk"))}</span>`
                  : `<span class="pill grey">${UI.esc(t("rec.needLogin"))}</span>`}
        <button class="btn small" id="rec-again">${UI.esc(t("rec.regenerate"))}</button>
      </div>
      ${recs.map((r) => this.card(r, res)).join("")}
      ${res.regional_advisory && res.regional_advisory.length ? `
        <div class="card" style="margin-top:14px">
          <div class="card-head"><h3>${UI.esc(t("rec.advisory"))}</h3><span class="badge grey">KB only</span></div>
          <p class="muted small">${UI.esc(t("rec.advisoryNote"))}</p>
          ${res.regional_advisory.map((a) => `
            <div style="border-top:1px solid var(--line);padding-top:10px;margin-top:10px">
              <strong>${UI.esc(a.name)}${a.name_kn ? ` · ${UI.esc(a.name_kn)}` : ""}</strong>
              <span class="badge ${UI.scoreClass(a.rule_fit)}" style="margin-left:6px">rule fit ${UI.pct(a.rule_fit, 0)}</span>
              <ul class="reasons">${a.reasons.slice(0, 3).map((x) => `<li>${UI.esc(x)}</li>`).join("")}</ul>
            </div>`).join("")}
        </div>` : ""}
      <div class="card" style="margin-top:14px">
        <div class="card-head"><h3>${UI.esc(t("rec.expansion"))}</h3></div>
        <table><thead><tr><th>Input</th><th>Value</th><th>Assumed as</th><th>Basis</th></tr></thead>
        <tbody>
          ${res.expansion_audit.map((e) => `<tr><td class="mono">${UI.esc(e.input)}</td>
            <td>${UI.esc(e.value === null ? `${payload.rainfall_mm} mm (+ irrigation index)` : e.value)}</td>
            <td class="mono">${UI.esc(e.assumed_as)}</td><td class="muted small">${UI.esc(e.basis)}</td></tr>`).join("")}
        </tbody></table>
        <div class="callout info" style="margin-top:12px"><strong>${UI.esc(t("rec.confidenceNote"))}</strong>
          ${UI.esc(res.confidence_note)}. ${UI.esc(res.blend.score_label)}</div>
      </div>
      <div class="callout warn" style="margin-top:14px"><strong>${UI.esc(t("rec.disclaimer"))}</strong>${UI.esc(res.disclaimer)}</div>`;

    const saveBtn = host.querySelector("#rec-save");
    if (saveBtn) saveBtn.addEventListener("click", () => this.save(view, state));
    host.querySelector("#rec-again").addEventListener("click", () => {
      view.querySelector("#predict-form").scrollIntoView({ behavior: "smooth", block: "start" });
      view.querySelector("#predict-form").requestSubmit();
    });
  },

  card(r, res) {
    const isTop = r.rank === 1;
    return `
      <div class="rec-card ${isTop ? "top" : ""}" style="margin-top:14px">
        <span class="rank-strip"></span>
        <div class="rec-head">
          <div class="rec-title">
            <h3>${r.rank}. ${UI.esc(r.name)}</h3>
            <div class="kn">${UI.esc(r.name_kn || "")} ${r.dk_local ? `· <span class="badge green">${UI.esc(t("crops.dkLocal"))}</span>` : ""}</div>
          </div>
          <div class="rec-score">
            <div class="pct">${UI.pct(r.confidence, 0)}</div>
            <span class="badge ${UI.scoreClass(r.confidence)}">${UI.esc(r.status)}</span>
          </div>
        </div>
        <div class="meter"><span style="width:${Math.max(3, r.confidence * 100)}%"></span></div>
        <div class="metrics-inline">
          <span><b>${UI.esc(t("rec.modelProb"))}</b> ${UI.pct(r.model_probability, 1)}</span>
          <span><b>${UI.esc(t("rec.ruleFit"))}</b> ${UI.pct(r.rule_fit, 1)}</span>
          <span><b>category</b> ${UI.esc(r.category || "—")}</span>
          ${r.duration_days ? `<span><b>duration</b> ~${r.duration_days} d</span>` : ""}
          ${r.waterlogging_penalised ? `<span class="badge amber">waterlogging risk</span>` : ""}
          <span><b>rule parts</b> water ${r.rule_components.water} · season ${r.rule_components.season} · rain ${r.rule_components.rain} · soil ${r.rule_components.soil}</span>
        </div>
        <h4 style="margin:12px 0 4px">${UI.esc(t("rec.why"))}</h4>
        <ul class="reasons">${r.reasons.map((x) => `<li>${UI.esc(x)}</li>`).join("")}</ul>
        ${r.advisories && r.advisories.length ? `
          <h4 style="margin:10px 0 4px">${UI.esc(t("rec.cautions"))}</h4>
          <div class="advisories">${r.advisories.map((a) => `<div class="callout warn">${UI.esc(a)}</div>`).join("")}</div>` : ""}
      </div>`;
  },

  async save(view, state) {
    const { payload } = state;
    const btn = view.querySelector("#rec-save");
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner dark"></span> ${UI.esc(t("rec.saving"))}`;
    try {
      await Api.predict({ ...payload, save: true });
      state.saved = true;
      btn.outerHTML = `<span class="pill">✓ ${UI.esc(t("rec.savedOk"))}</span>`;
      UI.toast(t("rec.savedOk"), "ok");
    } catch (e) {
      btn.disabled = false;
      btn.textContent = t("rec.saveToHistory");
      UI.toast(e.message, "err");
    }
  }
};

/* ==========================================================================
   MY HISTORY
   ========================================================================== */
Pages.history = {
  filters: { limit: 10, offset: 0, scope: undefined, with_feedback: undefined },

  async render(view) {
    const meta = App.meta;
    view.innerHTML = `
      <div class="grid cols-4" id="hist-stats">${UI.skeleton(2, false)}</div>
      <div class="card" style="margin-top:16px">
        <div class="toolbar">
          ${App.isAdmin ? `<label class="field"><span>${UI.esc(t("hist.scope"))}</span>
            <select id="f-scope"><option value="mine">${UI.esc(t("hist.mine"))}</option>
              <option value="all">${UI.esc(t("hist.allUsers"))}</option></select></label>` : ""}
          <label class="field"><span>${UI.esc(t("common.season"))}</span>
            <select id="f-season"><option value="">${UI.esc(t("common.all"))}</option>
              ${meta.seasons.map((s) => `<option value="${s.value}">${UI.esc(s.label)}</option>`).join("")}</select></label>
          <label class="field"><span>${UI.esc(t("common.crop"))}</span>
            <select id="f-crop"><option value="">${UI.esc(t("common.all"))}</option>
              ${meta.model_crops.map((c) => `<option value="${c.value}">${UI.esc(c.label)}</option>`).join("")}</select></label>
          <label class="field"><span>Feedback</span>
            <select id="f-feedback"><option value="">${UI.esc(t("common.all"))}</option>
              <option value="1">${UI.esc(t("hist.withFeedback"))}</option></select></label>
          <span class="spacer"></span>
          <button class="btn small" id="hist-export">${UI.esc(t("common.export"))}</button>
        </div>
        <div id="hist-table">${UI.skeleton(5)}</div>
        <div class="toolbar" style="margin:12px 0 0">
          <span class="spacer"></span>
          <button class="btn small" id="hist-prev">←</button>
          <span class="muted small" id="hist-page"></span>
          <button class="btn small" id="hist-next">→</button>
        </div>
      </div>`;

    const bind = (id, key) => {
      const el = view.querySelector(id);
      if (el) el.addEventListener("change", (e) => { this.filters[key] = e.target.value || undefined; this.filters.offset = 0; this.load(view); });
    };
    bind("#f-scope", "scope"); bind("#f-season", "season"); bind("#f-crop", "crop");
    bind("#f-feedback", "with_feedback");
    view.querySelector("#hist-prev").addEventListener("click", () => {
      this.filters.offset = Math.max(0, this.filters.offset - this.filters.limit); this.load(view);
    });
    view.querySelector("#hist-next").addEventListener("click", () => {
      this.filters.offset += this.filters.limit; this.load(view);
    });
    view.querySelector("#hist-export").addEventListener("click", () =>
      Api.download("/api/history/export", { scope: this.filters.scope }));

    this.load(view);
    this.loadStats(view);
  },

  async loadStats(view) {
    const host = view.querySelector("#hist-stats");
    try {
      const s = await Api.historySummary({ scope: this.filters.scope });
      host.innerHTML = `
        <div class="stat"><div class="label">${UI.esc(t("nav.history"))}</div><div class="value">${s.total}</div>
          <div class="sub">avg suitability ${UI.pct(s.avg_confidence, 0)}</div></div>
        <div class="stat"><div class="label">${UI.esc(t("hist.feedback"))}</div><div class="value">${s.with_feedback}</div>
          <div class="sub">${s.advice_followed} followed the advice fully</div></div>
        <div class="stat"><div class="label">Top crop suggested</div>
          <div class="value">${s.top_crops.length ? UI.esc(s.top_crops[0].crop) : "—"}</div>
          <div class="sub">${s.top_crops.length ? s.top_crops[0].count + " times" : "no data yet"}</div></div>
        <div class="stat"><div class="label">Outcomes reported</div>
          <div class="value">${Object.values(s.outcomes).reduce((a, b) => a + b, 0)}</div>
          <div class="sub">${Object.entries(s.outcomes).map(([k, v]) => `${k} ${v}`).join(" · ") || "—"}</div></div>`;
    } catch (e) {
      host.innerHTML = `<div class="card"><p class="muted small">${UI.esc(e.message)}</p></div>`;
    }
  },

  async load(view) {
    const host = view.querySelector("#hist-table");
    host.innerHTML = UI.skeleton(5);
    try {
      const data = await Api.history(this.filters);
      if (!data.total) {
        host.innerHTML = UI.empty(t("hist.emptyTitle"), t("hist.emptyBody"),
          `<a class="btn primary" href="#/recommend">${UI.esc(t("nav.recommend"))}</a>`, "table");
        view.querySelector("#hist-page").textContent = "";
        return;
      }
      host.innerHTML = `
        <div class="table-wrap"><table>
          <thead><tr>
            <th>${UI.esc(t("common.date"))}</th>${App.isAdmin && this.filters.scope === "all" ? `<th>${UI.esc(t("common.farmer"))}</th>` : ""}
            <th>${UI.esc(t("common.soil"))}</th><th>${UI.esc(t("common.season"))}</th>
            <th class="num">${UI.esc(t("common.rainfall"))}</th><th>${UI.esc(t("common.water"))}</th>
            <th>${UI.esc(t("common.crop"))}</th><th class="num">${UI.esc(t("common.confidence"))}</th>
            <th>Feedback</th><th>${UI.esc(t("common.actions"))}</th>
          </tr></thead>
          <tbody>${data.items.map((r) => this.row(r)).join("")}</tbody>
        </table></div>`;
      view.querySelector("#hist-page").textContent =
        `${UI.human(this.filters.offset + 1)}–${Math.min(this.filters.offset + this.filters.limit, data.total)} ${t("common.of")} ${data.total}`;
      view.querySelectorAll("[data-view]").forEach((b) => b.addEventListener("click", () => this.detail(b.dataset.view)));
      view.querySelectorAll("[data-feedback]").forEach((b) => b.addEventListener("click", () => this.feedbackModal(b.dataset.feedback, view)));
      view.querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", () => this.remove(b.dataset.del, view)));
      view.querySelector("#hist-next").disabled = this.filters.offset + this.filters.limit >= data.total;
      view.querySelector("#hist-prev").disabled = this.filters.offset === 0;
    } catch (e) {
      host.innerHTML = `<div class="callout danger">${UI.esc(e.message)}</div>`;
    }
  },

  row(r) {
    return `<tr data-row="${r.id}">
      <td class="nowrap">${UI.dOnly(r.created_at)}</td>
      ${App.isAdmin && this.filters.scope === "all" ? `<td>${UI.esc(r.farmer || "—")}<div class="muted small">${UI.esc(r.village || "")}</div></td>` : ""}
      <td>${UI.esc(UI.titleCase(r.soil_type))}</td>
      <td>${UI.esc(r.season)}</td>
      <td class="num">${UI.num(r.rainfall_mm, 0)}</td>
      <td>${UI.esc(UI.titleCase(r.water_availability))}</td>
      <td><strong>${UI.esc(UI.titleCase(r.top_crop))}</strong></td>
      <td class="num">${UI.pct(r.top_confidence, 0)}</td>
      <td>${r.actual_crop ? `${UI.esc(UI.titleCase(r.actual_crop))} ${UI.outcomeBadge(r.yield_outcome)}` : `<span class="muted small">none</span>`}</td>
      <td class="nowrap">
        <button class="btn small" data-view="${r.id}">${UI.esc(t("hist.detail"))}</button>
        <button class="btn small" data-feedback="${r.id}">${UI.esc(t("hist.feedback"))}</button>
        <button class="btn small danger" data-del="${r.id}">${UI.esc(t("common.delete"))}</button>
      </td></tr>`;
  },

  async detail(id) {
    try {
      const { item } = await Api.historyItem(id);
      const res = item.results || {};
      UI.modal({
        title: `${t("hist.detail")} #${id}`,
        wide: true,
        body: `
          <div class="grid cols-2">
            <div><h4>Inputs</h4>
              <table><tbody>
                <tr><td>${UI.esc(t("common.soil"))}</td><td>${UI.esc(UI.titleCase(item.soil_type))}</td></tr>
                <tr><td>${UI.esc(t("common.season"))}</td><td>${UI.esc(item.season)}</td></tr>
                <tr><td>${UI.esc(t("common.rainfall"))}</td><td>${UI.num(item.rainfall_mm, 0)} mm</td></tr>
                <tr><td>${UI.esc(t("common.water"))}</td><td>${UI.esc(UI.titleCase(item.water_availability))}</td></tr>
                <tr><td>Irrigation</td><td>${UI.esc(UI.human(item.irrigation_source) || "—")}</td></tr>
                <tr><td>${UI.esc(t("common.taluk"))}</td><td>${UI.esc(item.taluk || "—")}</td></tr>
                <tr><td>Model</td><td class="mono">${UI.esc(item.model_key)} v${UI.esc(item.model_version)}</td></tr>
                <tr><td>Regional tuning</td><td>${item.regional_tuning ? "on" : "off"}</td></tr>
              </tbody></table>
              ${item.notes ? `<p class="muted small">${UI.esc(item.notes)}</p>` : ""}
              ${item.actual_crop ? `<div class="callout ok" style="margin-top:10px"><strong>Reported outcome</strong>
                grew ${UI.esc(item.actual_crop)} · ${UI.esc(item.yield_outcome)} · followed advice: ${UI.esc(item.followed_advice || "—")}</div>` : ""}
            </div>
            <div><h4>Top recommendations</h4>
              ${(res.recommendations || []).map((r) => `
                <div style="border-left:3px solid ${r.rank === 1 ? "var(--green-600)" : "var(--line-strong)"};padding:8px 10px;margin-bottom:8px">
                  <strong>${r.rank}. ${UI.esc(r.name)}</strong> <span class="badge ${UI.scoreClass(r.confidence)}">${UI.pct(r.confidence, 0)}</span>
                  <div class="muted small">model ${UI.pct(r.model_probability, 1)} · rule ${UI.pct(r.rule_fit, 1)}</div>
                  <ul class="reasons">${(r.reasons || []).slice(0, 4).map((x) => `<li>${UI.esc(x)}</li>`).join("")}</ul>
                </div>`).join("") || `<p class="muted small">No detail stored.</p>`}
              ${res.confidence_note ? `<div class="callout info">${UI.esc(res.confidence_note)}</div>` : ""}
            </div>
          </div>`,
        footer: `<button class="btn" data-close>${UI.esc(t("common.close"))}</button>`
      });
    } catch (e) { UI.toast(e.message, "err"); }
  },

  feedbackModal(id, view) {
    UI.modal({
      title: t("hist.feedbackTitle"),
      body: `
        <p class="muted small">${UI.esc(t("hist.feedbackIntro"))}</p>
        <form id="fb-form" class="form">
          <label class="field"><span>${UI.esc(t("hist.actualCrop"))} *</span>
            <select name="actual_crop">${UI.options(App.meta.crops_all, "")}</select></label>
          <label class="field"><span>${UI.esc(t("hist.yieldOutcome"))} *</span>
            <select name="yield_outcome">${UI.options(App.meta.yield_outcomes, "good")}</select></label>
          <label class="field"><span>${UI.esc(t("hist.followedAdvice"))}</span>
            <select name="followed_advice"><option value="yes">${UI.esc(t("common.yes"))}</option>
              <option value="partly">Partly</option><option value="no">${UI.esc(t("common.no"))}</option></select></label>
          <div class="grid-2">
            <label class="field"><span>${UI.esc(t("common.village"))}</span><input name="village" /></label>
            <label class="field"><span>${UI.esc(t("hist.area"))}</span><input type="number" step="0.1" min="0" name="area_acres" /></label>
          </div>
          <label class="field"><span>${UI.esc(t("common.notes"))}</span><textarea name="feedback_notes"></textarea></label>
          <label class="checkbox"><input type="checkbox" name="add_to_dataset" checked />
            <span>${UI.esc(t("hist.addDataset"))}</span></label>
          <label class="checkbox"><input type="checkbox" name="consent" checked />
            <span>${UI.esc(t("hist.consent"))}</span></label>
        </form>`,
      footer: `<button class="btn" data-close>${UI.esc(t("common.cancel"))}</button>
        <button class="btn primary" id="fb-submit">${UI.esc(t("hist.submitFeedback"))}</button>`,
      onMount(node, close) {
        node.querySelector("#fb-submit").addEventListener("click", async (e) => {
          const btn = e.currentTarget;
          const payload = UI.readForm(node.querySelector("#fb-form"));
          btn.disabled = true; btn.innerHTML = `<span class="spinner"></span>`;
          try {
            const out = await Api.feedback(id, payload);
            UI.toast(out.loop_message || t("hist.feedbackDone"), "ok", 5200);
            close();
            // optimistic row update, then refresh from the server
            const row = view.querySelector(`tr[data-row="${id}"] td:nth-child(${App.isAdmin && Pages.history.filters.scope === "all" ? 9 : 8})`);
            if (row) row.innerHTML = `${UI.esc(UI.titleCase(payload.actual_crop))} ${UI.outcomeBadge(payload.yield_outcome)}`;
            Pages.history.load(view); Pages.history.loadStats(view);
          } catch (err) {
            btn.disabled = false; btn.textContent = t("hist.submitFeedback");
            UI.toast(err.details && err.details.length ? `${err.message}: ${err.details.join("; ")}` : err.message, "err", 6000);
          }
        });
      }
    });
  },

  async remove(id, view) {
    if (!(await UI.confirmDialog({ title: t("common.delete"), message: t("hist.deleteConfirm"), confirmLabel: t("common.delete"), danger: true }))) return;
    const row = view.querySelector(`tr[data-row="${id}"]`);
    if (row) { row.style.opacity = ".4"; row.style.pointerEvents = "none"; }   // optimistic
    try {
      await Api.deleteHistory(id);
      UI.toast(t("common.deleted"), "ok");
      this.load(view); this.loadStats(view);
    } catch (e) {
      if (row) { row.style.opacity = ""; row.style.pointerEvents = ""; }
      UI.toast(e.message, "err");
    }
  }
};

/* ==========================================================================
   PRIMARY DATASET SURVEY
   ========================================================================== */
Pages.surveys = {
  tab: "mine",
  filters: { limit: 10, offset: 0 },

  async render(view) {
    const tabs = [["mine", t("surv.mine")]];
    if (App.isAdmin) tabs.push(["queue", t("surv.queue")], ["all", t("surv.all")]);
    view.innerHTML = `
      <div class="card">
        <div class="card-head">
          <div><h3>${UI.esc(t("surv.title"))}</h3><p class="muted small" style="margin:0">${UI.esc(t("surv.intro"))}</p></div>
          <span class="spacer"></span>
          <button class="btn primary" id="surv-new">+ ${UI.esc(t("surv.new"))}</button>
        </div>
        <div class="grid cols-4" id="surv-stats">${UI.skeleton(2, false)}</div>
      </div>
      <div class="card">
        <div class="tabs-inline" id="surv-tabs">
          ${tabs.map(([id, label]) => `<button data-tab="${id}" class="${this.tab === id ? "active" : ""}">${UI.esc(label)}</button>`).join("")}
        </div>
        <div class="toolbar">
          <label class="field"><span>${UI.esc(t("common.status"))}</span>
            <select id="s-status"><option value="">${UI.esc(t("common.all"))}</option>
              <option value="pending">${UI.esc(t("surv.pending"))}</option>
              <option value="approved">${UI.esc(t("surv.approved"))}</option>
              <option value="rejected">${UI.esc(t("surv.rejected"))}</option></select></label>
          <label class="field"><span>${UI.esc(t("common.taluk"))}</span>
            <select id="s-taluk"><option value="">${UI.esc(t("common.all"))}</option>
              ${App.meta.taluks.map((x) => `<option value="${x.value}">${UI.esc(x.label)}</option>`).join("")}</select></label>
          <label class="field"><span>${UI.esc(t("common.search"))}</span><input id="s-search" placeholder="${UI.esc(t("common.village"))} / ${UI.esc(t("common.farmer"))}" /></label>
          <span class="spacer"></span>
          <button class="btn small" id="surv-export">${UI.esc(t("common.export"))}</button>
          ${App.isAdmin ? `<button class="btn small" id="surv-cleaning">${UI.esc(t("surv.cleaning"))}</button>` : ""}
        </div>
        <div id="surv-table">${UI.skeleton(5)}</div>
        <div class="toolbar" style="margin:12px 0 0"><span class="spacer"></span>
          <button class="btn small" id="surv-prev">←</button>
          <span class="muted small" id="surv-page"></span>
          <button class="btn small" id="surv-next">→</button></div>
      </div>`;

    view.querySelector("#surv-tabs").addEventListener("click", (e) => {
      const b = e.target.closest("[data-tab]");
      if (!b) return;
      this.tab = b.dataset.tab; this.filters.offset = 0;
      view.querySelectorAll("#surv-tabs button").forEach((x) => x.classList.toggle("active", x === b));
      this.load(view);
    });
    view.querySelector("#surv-new").addEventListener("click", () => this.formModal(view));
    ["#s-status", "#s-taluk"].forEach((sel) => view.querySelector(sel).addEventListener("change", (e) => {
      this.filters[sel === "#s-status" ? "status" : "taluk"] = e.target.value || undefined;
      this.filters.offset = 0; this.load(view);
    }));
    let debounce;
    view.querySelector("#s-search").addEventListener("input", (e) => {
      clearTimeout(debounce);
      debounce = setTimeout(() => { this.filters.search = e.target.value || undefined; this.filters.offset = 0; this.load(view); }, 320);
    });
    view.querySelector("#surv-prev").addEventListener("click", () => { this.filters.offset = Math.max(0, this.filters.offset - this.filters.limit); this.load(view); });
    view.querySelector("#surv-next").addEventListener("click", () => { this.filters.offset += this.filters.limit; this.load(view); });
    view.querySelector("#surv-export").addEventListener("click", () => Api.download("/api/surveys/export", { scope: this.tab === "mine" ? undefined : "all" }));
    const cl = view.querySelector("#surv-cleaning");
    if (cl) cl.addEventListener("click", () => this.cleaningModal());

    this.load(view); this.loadStats(view);
  },

  async loadStats(view) {
    try {
      const d = await Api.surveys({ limit: 1, scope: App.isAdmin ? "all" : "mine" });
      view.querySelector("#surv-stats").innerHTML = `
        <div class="stat"><div class="label">${UI.esc(t("surv.mine"))}</div><div class="value">${d.total}</div>
          <div class="sub">${App.isAdmin ? "you can see all entries" : "your own entries"}</div></div>
        <div class="stat"><div class="label">${UI.esc(t("surv.pending"))}</div><div class="value">${d.counts.pending ?? "—"}</div>
          <div class="sub">awaiting approval</div></div>
        <div class="stat"><div class="label">${UI.esc(t("surv.approved"))}</div><div class="value">${d.counts.approved}</div>
          <div class="sub">eligible for training</div></div>
        <div class="stat"><div class="label">${UI.esc(t("surv.rejected"))}</div><div class="value">${d.counts.rejected}</div>
          <div class="sub">failed cleaning / review</div></div>`;
    } catch (e) {
      view.querySelector("#surv-stats").innerHTML = `<div class="card"><p class="muted small">${UI.esc(e.message)}</p></div>`;
    }
  },

  async load(view) {
    const host = view.querySelector("#surv-table");
    host.innerHTML = UI.skeleton(5);
    const params = { ...this.filters };
    if (this.tab === "queue") params.status = "pending";
    params.scope = this.tab === "mine" ? "mine" : "all";
    try {
      const d = await Api.surveys(params);
      if (!d.total) {
        host.innerHTML = this.tab === "queue"
          ? UI.empty(t("surv.queueEmpty"), "All survey entries have been reviewed. New submissions will appear here.", "", "leaf")
          : UI.empty(t("surv.emptyTitle"), t("surv.emptyBody"),
            `<button class="btn primary" id="surv-empty-new">+ ${UI.esc(t("surv.new"))}</button>`, "table");
        const b = host.querySelector("#surv-empty-new");
        if (b) b.addEventListener("click", () => this.formModal(view));
        view.querySelector("#surv-page").textContent = "";
        return;
      }
      host.innerHTML = `<div class="table-wrap"><table>
        <thead><tr><th>${UI.esc(t("common.date"))}</th><th>${UI.esc(t("common.farmer"))} / ${UI.esc(t("common.village"))}</th>
          <th>${UI.esc(t("common.soil"))}</th><th>${UI.esc(t("common.season"))}</th><th class="num">${UI.esc(t("common.rainfall"))}</th>
          <th>Water source</th><th>${UI.esc(t("surv.cropGrown"))}</th><th>${UI.esc(t("surv.yieldOutcome"))}</th>
          <th>${UI.esc(t("common.status"))}</th><th>${UI.esc(t("common.actions"))}</th></tr></thead>
        <tbody>${d.items.map((s) => this.row(s)).join("")}</tbody></table></div>`;
      view.querySelector("#surv-page").textContent =
        `${this.filters.offset + 1}–${Math.min(this.filters.offset + this.filters.limit, d.total)} ${t("common.of")} ${d.total}`;
      host.querySelectorAll("[data-approve]").forEach((b) => b.addEventListener("click", () => this.review(b.dataset.approve, "approved", view)));
      host.querySelectorAll("[data-reject]").forEach((b) => b.addEventListener("click", () => this.review(b.dataset.reject, "rejected", view)));
      host.querySelectorAll("[data-edit]").forEach((b) => b.addEventListener("click", () => this.formModal(view, b.dataset.edit)));
      host.querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", () => this.remove(b.dataset.del, view)));
      view.querySelector("#surv-prev").disabled = this.filters.offset === 0;
      view.querySelector("#surv-next").disabled = this.filters.offset + this.filters.limit >= d.total;
    } catch (e) {
      host.innerHTML = `<div class="callout danger">${UI.esc(e.message)}</div>`;
    }
  },

  row(s) {
    const canEdit = s.user_id === App.user.id || App.isAdmin;
    return `<tr data-row="${s.id}">
      <td class="nowrap">${UI.dOnly(s.created_at)}</td>
      <td>${UI.esc(s.farmer_name)}<div class="muted small">${UI.esc(s.village)}, ${UI.esc(s.taluk)}</div></td>
      <td>${UI.esc(UI.titleCase(s.soil_type))}</td>
      <td>${UI.esc(s.season)}</td>
      <td class="num">${UI.num(s.rainfall_mm, 0)}</td>
      <td>${UI.esc(UI.titleCase(s.water_source))}<div class="muted small">${UI.esc(s.water_availability)}</div></td>
      <td>${UI.esc(UI.titleCase(s.crop_grown))}</td>
      <td>${UI.outcomeBadge(s.yield_outcome)}</td>
      <td>${UI.statusBadge(s.status)}${s.consent ? "" : ` <span class="badge red">no consent</span>`}
        ${s.review_note ? `<div class="muted small">${UI.esc(s.review_note)}</div>` : ""}</td>
      <td class="nowrap">
        ${App.isAdmin && s.status !== "approved" ? `<button class="btn small primary" data-approve="${s.id}">${UI.esc(t("surv.approve"))}</button>` : ""}
        ${App.isAdmin && s.status !== "rejected" ? `<button class="btn small" data-reject="${s.id}">${UI.esc(t("surv.reject"))}</button>` : ""}
        ${canEdit ? `<button class="btn small" data-edit="${s.id}">${UI.esc(t("common.edit"))}</button>
        <button class="btn small danger" data-del="${s.id}">${UI.esc(t("common.delete"))}</button>` : ""}
      </td></tr>`;
  },

  async review(id, status, view) {
    const row = view.querySelector(`tr[data-row="${id}"]`);
    if (row) { row.style.opacity = ".5"; }        // optimistic
    try {
      await Api.reviewSurvey(id, { status });
      UI.toast(status === "approved" ? t("surv.approvedOk") : t("surv.rejectedOk"), "ok");
      this.load(view); this.loadStats(view);
    } catch (e) {
      if (row) row.style.opacity = "";
      UI.toast(e.message, "err");
    }
  },

  async remove(id, view) {
    if (!(await UI.confirmDialog({ title: t("common.delete"), message: t("surv.deleteConfirm"), confirmLabel: t("common.delete"), danger: true }))) return;
    try { await Api.deleteSurvey(id); UI.toast(t("common.deleted"), "ok"); this.load(view); this.loadStats(view); }
    catch (e) { UI.toast(e.message, "err"); }
  },

  async formModal(view, id) {
    let item = null;
    if (id) {
      try { item = (await Api.surveys({ limit: 200, scope: App.isAdmin ? "all" : "mine" })).items.find((x) => String(x.id) === String(id)); }
      catch (e) { UI.toast(e.message, "err"); return; }
    }
    const y = item || {};
    UI.modal({
      title: id ? `${t("common.edit")} #${id}` : t("surv.new"),
      wide: true,
      body: `
        <form id="sv-form" class="form">
          <div class="grid-2">
            <label class="field"><span>${UI.esc(t("surv.farmerName"))} *</span>
              <input name="farmer_name" value="${UI.esc(y.farmer_name || App.user.name)}" required /></label>
            <label class="field"><span>${UI.esc(t("common.village"))} *</span>
              <input name="village" value="${UI.esc(y.village || App.user.village || "")}" required /></label>
          </div>
          <div class="grid-2">
            <label class="field"><span>${UI.esc(t("common.taluk"))} *</span>
              <select name="taluk">${UI.options(App.meta.taluks, y.taluk || App.user.taluk || "Mangaluru")}</select></label>
            <label class="field"><span>Phone <span class="muted small">(${UI.esc(t("common.optional"))})</span></span>
              <input name="phone" value="${UI.esc(y.phone || App.user.phone || "")}" /></label>
          </div>
          <div class="grid-2">
            <label class="field"><span>${UI.esc(t("common.soil"))} *</span>
              <select name="soil_type">${UI.options(App.meta.soil_types, y.soil_type || "laterite")}</select></label>
            <label class="field"><span>${UI.esc(t("common.season"))} *</span>
              <select name="season">${UI.options(App.meta.seasons, y.season || "Kharif")}</select></label>
          </div>
          <div class="grid-2">
            <label class="field"><span>${UI.esc(t("common.rainfall"))} (mm) *</span>
              <input type="number" name="rainfall_mm" min="0" max="1000" step="5" value="${y.rainfall_mm ?? 220}" required />
              <span class="hint">Growing-window rainfall, not the annual district total.</span></label>
            <label class="field"><span>Water source *</span>
              <select name="water_source">${UI.options(App.meta.irrigation_sources, y.water_source || "rainfed")}</select></label>
          </div>
          <div class="grid-2">
            <label class="field"><span>${UI.esc(t("surv.cropGrown"))} *</span>
              <select name="crop_grown">${UI.options(App.meta.crops_all, y.crop_grown || "rice")}</select></label>
            <label class="field"><span>${UI.esc(t("surv.yieldOutcome"))} *</span>
              <select name="yield_outcome">${UI.options(App.meta.yield_outcomes, y.yield_outcome || "good")}</select></label>
          </div>
          <label class="field"><span>${UI.esc(t("surv.area"))} <span class="muted small">(${UI.esc(t("common.optional"))})</span></span>
            <input type="number" name="area_acres" step="0.1" min="0.01" max="100" value="${y.area_acres ?? ""}" /></label>
          <label class="field"><span>${UI.esc(t("common.notes"))}</span><textarea name="notes">${UI.esc(y.notes || "")}</textarea></label>
          <label class="checkbox"><input type="checkbox" name="consent" ${y.consent === false ? "" : "checked"} />
            <span>${UI.esc(t("surv.consent"))}<span class="hint" style="display:block">${UI.esc(t("surv.consentNote"))}</span></span></label>
        </form>`,
      footer: `<button class="btn" data-close>${UI.esc(t("common.cancel"))}</button>
        <button class="btn primary" id="sv-submit">${UI.esc(id ? t("common.save") : t("surv.submit"))}</button>`,
      onMount(node, close) {
        node.querySelector("#sv-submit").addEventListener("click", async (e) => {
          const btn = e.currentTarget;
          const payload = UI.readForm(node.querySelector("#sv-form"));
          payload.rainfall_mm = Number(payload.rainfall_mm);
          if (payload.area_acres === "" || payload.area_acres === undefined) payload.area_acres = null;
          else payload.area_acres = Number(payload.area_acres);
          btn.disabled = true; btn.innerHTML = `<span class="spinner"></span>`;
          try {
            if (id) await Api.updateSurvey(id, payload);
            else await Api.createSurvey(payload);
            UI.toast(id ? t("common.updated") : t("surv.submitted"), "ok", 4800);
            close(); Pages.surveys.load(view); Pages.surveys.loadStats(view);
          } catch (err) {
            btn.disabled = false;
            btn.textContent = id ? t("common.save") : t("surv.submit");
            const msg = err.details && err.details.length ? err.details.join(" • ") : err.message;
            UI.toast(msg, "err", 7000);
          }
        });
      }
    });
  },

  async cleaningModal() {
    try {
      const d = await Api.cleaningReport();
      UI.modal({
        title: t("surv.cleaning"), wide: true,
        body: `
          <div class="grid cols-3">
            <div class="stat"><div class="label">Approved rows</div><div class="value">${d.approved_rows}</div></div>
            <div class="stat"><div class="label">Merging into training</div><div class="value">${d.rows_merging_now}</div></div>
            <div class="stat"><div class="label">Excluded by rules</div><div class="value">${d.rows_dropped}</div></div>
          </div>
          <div class="callout info" style="margin:14px 0">${UI.esc(d.note)}</div>
          <h4>Rules applied at merge time</h4>
          <div class="table-wrap"><table><thead><tr><th>#</th><th>Rule</th><th>Action</th></tr></thead>
            <tbody>${d.rules.map((r) => `<tr><td>${r.id}</td><td>${UI.esc(r.rule)}</td><td class="mono small">${UI.esc(r.action)}</td></tr>`).join("")}</tbody></table></div>
          ${d.dropped.length ? `<h4 style="margin-top:14px">Excluded rows</h4>
            <div class="table-wrap"><table><thead><tr><th>#</th><th>Crop</th><th>Reason</th></tr></thead>
            <tbody>${d.dropped.map((x) => `<tr><td>${x.id ?? "—"}</td><td>${UI.esc(x.crop_grown || x.crop || "")}</td><td class="mono small">${UI.esc(x.reason)}</td></tr>`).join("")}</tbody></table></div>` : ""}`,
        footer: `<button class="btn" data-close>${UI.esc(t("common.close"))}</button>`
      });
    } catch (e) { UI.toast(e.message, "err"); }
  }
};

window.Pages = Pages;
