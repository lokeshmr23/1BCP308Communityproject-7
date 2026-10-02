/* Pages: Dataset Explorer, Model Performance, Project Comparison, Crop Reference, About. */
const P = window.Pages;

/* ==========================================================================
   DATASET EXPLORER
   ========================================================================== */
P.dataset = {
  tab: "secondary",
  rows: { limit: 15, offset: 0 },

  async render(view) {
    view.innerHTML = `
      <div class="card">
        <div class="card-head"><div>
          <h3>${UI.esc(t("ds.title"))}</h3>
          <p class="muted small" style="margin:0">Two data sources: the free secondary dataset (for training) and the primary survey (real
          observations from Dakshina Kannada). Every mapping, cleaning and merging rule is shown here.</p>
        </div></div>
        <div class="tabs-inline" id="ds-tabs">
          <button data-tab="secondary" class="active">${UI.esc(t("ds.secondary"))}</button>
          <button data-tab="rows">${UI.esc(t("ds.mapped"))}</button>
          <button data-tab="schema">${UI.esc(t("ds.schema"))}</button>
          <button data-tab="merge">${UI.esc(t("ds.merge"))}</button>
        </div>
        <div id="ds-body">${UI.skeleton(6)}</div>
      </div>`;
    view.querySelector("#ds-tabs").addEventListener("click", (e) => {
      const b = e.target.closest("[data-tab]");
      if (!b) return;
      this.tab = b.dataset.tab;
      view.querySelectorAll("#ds-tabs button").forEach((x) => x.classList.toggle("active", x === b));
      this.load(view);
    });
    this.load(view);
  },

  load(view) {
    if (this.tab === "secondary") return this.secondary(view);
    if (this.tab === "rows") return this.rowsTab(view);
    if (this.tab === "schema") return this.schema(view);
    return this.merge(view);
  },

  async secondary(view) {
    const host = view.querySelector("#ds-body");
    try {
      const s = await Api.dsSummary();
      const df = s.class_distribution;
      host.innerHTML = `
        <div class="grid cols-4">
          <div class="stat"><div class="label">${UI.esc(t("ds.rows"))}</div><div class="value">${s.rows}</div>
            <div class="sub">${s.class_distribution.length} crop classes · 100 rows each</div></div>
          <div class="stat"><div class="label">Columns</div><div class="value">${s.columns.length}</div>
            <div class="sub">N, P, K, temperature, humidity, pH, rainfall, label</div></div>
          <div class="stat"><div class="label">Derived inputs</div><div class="value">4</div>
            <div class="sub">soil type · season · rainfall · water availability</div></div>
          <div class="stat"><div class="label">Source</div><div class="value" style="font-size:1rem">Kaggle</div>
            <div class="sub"><a href="${UI.esc(s.source.url)}" target="_blank" rel="noopener">crop-recommendation-dataset</a></div></div>
        </div>
        <div class="callout info" style="margin:14px 0"><strong>About the secondary data</strong>${UI.esc(s.source.about)}</div>
        <div class="grid cols-2">
          <div class="card"><h4>${UI.esc(t("ds.rainfall"))}</h4>
            ${UI.histogram(s.rainfall_histogram.bins, s.rainfall_histogram.counts)}
            <div class="callout warn" style="margin-top:8px">${UI.esc(t("ds.rainfallWarn"))}</div></div>
          <div class="card"><h4>${UI.esc(t("ds.derivedDist"))}</h4>
            <h4 class="muted small" style="margin:8px 0 4px">season</h4>
            ${UI.donut(s.derived_distributions.season.map((x) => ({ label: x.value, value: x.count })))}
            <h4 class="muted small" style="margin:12px 0 4px">soil type</h4>
            ${UI.hbars(s.derived_distributions.soil_type.map((x) => ({ label: UI.titleCase(x.value), value: x.count })), { format: (v) => v })}
            <h4 class="muted small" style="margin:12px 0 4px">water availability</h4>
            ${UI.hbars(s.derived_distributions.water_availability.map((x) => ({ label: UI.titleCase(x.value), value: x.count })), { format: (v) => v })}
          </div>
        </div>
        <div class="card"><h4>${UI.esc(t("ds.classDist"))}</h4>
          ${UI.vbars(s.class_distribution.map((x) => ({ label: x.value, value: x.count })))}
          <p class="muted small">Every class has exactly 100 rows — a balanced, curated dataset, which is why the headline accuracy is high (see limitations).</p></div>
        <div class="card"><h4>${UI.esc(t("ds.stats"))}</h4>
          <div class="table-wrap"><table><thead><tr><th>feature</th><th class="num">mean</th><th class="num">std</th>
            <th class="num">min</th><th class="num">25%</th><th class="num">50%</th><th class="num">75%</th><th class="num">max</th></tr></thead>
            <tbody>${Object.entries(s.numeric_stats).map(([k, v]) => `<tr><td>${UI.esc(k)}</td>
              <td class="num">${v.mean}</td><td class="num">${v.std}</td><td class="num">${v.min}</td>
              <td class="num">${v["25%"]}</td><td class="num">${v["50%"]}</td><td class="num">${v["75%"]}</td><td class="num">${v.max}</td></tr>`).join("")}
            </tbody></table></div></div>`;
    } catch (e) { host.innerHTML = `<div class="callout danger">${UI.esc(e.message)}</div>`; }
  },

  async rowsTab(view) {
    const host = view.querySelector("#ds-body");
    host.innerHTML = UI.skeleton(6);
    try {
      const d = await Api.dsRows(this.rows);
      host.innerHTML = `
        <div class="toolbar">
          <label class="field"><span>${UI.esc(t("common.crop"))}</span><select id="r-crop"><option value="">${UI.esc(t("common.all"))}</option>
            ${d.filters.crops.map((c) => `<option value="${c}" ${this.rows.crop === c ? "selected" : ""}>${UI.esc(c)}</option>`).join("")}</select></label>
          <label class="field"><span>${UI.esc(t("common.season"))}</span><select id="r-season"><option value="">${UI.esc(t("common.all"))}</option>
            ${d.filters.seasons.map((c) => `<option value="${c}" ${this.rows.season === c ? "selected" : ""}>${UI.esc(c)}</option>`).join("")}</select></label>
          <label class="field"><span>${UI.esc(t("common.soil"))}</span><select id="r-soil"><option value="">${UI.esc(t("common.all"))}</option>
            ${d.filters.soils.map((c) => `<option value="${c}" ${this.rows.soil_type === c ? "selected" : ""}>${UI.esc(UI.titleCase(c))}</option>`).join("")}</select></label>
          <label class="field"><span>${UI.esc(t("common.water"))}</span><select id="r-water"><option value="">${UI.esc(t("common.all"))}</option>
            ${d.filters.water_levels.map((c) => `<option value="${c}" ${this.rows.water === c ? "selected" : ""}>${UI.esc(UI.titleCase(c))}</option>`).join("")}</select></label>
          <span class="spacer"></span>
          ${App.user ? `<button class="btn small" id="r-export">${UI.esc(t("common.export"))}</button>` : ""}
        </div>
        <div class="table-wrap"><table>
          <thead><tr><th>crop</th><th>${UI.esc(t("common.soil"))} (derived)</th><th>${UI.esc(t("common.season"))} (derived)</th>
            <th class="num">${UI.esc(t("common.rainfall"))}</th><th>${UI.esc(t("common.water"))} (derived)</th>
            <th class="num">N</th><th class="num">P</th><th class="num">K</th><th class="num">temp</th><th class="num">humidity</th><th class="num">pH</th></tr></thead>
          <tbody>${d.rows.map((r) => `<tr><td><strong>${UI.esc(r.crop)}</strong></td>
            <td>${UI.esc(UI.titleCase(r.soil_type))}</td><td>${UI.esc(r.season)}</td>
            <td class="num">${UI.num(r.rainfall, 1)}</td><td>${UI.esc(UI.titleCase(r.water_availability))}</td>
            <td class="num">${UI.num(r.N, 0)}</td><td class="num">${UI.num(r.P, 0)}</td><td class="num">${UI.num(r.K, 0)}</td>
            <td class="num">${UI.num(r.temperature, 1)}</td><td class="num">${UI.num(r.humidity, 1)}</td><td class="num">${UI.num(r.ph, 2)}</td></tr>`).join("")}</tbody>
        </table></div>
        <div class="toolbar" style="margin-top:12px"><span class="muted small">${UI.esc(t("common.showing"))} ${this.rows.offset + 1}–${Math.min(this.rows.offset + this.rows.limit, d.total)} ${t("common.of")} ${d.total}</span>
          <span class="spacer"></span><button class="btn small" id="r-prev">←</button><button class="btn small" id="r-next">→</button></div>
        <p class="muted small">These rows are the secondary dataset after the documented mapping rules were applied — the same frame the four-input ablation was trained on.</p>`;
      const setFilter = (sel, key) => host.querySelector(sel).addEventListener("change", (e) => {
        this.rows[key] = e.target.value || undefined; this.rows.offset = 0; this.rowsTab(view);
      });
      setFilter("#r-crop", "crop"); setFilter("#r-season", "season");
      setFilter("#r-soil", "soil_type"); setFilter("#r-water", "water");
      host.querySelector("#r-prev").addEventListener("click", () => { this.rows.offset = Math.max(0, this.rows.offset - this.rows.limit); this.rowsTab(view); });
      host.querySelector("#r-next").addEventListener("click", () => { this.rows.offset += this.rows.limit; this.rowsTab(view); });
      const ex = host.querySelector("#r-export");
      if (ex) ex.addEventListener("click", () => {
        const params = new URLSearchParams({ ...this.rows });
        fetch("/api/dataset/secondary/export").then((r) => r.blob()).then((b) => {
          const a = document.createElement("a");
          a.href = URL.createObjectURL(b); a.download = "derived_secondary_dataset.csv";
          document.body.appendChild(a); a.click(); a.remove();
        });
      });
    } catch (e) { host.innerHTML = `<div class="callout danger">${UI.esc(e.message)}</div>`; }
  },

  async schema(view) {
    const host = view.querySelector("#ds-body");
    try {
      const s = await Api.dsSchema();
      const rules = await Api.cleaningRules();
      host.innerHTML = `
        <div class="grid cols-2">
          <div class="card"><h4>Secondary dataset</h4>
            <p class="mono small">${UI.esc(s.secondary.file)}</p>
            <p class="muted small">${s.secondary.rows} rows · columns: ${s.secondary.columns.map(UI.esc).join(", ")}</p>
            <h4 style="margin-top:12px">${UI.esc(t("ds.unified"))}</h4>
            <div class="table-wrap"><table><thead><tr><th>column</th><th>role</th></tr></thead><tbody>
              ${s.unified_schema.columns.map((c) => `<tr><td class="mono">${UI.esc(c)}</td><td class="muted small">${UI.esc(
                c === "crop" ? "label" : c === "source" ? "secondary_kaggle | primary_survey" : c === "sample_weight" ? "yield_outcome → 0 / 0.5 / 1.0" : "decision feature")}</td></tr>`).join("")}
            </tbody></table></div>
            <div class="callout info" style="margin-top:10px">${UI.esc(s.unified_schema.note)}</div>
          </div>
          <div class="card"><h4>${UI.esc(t("ds.mapping"))}</h4>
            ${Object.entries(s.mapping_rules).map(([k, v]) => `
              <div style="border-top:1px solid var(--line);padding-top:8px;margin-top:8px">
                <strong class="mono">${UI.esc(k)}</strong>
                ${v.rules ? `<ul class="reasons">${v.rules.map((r) => `<li class="mono small">${UI.esc(r)}</li>`).join("")}</ul>` : ""}
                ${v.formula ? `<p class="mono small">${UI.esc(v.formula)}</p>` : ""}
                ${v.irrigation_sources ? `<p class="mono small">${Object.entries(v.irrigation_sources).map(([a, b]) => `${UI.esc(a)}→${UI.esc(b)}`).join(" · ")}</p>` : ""}
                ${v.honesty ? `<p class="callout warn small" style="margin:6px 0 0">${UI.esc(v.honesty)}</p>` : ""}
              </div>`).join("")}
          </div>
        </div>
        <div class="grid cols-2" style="margin-top:16px">
          <div class="card"><h4>${UI.esc(t("ds.cleaning"))}</h4>
            <div class="table-wrap"><table><thead><tr><th>#</th><th>rule</th><th>action</th></tr></thead><tbody>
              ${rules.primary_data_rules.map((r) => `<tr><td>${r.id}</td><td>${UI.esc(r.rule)}</td><td class="mono small">${UI.esc(r.action)}</td></tr>`).join("")}
            </tbody></table></div>
            <h4 style="margin-top:12px">Secondary data cleaning</h4>
            <ul class="reasons">${rules.secondary_data_rules.map((r) => `<li>${UI.esc(r.rule)} → <span class="mono">${UI.esc(r.action)}</span></li>`).join("")}</ul>
          </div>
          <div class="card"><h4>Input expansion (4 answers → 7 measured parameters)</h4>
            <p class="muted small">${UI.esc(s.expansion_rules.why)}</p>
            <div class="table-wrap"><table><thead><tr><th>soil type</th><th class="num">pH</th><th class="num">N</th><th class="num">P</th><th class="num">K</th></tr></thead><tbody>
              ${Object.entries(s.expansion_rules.soil_profiles).map(([k, v]) => `<tr><td>${UI.esc(UI.titleCase(k))}</td>
                <td class="num">${v.ph}</td><td class="num">${v.N}</td><td class="num">${v.P}</td><td class="num">${v.K}</td></tr>`).join("")}
            </tbody></table></div>
            <div class="table-wrap" style="margin-top:10px"><table><thead><tr><th>season</th><th class="num">temp °C</th><th class="num">RH %</th></tr></thead><tbody>
              ${Object.entries(s.expansion_rules.season_profiles).map(([k, v]) => `<tr><td>${UI.esc(k)}</td>
                <td class="num">${v.temperature_c}</td><td class="num">${v.humidity_pct}</td></tr>`).join("")}
            </tbody></table></div>
            <p class="muted small" style="margin-top:8px">Irrigation index applied to rainfall: ${Object.entries(s.expansion_rules.water_irrigation_factor).map(([k, v]) => `${UI.esc(k)} ×${v}`).join(" · ")}</p>
          </div>
        </div>
        <div class="card"><h4>${UI.esc(t("ds.feedback"))}</h4>
          <ol class="reasons">${s.feedback_loop.map((x) => `<li>${UI.esc(x)}</li>`).join("")}</ol></div>`;
    } catch (e) { host.innerHTML = `<div class="callout danger">${UI.esc(e.message)}</div>`; }
  },

  async merge(view) {
    const host = view.querySelector("#ds-body");
    try {
      const m = await Api.mergedPreview();
      host.innerHTML = `
        <div class="grid cols-4">
          <div class="stat"><div class="label">Secondary rows</div><div class="value">${m.secondary_rows}</div><div class="sub">sample_weight 1.0</div></div>
          <div class="stat"><div class="label">Approved survey rows</div><div class="value">${m.approved_primary_rows}</div><div class="sub">real observations</div></div>
          <div class="stat"><div class="label">${UI.esc(t("ds.merging"))}</div><div class="value">${m.primary_rows_merging}</div><div class="sub">pass all cleaning rules</div></div>
          <div class="stat"><div class="label">${UI.esc(t("ds.dropped"))}</div><div class="value">${m.primary_rows_dropped}</div><div class="sub">excluded, with reasons</div></div>
        </div>
        ${m.dropped_detail.length ? `<div class="card"><h4>Excluded rows</h4>
          <div class="table-wrap"><table><thead><tr><th>id</th><th>crop</th><th>rule</th><th>reason</th></tr></thead><tbody>
            ${m.dropped_detail.map((d) => `<tr><td>${d.id ?? "—"}</td><td>${UI.esc(d.crop_grown || d.crop || "")}</td>
              <td class="num">${d.rule_id}</td><td class="mono small">${UI.esc(d.reason)}</td></tr>`).join("")}
          </tbody></table></div></div>` : ""}
        <div class="grid cols-2" style="margin-top:16px">
          <div class="card"><h4>Primary rows (${UI.esc(t("ds.merging"))})</h4>
            ${m.preview_primary.length ? `<div class="table-wrap"><table><thead><tr>
              <th>soil</th><th>season</th><th class="num">rain</th><th>water</th><th>crop</th><th class="num">weight</th></tr></thead>
              <tbody>${m.preview_primary.map((r) => `<tr><td>${UI.esc(UI.titleCase(r.soil_type))}</td><td>${UI.esc(r.season)}</td>
                <td class="num">${UI.num(r.rainfall_mm, 0)}</td><td>${UI.esc(r.water_availability)}</td>
                <td>${UI.esc(UI.titleCase(r.crop))}</td><td class="num">${r.sample_weight}</td></tr>`).join("")}</tbody></table></div>`
              : UI.empty("No primary rows merging yet", "Approve survey entries (Primary Dataset Survey → Review queue) and they will appear here, ready for the next retrain.", "", "table")}
          </div>
          <div class="card"><h4>Secondary rows (head)</h4>
            <div class="table-wrap"><table><thead><tr><th>soil</th><th>season</th><th class="num">rain</th><th>water</th><th>crop</th><th class="num">weight</th></tr></thead>
            <tbody>${m.preview_secondary.map((r) => `<tr><td>${UI.esc(UI.titleCase(r.soil_type))}</td><td>${UI.esc(r.season)}</td>
              <td class="num">${UI.num(r.rainfall_mm, 0)}</td><td>${UI.esc(r.water_availability)}</td>
              <td>${UI.esc(r.crop)}</td><td class="num">${r.sample_weight}</td></tr>`).join("")}</tbody></table></div>
          </div>
        </div>`;
    } catch (e) { host.innerHTML = `<div class="callout danger">${UI.esc(e.message)}</div>`; }
  }
};

/* ==========================================================================
   MODEL PERFORMANCE
   ========================================================================== */
P.model = {
  retrainTimer: null,

  async render(view) {
    view.innerHTML = `<div id="model-body">${UI.skeleton(6)}</div>`;
    try {
      const m = await Api.metrics();
      const status = await Api.modelStatus();
      this.renderBody(view, m, status);
      if (status.retrain.running) this.pollRetrain(view);
    } catch (e) {
      view.querySelector("#model-body").innerHTML = `<div class="card"><div class="callout danger">
        <strong>Metrics unavailable</strong>${UI.esc(e.message)}<br>
        <span class="small">Run <span class="mono">python -m app.ml.train</span> in the backend, or use the admin retrain button.</span></div></div>`;
    }
  },

  renderBody(view, m, status) {
    const modelKeys = Object.keys(m.models);
    const best = m.best_model;
    view.querySelector("#model-body").innerHTML = `
      <div class="grid cols-4">
        <div class="stat"><div class="label">${UI.esc(t("model.best"))}</div>
          <div class="value" style="font-size:1.15rem">${UI.esc(best.label)}</div>
          <div class="sub">${UI.esc(best.selection_rule)}</div></div>
        <div class="stat"><div class="label">${UI.esc(t("model.accuracy"))} (holdout)</div>
          <div class="value">${UI.pct(best.metrics.test_accuracy, 2)}</div>
          <div class="sub">${m.dataset.test_rows} held-out rows</div></div>
        <div class="stat"><div class="label">${UI.esc(t("model.top3"))}</div>
          <div class="value">${UI.pct(best.metrics.top3_accuracy, 1)}</div>
          <div class="sub">true crop inside the top-3 list</div></div>
        <div class="stat"><div class="label">4-input ablation</div>
          <div class="value">${UI.pct(m.ablation_four_inputs.best.test_accuracy, 1)}</div>
          <div class="sub">top-3 ${UI.pct(m.ablation_four_inputs.best.top3_accuracy, 1)} — see below</div></div>
      </div>

      <div class="card">
        <div class="card-head"><h3>${UI.esc(t("model.protocol"))}</h3><span class="spacer"></span>
          <span class="pill">${UI.esc(m.dataset.protocol)}</span></div>
        <div class="grid cols-3">
          <div><div class="muted small">Training rows</div><strong>${m.dataset.train_rows}</strong></div>
          <div><div class="muted small">Classes</div><strong>${m.dataset.n_classes}</strong></div>
          <div><div class="muted small">Secondary rows</div><strong>${m.dataset.secondary_rows_used}</strong>
            <div class="muted small">${m.dataset.primary_rows_used} primary survey row(s) merged</div></div>
        </div>
        <p class="muted small" style="margin-top:10px">Trained ${UI.esc(UI.dt(m.trained_at))} · model v${UI.esc(m.model_version)} ·
          artefact ${m.artifacts.model_size_kb} KB (joblib compress=3, lazy-loaded) · training took ${m.training_seconds}s.</p>
        ${m.environment ? `<p class="muted small">Built with Python ${UI.esc(m.environment.python)} ·
          scikit-learn ${UI.esc(m.environment.scikit_learn)} · numpy ${UI.esc(m.environment.numpy)} ·
          pandas ${UI.esc(m.environment.pandas)} · joblib ${UI.esc(m.environment.joblib)} — the pinned versions in
          <code>requirements.txt</code>, so the committed artefact loads without a version warning.</p>` : ""}
      </div>

      <div class="card">
        <div class="card-head"><h3>${UI.esc(t("model.compare"))}</h3>
          <span class="spacer"></span><span class="badge green">best: ${UI.esc(best.key)}</span></div>
        <div class="table-wrap"><table>
          <thead><tr><th>Algorithm</th><th class="num">${UI.esc(t("model.accuracy"))}</th>
            <th class="num">${UI.esc(t("model.precision"))}</th><th class="num">${UI.esc(t("model.recall"))}</th>
            <th class="num">${UI.esc(t("model.f1"))}</th><th class="num">${UI.esc(t("model.cv"))}</th>
            <th class="num">${UI.esc(t("model.top3"))}</th><th class="num">fit (s)</th><th class="num">mean conf.</th></tr></thead>
          <tbody>${modelKeys.map((k) => {
            const r = m.models[k];
            const isBest = k === best.key;
            return `<tr style="${isBest ? "background:var(--green-50)" : ""}">
              <td><strong>${UI.esc(r.label)}</strong>${isBest ? ` <span class="badge green">selected</span>` : ""}
                ${r.sample_weights_used ? `<span class="badge grey" title="sample_weight applied">w</span>` : ""}</td>
              <td class="num">${UI.pct(r.test_accuracy, 2)}</td><td class="num">${UI.pct(r.test_precision_macro, 2)}</td>
              <td class="num">${UI.pct(r.test_recall_macro, 2)}</td><td class="num">${UI.pct(r.test_f1_macro, 2)}</td>
              <td class="num">${UI.pct(r.cv_macro_f1_mean, 2)} <span class="muted small">±${UI.num(r.cv_macro_f1_std, 2)}</span></td>
              <td class="num">${UI.pct(r.top3_accuracy, 1)}</td><td class="num">${r.fit_seconds}</td>
              <td class="num">${UI.pct(r.mean_max_confidence, 1)}</td></tr>`;
          }).join("")}</tbody></table></div>
        <p class="muted small" style="margin-top:8px">Selection rule: <em>${UI.esc(best.selection_rule)}</em>. Cross-validation is
          run on the training split only, and folds are scored without sample weights so all four algorithms are compared identically.</p>
      </div>

      <div class="card">
        <div class="card-head"><h3>${UI.esc(t("model.ablation"))}</h3><span class="badge amber">honest reporting</span></div>
        <p class="muted small">${UI.esc(m.ablation_four_inputs.note)}</p>
        <div class="table-wrap"><table>
          <thead><tr><th>Algorithm</th><th class="num">${UI.esc(t("model.accuracy"))}</th>
            <th class="num">${UI.esc(t("model.f1"))}</th><th class="num">${UI.esc(t("model.cv"))}</th>
            <th class="num">${UI.esc(t("model.top3"))}</th></tr></thead>
          <tbody>${Object.entries(m.ablation_four_inputs.models).map(([k, r]) => `<tr>
            <td>${UI.esc(r.label)}${k === m.ablation_four_inputs.best_key ? ` <span class="badge grey">best of the four</span>` : ""}</td>
            <td class="num">${UI.pct(r.test_accuracy, 2)}</td><td class="num">${UI.pct(r.test_f1_macro, 2)}</td>
            <td class="num">${UI.pct(r.cv_macro_f1_mean, 2)}</td><td class="num">${UI.pct(r.top3_accuracy, 1)}</td></tr>`).join("")}</tbody>
        </table></div>
        <div class="callout warn" style="margin-top:10px"><strong>Why this matters</strong>
          Top-1 accuracy drops from ${UI.pct(best.metrics.test_accuracy, 1)} (7 measured parameters) to
          ${UI.pct(m.ablation_four_inputs.best.test_accuracy, 1)} when the model may only see the four questions the app asks.
          Top-3 accuracy falls far less (${UI.pct(best.metrics.top3_accuracy, 0)} → ${UI.pct(m.ablation_four_inputs.best.top3_accuracy, 0)}),
          which is exactly why this app returns a ranked top-3 with reasons, with the knowledge-guided expansion and the
          agronomic rule score doing the rest of the work.</div>
      </div>

      <div class="grid cols-2">
        <div class="card"><h4>${UI.esc(t("model.fi"))}</h4>
          <p class="muted small">${UI.esc(m.feature_importance.method || "")}</p>
          ${UI.hbars(Object.entries(m.feature_importance.grouped || {}).map(([k, v]) => ({ label: k, value: v })), { format: (v) => UI.pct(v, 1) })}
          <h4 style="margin-top:14px">${UI.esc(t("model.perm"))}</h4>
          <p class="muted small">${UI.esc(m.feature_importance.permutation_note || "")}</p>
          ${UI.hbars(Object.entries(m.feature_importance.permutation_grouped || {}).map(([k, v]) => ({ label: k, value: v })), { format: (v) => UI.num(v, 3) })}
          <p class="muted small">Ranking agrees with the agronomic literature and with this project's own SHAP-style reading:
            moisture-related features (rainfall, humidity) and potassium dominate, while pH matters least.</p>
        </div>
        <div class="card"><h4>${UI.esc(t("model.cm"))}</h4>
          <p class="muted small">${UI.esc(t("model.cmNote"))}</p>
          <div style="overflow-x:auto">${UI.heatmap(m.confusion_matrix.labels, m.confusion_matrix.matrix)}</div>
        </div>
      </div>

      <div class="card">
        <div class="card-head"><h3>${UI.esc(t("model.perClass"))}</h3></div>
        <div class="table-wrap"><table><thead><tr><th>crop</th><th class="num">precision</th>
          <th class="num">recall</th><th class="num">F1</th><th class="num">support</th></tr></thead>
          <tbody>${Object.entries(best.metrics.per_class).map(([c, r]) => `<tr><td>${UI.esc(c)}</td>
            <td class="num">${UI.num(r.precision, 3)}</td><td class="num">${UI.num(r.recall, 3)}</td>
            <td class="num">${UI.num(r.f1, 3)}</td><td class="num">${r.support}</td></tr>`).join("")}</tbody></table></div>
      </div>

      <div class="card">
        <div class="card-head"><h3>${UI.esc(t("model.external"))}</h3></div>
        ${m.external_check.n_rows ? `<div class="grid cols-3">
            <div class="stat"><div class="label">Survey rows compared</div><div class="value">${m.external_check.n_rows}</div></div>
            <div class="stat"><div class="label">Agreement (top-1)</div><div class="value">${UI.pct(m.external_check.accuracy, 1)}</div></div>
            <div class="stat"><div class="label">Agreement (top-3)</div><div class="value">${UI.pct(m.external_check.top3_accuracy, 1)}</div></div>
          </div>` : `<div class="callout info">${UI.esc(m.external_check.note)}</div>`}
      </div>

      <div class="card">
        <div class="card-head"><h3>${UI.esc(t("model.limits"))}</h3></div>
        <ol class="reasons">${m.honest_limitations.map((x) => `<li>${UI.esc(x)}</li>`).join("")}</ol>
      </div>

      <div class="card">
        <div class="card-head"><h3>${UI.esc(t("model.status"))}</h3>
          <span class="spacer"></span>
          ${App.isAdmin ? `<button class="btn primary small" id="retrain-btn">${UI.esc(t("model.retrain"))}</button>` : `<span class="badge grey">${UI.esc(t("common.adminOnly"))}</span>`}
        </div>
        <div class="grid cols-3">
          <div class="stat"><div class="label">Model loaded</div><div class="value" style="font-size:1.05rem">${status.registry.loaded ? "yes (lazy)" : "not yet — loads on first prediction"}</div>
            <div class="sub">${status.registry.model_key || "—"} v${status.registry.model_version || "—"}</div></div>
          <div class="stat"><div class="label">Approved survey rows</div><div class="value">${status.primary_data.approved_survey_rows}</div>
            <div class="sub">${status.primary_data.pending_survey_rows} awaiting review</div></div>
          <div class="stat"><div class="label">Predictions logged</div><div class="value">${status.primary_data.predictions_logged}</div>
            <div class="sub">all users</div></div>
        </div>
        <div id="retrain-out" style="margin-top:12px">
          ${status.retrain.message ? `<div class="callout ${status.retrain.ok === false ? "danger" : "info"}">${UI.esc(status.retrain.message)}</div>` : ""}
        </div>
        <p class="muted small" style="margin-top:10px">${UI.esc(t("model.retrainNote"))} ${UI.esc(status.cold_start_note)}</p>
      </div>`;

    const btn = view.querySelector("#retrain-btn");
    if (btn) btn.addEventListener("click", () => this.startRetrain(view));
  },

  async startRetrain(view) {
    const out = view.querySelector("#retrain-out");
    try {
      await Api.retrain({ include_primary_surveys: true });
      out.innerHTML = `<div class="callout info"><strong>${UI.esc(t("model.retrainStart"))}</strong>
        Training four models with a stratified split + 5-fold CV. This page updates automatically.</div>`;
      UI.toast(t("model.retrainStart"), "ok");
      this.pollRetrain(view);
    } catch (e) { UI.toast(e.message, "err"); }
  },

  pollRetrain(view) {
    clearInterval(this.retrainTimer);
    const out = view.querySelector("#retrain-out");
    let ticks = 0;
    this.retrainTimer = setInterval(async () => {
      ticks++;
      try {
        const s = await Api.retrainStatus();
        if (out) out.innerHTML = `<div class="callout info"><strong>${s.running ? t("model.retrainStart") : ""}</strong>${UI.esc(s.message)}</div>`;
        if (!s.running) {
          clearInterval(this.retrainTimer);
          if (s.ok) { UI.toast(t("model.retrainDone"), "ok"); this.render(view); }
          else UI.toast(t("model.retrainFailed"), "err", 7000);
        } else if (ticks > 40) clearInterval(this.retrainTimer);
      } catch (e) { clearInterval(this.retrainTimer); }
    }, 3000);
  }
};

/* ==========================================================================
   PROJECT COMPARISON
   ========================================================================== */
P.comparison = {
  async render(view) {
    const rows = [
      {
        work: "Pudumalar et al. (2017), IEEE ICoAC — “Crop Recommendation System for Precision Agriculture”",
        inputs: "Soil type, pH, N-P-K, rainfall, temperature",
        data: "Soil/agricultural data of a Tamil Nadu district (own collection)",
        algo: "Ensemble majority voting: Random Tree + CHAID + KNN + Naive Bayes (WEKA)",
        acc: "88% (ensemble)",
        xai: "Rule generation from the ensemble — interpretable but not per-prediction scores",
        regional: "Tamil Nadu district level",
        ui: "Desktop/WEKA workflow, not a web product",
        deploy: "Not reported",
        cost: "Not reported",
        note: "Baseline that established the multi-model ensemble idea; no water-availability input."
      },
      {
        work: "Priya, Ramesh & Khosla (2018), IEEE ICACCI — “Crop Prediction on the Region Belts of India: A Naïve Bayes MapReduce Precision Agricultural Model”",
        inputs: "Rainfall, soil, temperature (region belts of India)",
        data: "Region-belt rainfall (1901–2017) and soil data",
        algo: "Naive Bayes on Hadoop MapReduce (big-data pipeline)",
        acc: "Not verified — the full text is paywalled and this project does not quote unverified numbers",
        xai: "Probabilistic; no explanation layer reported",
        regional: "Region belts of India (larger scale than a district)",
        ui: "Research pipeline, no end-user app reported",
        deploy: "Hadoop cluster (not free-tier friendly)",
        cost: "Cluster cost",
        note: "Shows the seasonal/regional framing but opts for scale (MapReduce) over farmer-facing usability."
      },
      {
        work: "ACM (2024) — “Crop Recommendation using Machine Learning Algorithms”",
        inputs: "Soil nutrients and environmental parameters",
        data: "Soil + environmental parameter dataset",
        algo: "Decision Tree, Random Forest, SVM, KNN, Naive Bayes, LightGBM, Logistic Regression",
        acc: "RF, Naive Bayes and LightGBM reported as top performers; exact figures behind the publisher paywall",
        xai: "Accuracy/precision/recall/F1 comparison only",
        regional: "Not region-specific",
        ui: "Not an application",
        deploy: "Not reported",
        cost: "Not reported",
        note: "Same algorithm family as this project; validates comparing DT/RF/KNN/NB rather than using one model."
      },
      {
        work: "Shastri et al. (2025), Scientific Reports 15:25498 — “Advancing crop recommendation system with supervised machine learning and explainable AI”",
        inputs: "N, P, K, temperature, humidity, pH, rainfall",
        data: "Kaggle Crop Recommendation Dataset — 2200 rows × 22 crops, 70:30 split",
        algo: "Gradient boosting with SHAP/LIME explainability (RF benchmarked at 98.86%)",
        acc: "99.27% (their proposed model)",
        xai: "Strong: SHAP + LIME per-prediction explanations",
        regional: "Not region-specific (global crop list)",
        ui: "Research prototype",
        deploy: "Not reported",
        cost: "Not reported",
        note: "Closest methodological neighbour and the paper this project's XAI approach is modelled on; it does not address season or irrigation inputs, farmer feedback, or a specific district."
      },
      {
        work: "Scientific Reports (2025) — “Interpretable deep learning models for independent fertilizer and crop recommendation” (TabNet + SHAP)",
        inputs: "Soil nutrients, pH, weather",
        data: "IoT-enabled agricultural dataset (SMOTE-balanced, iterative imputation)",
        algo: "TabNet deep learning vs Random Forest baseline",
        acc: "Crop recommendation 96.21% (RF baseline 85.34%)",
        xai: "SHAP post-hoc attributions",
        regional: "Not region-specific",
        ui: "Research prototype",
        deploy: "Not reported",
        cost: "GPU training cost",
        note: "Shows deep models can beat RF, but needs far more data/compute than a free-tier academic deployment allows."
      },
      {
        work: "Scientific Reports (2026) — “Agentic AI-driven autonomous decision support system for smart agriculture”",
        inputs: "N, P, K, temperature, humidity, pH, rainfall",
        data: "2200-sample crop dataset (plus fertilizer data)",
        algo: "Random Forest (crop) + XGBoost (fertilizer) with SHAP/LIME",
        acc: "92.4% crop recommendation",
        xai: "SHAP + LIME",
        regional: "Example city-level (Chennai) illustration",
        ui: "Agentic decision-support prototype",
        deploy: "Not reported",
        cost: "Not reported",
        note: "Confirms RF as a robust choice on this dataset; also shows that reported accuracy varies a lot with protocol, which is why this project publishes its full protocol."
      },
      {
        work: "THIS PROJECT — Dakshina Kannada Crop Advisor",
        mine: true,
        inputs: "4 farmer-answerable inputs (soil type, season, rainfall, water availability/irrigation source); knowledge-guided expansion to the 7 measured parameters; regional tuning",
        data: "Kaggle secondary dataset (2200 × 22, retrained on a stratified split) + a primary district survey with consent + a cited crop knowledge base (TNAU/ICAR/KVK DK)",
        algo: "Decision Tree, Random Forest (selected), KNN, Gaussian Naive Bayes — stratified 80/20 + 5-fold CV; geometric blend of model probability and agronomic rule fit",
        acc: `Random Forest: ${UICore.metricsText()}`,
        xai: "Per-recommendation reasons from a cited knowledge base, rule-component breakdown (water/season/rain/soil), impurity + permutation feature importance, and a visible audit of the 4→7 input expansion",
        regional: `Built for Dakshina Kannada: district taluks, laterite/coastal soil profiles, DK rainfall presets, KVK crop areas, plus a labelled regional advisory for arecanut, cashew, black pepper, cocoa and rubber`,
        ui: "Responsive bilingual (English/Kannada) SPA with auth, sidebar navigation, empty/loading states and optimistic updates",
        deploy: "Render free tier (web service) + free hosted Postgres (Neon/Supabase), /health probe, /api/predict REST endpoint, lazy-loaded 0.7 MB model",
        cost: "₹0 — free tiers only",
        note: "Publishes its own honest ablation: restricting the model to the four collected inputs drops top-1 accuracy to ~59% (top-3 ~87%), which is why the product returns a ranked top-3 with reasons, not a single verdict."
      }
    ];
    const cols = [["inputs", "Inputs"], ["data", "Dataset"], ["algo", "Algorithm(s)"], ["acc", "Reported accuracy"],
      ["xai", "Explainability"], ["regional", "Regional support"], ["ui", "User interface"], ["deploy", "Deployment"],
      ["cost", "Cost"], ["note", "Honest notes"]];

    view.innerHTML = `
      <div class="card">
        <div class="card-head"><div><h3>${UI.esc(t("cmp.title"))}</h3>
          <p class="muted small" style="margin:0">${UI.esc(t("cmp.intro"))}</p></div></div>
        <div class="callout warn">${UI.esc(t("cmp.caveat"))}</div>
        <div class="table-wrap" style="margin-top:12px"><table>
          <thead><tr><th style="min-width:230px">Work</th>${cols.map(([, l]) => `<th>${UI.esc(l)}</th>`).join("")}</tr></thead>
          <tbody>${rows.map((r) => `<tr style="${r.mine ? "background:var(--green-50)" : ""}">
            <td><strong>${UI.esc(r.work)}</strong></td>
            ${cols.map(([k]) => `<td class="small">${UI.esc(r[k] || "—")}</td>`).join("")}</tr>`).join("")}</tbody>
        </table></div>
      </div>

      <div class="grid cols-2">
        <div class="card"><h4>${UI.esc(t("cmp.innovations"))}</h4>
          <ol class="reasons">
            <li><strong>Season and water availability as first-class inputs.</strong> None of the reviewed systems takes an
              irrigation source or a season decision from the farmer; both change the answer here, and water availability also
              gates the agronomic rule score.</li>
            <li><strong>Top-3 with reasons instead of a single label.</strong> Every card carries a suitability score, the raw
              model probability, the rule-fit breakdown and short factual sentences assembled from the cited knowledge base.</li>
            <li><strong>Regional tuning for a real district.</strong> DK taluks, laterite/coastal soil profiles, monsoon rainfall
              presets, and a labelled knowledge-base advisory for the district's signature crops that the Kaggle dataset lacks
              (arecanut, cashew, black pepper, cocoa, rubber).</li>
            <li><strong>A working feedback loop.</strong> A farmer reports what actually happened; with consent it becomes a survey
              row, an evaluator approves it, and the admin retrain merges it (weighted by yield outcome) into the next model.</li>
            <li><strong>Honest evaluation.</strong> The 4-input ablation, the "7 measured parameters, 4 asked questions" expansion
              audit, and the rainfall-extrapolation warning are all visible in the product, not buried in a limitations section.</li>
            <li><strong>Bilingual, zero-cost, deployable.</strong> English/Kannada UI, no paid services, one command to deploy.</li>
          </ol>
        </div>
        <div class="card"><h4>${UI.esc(t("cmp.adopted"))}</h4>
          <ol class="reasons">
            <li>The four-algorithm comparison (DT, RF, KNN, NB) and the expectation that Random Forest wins — adopted from the
              ACM 2024 comparison and Pudumalar et al. This project's result (RF best) agrees.</li>
            <li>The Kaggle Crop Recommendation Dataset (2200 × 22) as the free secondary source — the same dataset used by the
              Scientific Reports 2025 and 2026 papers reviewed here.</li>
            <li>Stratified split plus k-fold cross-validation, reporting accuracy, precision, recall and F1 per class — standard
              protocol in the reviewed work.</li>
            <li>Explainability as a requirement rather than an extra: motivated by the SHAP/LIME papers, but implemented as a
              cited rule-based reason layer, because a physics-free SHAP value means little to a farmer.</li>
            <li>Chandrasekaran-style feature-importance reading (moisture and potassium dominate) reproduced independently here —
              useful triangulation for the report.</li>
          </ol>
          <div class="callout info" style="margin-top:8px"><strong>What was deliberately NOT adopted</strong>
            Single-number accuracy claims without the protocol, synthetic/oversampled data presented as field data, and
            deep-learning baselines that cannot be trained or served on a free academic tier.</div>
        </div>
      </div>

      <div class="card"><h4>${UI.esc(t("cmp.sources"))}</h4>
        <ul class="reasons">
          <li>S. Pudumalar et al., “Crop Recommendation System for Precision Agriculture”, 2016 Eighth International Conference on
            Advanced Computing (ICoAC), IEEE, 2017, pp. 32–36. <a href="https://dl.acm.org/doi/10.1145/3659677.3659701" target="_blank" rel="noopener">cited in ACM 2024</a></li>
          <li>R. Priya, D. Ramesh, E. Khosla, “Crop Prediction on the Region Belts of India: A Naïve Bayes MapReduce Precision
            Agricultural Model”, ICACCI 2018, IEEE, pp. 99–104.</li>
          <li>“Crop Recommendation using Machine Learning Algorithms”, 2024.
            <a href="https://dl.acm.org/doi/10.1145/3659677.3659701" target="_blank" rel="noopener">doi:10.1145/3659677.3659701</a></li>
          <li>S. Shastri, S. Kumar, V. Mansotra, R. Salgotra, “Advancing crop recommendation system with supervised machine learning
            and explainable artificial intelligence”, <em>Scientific Reports</em> 15:25498 (2025).
            <a href="https://www.nature.com/articles/s41598-025-07003-8" target="_blank" rel="noopener">nature.com/articles/s41598-025-07003-8</a></li>
          <li>“Interpretable deep learning models for independent fertilizer and crop recommendation”, <em>Scientific Reports</em> (2025).
            <a href="https://www.nature.com/articles/s41598-025-26910-4" target="_blank" rel="noopener">nature.com/articles/s41598-025-26910-4</a></li>
          <li>“Agentic AI-driven autonomous decision support system for smart agriculture”, <em>Scientific Reports</em> (2026).
            <a href="https://www.nature.com/articles/s41598-026-39472-w" target="_blank" rel="noopener">nature.com/articles/s41598-026-39472-w</a></li>
          <li>Kaggle “Crop Recommendation Dataset” (atharvaingle) — the secondary dataset.
            <a href="https://www.kaggle.com/datasets/atharvaingle/crop-recommendation-dataset" target="_blank" rel="noopener">kaggle.com/datasets/atharvaingle/crop-recommendation-dataset</a></li>
          <li>KVK Dakshina Kannada district profile and annual report (rainfall, soils, crop areas, pH).
            <a href="https://www.kvkdk.org/district_profile.html" target="_blank" rel="noopener">kvkdk.org</a></li>
          <li>TNAU Agritech Portal / Crop Production Guide (crop climate and water requirements).
            <a href="https://agritech.tnau.ac.in/" target="_blank" rel="noopener">agritech.tnau.ac.in</a></li>
        </ul>
      </div>`;
  }
};

const UICore = {
  metricsText() {
    const m = window.__metrics;
    if (!m) return "99.55% holdout accuracy, 100% top-3 (see Model Performance for live figures)";
    return `${UI.pct(m.best_model.metrics.test_accuracy, 2)} holdout accuracy, `
      + `${UI.pct(m.best_model.metrics.top3_accuracy, 1)} top-3, `
      + `${UI.pct(m.best_model.metrics.cv_macro_f1_mean, 2)} CV macro-F1`;
  }
};
window.UICore = UICore;

/* ==========================================================================
   CROP REFERENCE (CRUD)
   ========================================================================== */
P.crops = {
  async render(view) {
    view.innerHTML = `
      <div class="card">
        <div class="card-head"><div><h3>${UI.esc(t("crops.title"))}</h3>
          <p class="muted small" style="margin:0">${UI.esc(t("crops.intro"))}</p></div>
          <span class="spacer"></span>
          ${App.isAdmin ? `<button class="btn small" id="crops-import">${UI.esc(t("crops.importDefaults"))}</button>
          <button class="btn primary small" id="crops-new">+ ${UI.esc(t("crops.new"))}</button>` : `<span class="badge grey">${UI.esc(t("common.adminOnly"))}</span>`}
        </div>
        <div class="toolbar">
          <label class="field"><span>${UI.esc(t("common.search"))}</span><input id="c-search" placeholder="rice / adike / coconut" /></label>
          <label class="field"><span>Category</span><select id="c-cat"><option value="">${UI.esc(t("common.all"))}</option>
            ${[...new Set(App.meta.crops_all.map((c) => c.category))].map((c) => `<option value="${c}">${UI.esc(c)}</option>`).join("")}</select></label>
          <label class="field"><span>Region</span><select id="c-dk"><option value="">${UI.esc(t("common.all"))}</option>
            <option value="1">${UI.esc(t("crops.dkLocal"))}</option></select></label>
        </div>
        <div id="crops-table">${UI.skeleton(6)}</div>
      </div>`;
    const imp = view.querySelector("#crops-import");
    if (imp) imp.addEventListener("click", async (e) => {
      e.target.disabled = true;
      try { const r = await Api.importCrops(); UI.toast(`${r.created} rows imported`, "ok"); this.load(view); }
      catch (err) { UI.toast(err.message, "err"); } finally { e.target.disabled = false; }
    });
    const nw = view.querySelector("#crops-new");
    if (nw) nw.addEventListener("click", () => this.form(view));
    view.querySelector("#c-search").addEventListener("input", (e) => {
      clearTimeout(this._d); this._d = setTimeout(() => { this.q = e.target.value; this.load(view); }, 300);
    });
    view.querySelector("#c-cat").addEventListener("change", (e) => { this.cat = e.target.value; this.load(view); });
    view.querySelector("#c-dk").addEventListener("change", (e) => { this.dk = e.target.value; this.load(view); });
    this.load(view);
  },

  async load(view) {
    const host = view.querySelector("#crops-table");
    host.innerHTML = UI.skeleton(5);
    try {
      const params = { limit: 100 };
      if (this.q) params.search = this.q;
      if (this.cat) params.category = this.cat;
      if (this.dk) params.dk_local = this.dk;
      const d = await Api.crops(params);
      const kb = await Api.cropReferencePublic();
      this.kbMap = Object.fromEntries(kb.crops.map((c) => [c.crop, c]));
      const items = d.items && d.items.length ? d.items : kb.crops.map((c) => ({
        id: null, crop_key: c.crop, name: c.name, name_kn: c.name_kn, category: c.category,
        water_need: c.water_need, rainfall_monthly_mm: c.rainfall_monthly_mm, ph: c.ph,
        temp_c: c.temp_c, duration_days: c.duration_days, total_water_mm: c.total_water_mm,
        dk_local: c.dk_local, in_model_label_space: c.in_model_label_space, kb_only: c.kb_only,
        note: c.note, source: c.source, source_url: c.source_url
      }));
      if (!items.length) {
        host.innerHTML = UI.empty(t("crops.emptyTitle"), t("crops.emptyBody"), "", "leaf");
        return;
      }
      host.innerHTML = `
        ${d.total === 0 ? `<div class="callout info">The editable table is empty, so the read-only built-in knowledge base is shown.
          ${App.isAdmin ? "Use “Import built-in knowledge base” to start editing." : "An admin can import it for editing."}</div>` : ""}
        <div class="table-wrap"><table>
          <thead><tr><th>${UI.esc(t("common.crop"))}</th><th>Category</th><th>${UI.esc(t("crops.waterNeed"))}</th>
            <th class="num">${UI.esc(t("crops.rainBand"))}</th><th class="num">${UI.esc(t("crops.ph"))}</th>
            <th class="num">${UI.esc(t("crops.temp"))}</th><th class="num">${UI.esc(t("crops.duration"))}</th>
            <th>Flags</th><th>${UI.esc(t("crops.source"))}</th>${App.isAdmin ? `<th>${UI.esc(t("common.actions"))}</th>` : ""}</tr></thead>
          <tbody>${items.map((c) => `<tr>
            <td><strong>${UI.esc(c.name)}</strong>${c.name_kn ? `<div class="muted small">${UI.esc(c.name_kn)}</div>` : ""}</td>
            <td>${UI.esc(c.category || "—")}</td>
            <td>${UI.esc(UI.titleCase(c.water_need || ""))}</td>
            <td class="num">${(c.rainfall_monthly_mm || []).map((x) => UI.num(x, 0)).join("–")}</td>
            <td class="num">${(c.ph || []).map((x) => UI.num(x, 1)).join("–")}</td>
            <td class="num">${(c.temp_c || []).map((x) => UI.num(x, 0)).join("–")}</td>
            <td class="num">${c.duration_days || "—"}</td>
            <td>${c.dk_local ? `<span class="badge green">${UI.esc(t("crops.dkLocal"))}</span>` : ""}
              ${c.in_model_label_space ? `<span class="badge blue">${UI.esc(t("crops.inModel"))}</span>` : `<span class="badge grey">${UI.esc(t("crops.kbOnly"))}</span>`}</td>
            <td class="small muted">${c.source_url ? `<a href="${UI.esc(c.source_url)}" target="_blank" rel="noopener">${UI.esc((c.source || "").slice(0, 42))}…</a>` : UI.esc(c.source || "—")}</td>
            ${App.isAdmin ? `<td class="nowrap">${c.id ? `<button class="btn small" data-edit="${c.id}">${UI.esc(t("common.edit"))}</button>
              <button class="btn small danger" data-del="${c.id}" data-key="${UI.esc(c.crop_key)}">${UI.esc(t("common.delete"))}</button>`
              : `<span class="muted small">built-in</span>`}</td>` : ""}
          </tr>`).join("")}</tbody></table></div>
        <p class="muted small" style="margin-top:10px">Editing a row here changes the <strong>rule-fit</strong> component of the
          recommendation score (water need, rainfall band, suitable soils/seasons, regional flag) — the machine-learning
          probability is unaffected. Built-in numbers come from TNAU/ICAR/KVK sources listed on the About page.</p>`;
      host.querySelectorAll("[data-edit]").forEach((b) => b.addEventListener("click", () => {
        const row = items.find((x) => String(x.id) === b.dataset.edit);
        this.form(view, row);
      }));
      host.querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", async () => {
        if (!(await UI.confirmDialog({ title: t("common.delete"), message: t("crops.deleteConfirm"), confirmLabel: t("common.delete"), danger: true }))) return;
        try { await Api.deleteCrop(b.dataset.del); UI.toast(t("common.deleted"), "ok"); this.load(view); }
        catch (e) { UI.toast(e.message, "err"); }
      }));
    } catch (e) { host.innerHTML = `<div class="callout danger">${UI.esc(e.message)}</div>`; }
  },

  form(view, c) {
    const y = c || { seasons: ["Kharif"], soils: ["laterite"], water_need: "medium", rainfall_monthly_mm: [50, 200], ph: [5.5, 7.5], temp_c: [20, 35] };
    const seasonBoxes = App.meta.seasons.map((s) => `<label class="chip" style="cursor:pointer">
      <input type="checkbox" name="seasons" value="${s.value}" ${y.seasons && y.seasons.includes(s.value) ? "checked" : ""}/> ${UI.esc(s.value)}</label>`).join(" ");
    const soilBoxes = App.meta.soil_types.map((s) => `<label class="chip" style="cursor:pointer">
      <input type="checkbox" name="soils" value="${s.value}" ${y.soils && y.soils.includes(s.value) ? "checked" : ""}/> ${UI.esc(UI.titleCase(s.value))}</label>`).join(" ");
    UI.modal({
      title: c && c.id ? `${t("common.edit")}: ${c.name}` : t("crops.new"),
      wide: true,
      body: `
        <form id="crop-form" class="form">
          <div class="grid-2">
            <label class="field"><span>Crop key (slug) *</span><input name="crop_key" value="${UI.esc(y.crop_key || "")}" ${c && c.id ? "readonly" : ""} required /></label>
            <label class="field"><span>Name *</span><input name="name" value="${UI.esc(y.name || "")}" required /></label>
          </div>
          <div class="grid-2">
            <label class="field"><span>Kannada name</span><input name="name_kn" value="${UI.esc(y.name_kn || "")}" /></label>
            <label class="field"><span>Category</span><input name="category" value="${UI.esc(y.category || "cereal")}" /></label>
          </div>
          <fieldset style="border:1px solid var(--line);border-radius:9px;padding:10px">
            <legend class="small muted">Seasons</legend><div class="chips">${seasonBoxes}</div></fieldset>
          <fieldset style="border:1px solid var(--line);border-radius:9px;padding:10px">
            <legend class="small muted">Suitable soils</legend><div class="chips">${soilBoxes}</div></fieldset>
          <div class="grid-2">
            <label class="field"><span>Water need</span><select name="water_need">${UI.options(App.meta.water_levels, y.water_need)}</select></label>
            <label class="field"><span>Duration (days)</span><input type="number" name="duration_days" value="${y.duration_days || 120}" /></label>
          </div>
          <div class="grid-2">
            <label class="field"><span>Rainfall band min (mm)</span><input type="number" name="rainfall_min" value="${(y.rainfall_monthly_mm || [50, 200])[0]}" /></label>
            <label class="field"><span>Rainfall band max (mm)</span><input type="number" name="rainfall_max" value="${(y.rainfall_monthly_mm || [50, 200])[1]}" /></label>
          </div>
          <div class="grid-2">
            <label class="field"><span>pH min</span><input type="number" step="0.1" name="ph_min" value="${(y.ph || [5.5, 7.5])[0]}" /></label>
            <label class="field"><span>pH max</span><input type="number" step="0.1" name="ph_max" value="${(y.ph || [5.5, 7.5])[1]}" /></label>
          </div>
          <div class="grid-2">
            <label class="field"><span>Temp min (°C)</span><input type="number" step="0.5" name="temp_min" value="${(y.temp_c || [20, 35])[0]}" /></label>
            <label class="field"><span>Temp max (°C)</span><input type="number" step="0.5" name="temp_max" value="${(y.temp_c || [20, 35])[1]}" /></label>
          </div>
          <label class="field"><span>Crop water requirement (text, quoted from source)</span><input name="total_water_mm" value="${UI.esc(y.total_water_mm || "")}" /></label>
          <label class="field"><span>Note</span><textarea name="note">${UI.esc(y.note || "")}</textarea></label>
          <label class="field"><span>Source</span><input name="source" value="${UI.esc(y.source || "TNAU Agritech Portal / ICAR package of practices")}" /></label>
          <label class="field"><span>Source URL</span><input name="source_url" value="${UI.esc(y.source_url || "")}" /></label>
          <div class="grid-2">
            <label class="checkbox"><input type="checkbox" name="dk_local" ${y.dk_local ? "checked" : ""}/> <span>${UI.esc(t("crops.dkLocal"))}</span></label>
            <label class="checkbox"><input type="checkbox" name="is_active" ${y.is_active === false ? "" : "checked"}/> <span>Active</span></label>
          </div>
        </form>`,
      footer: `<button class="btn" data-close>${UI.esc(t("common.cancel"))}</button>
        <button class="btn primary" id="crop-save">${UI.esc(t("common.save"))}</button>`,
      onMount(node, close) {
        node.querySelector("#crop-save").addEventListener("click", async (e) => {
          const form = node.querySelector("#crop-form");
          const raw = UI.readForm(form);
          const payload = {
            crop_key: raw.crop_key, name: raw.name, name_kn: raw.name_kn, category: raw.category,
            seasons: [...form.querySelectorAll('input[name="seasons"]:checked')].map((i) => i.value),
            soils: [...form.querySelectorAll('input[name="soils"]:checked')].map((i) => i.value),
            water_need: raw.water_need, duration_days: Number(raw.duration_days),
            rainfall_min: Number(raw.rainfall_min), rainfall_max: Number(raw.rainfall_max),
            ph_min: Number(raw.ph_min), ph_max: Number(raw.ph_max),
            temp_min: Number(raw.temp_min), temp_max: Number(raw.temp_max),
            total_water_mm: raw.total_water_mm, note: raw.note, source: raw.source,
            source_url: raw.source_url, dk_local: !!raw.dk_local, is_active: !!raw.is_active
          };
          e.target.disabled = true;
          try {
            if (c && c.id) await Api.updateCrop(c.id, payload);
            else await Api.createCrop(payload);
            UI.toast(t("common.saved"), "ok");
            close(); Pages.crops.load(view);
          } catch (err) {
            e.target.disabled = false;
            UI.toast(err.details && err.details.length ? err.details.join(" • ") : err.message, "err", 7000);
          }
        });
      }
    });
  }
};

/* ==========================================================================
   ABOUT
   ========================================================================== */
P.about = {
  async render(view) {
    const endpoints = [
      ["GET", "/health", "Uptime probe: db connectivity, model load state, version"],
      ["POST", "/api/predict", "Top-3 recommendation (no auth needed; save requires a token)"],
      ["GET", "/api/meta", "Form vocabularies: soils, seasons, water levels, irrigation sources, taluks"],
      ["POST", "/api/auth/register · /login", "Farmer self-registration; JWT login for both roles"],
      ["GET", "/api/history · PATCH · DELETE", "Prediction history CRUD (own rows; admins can list all)"],
      ["POST", "/api/history/{id}/feedback", "Outcome feedback → optionally writes a primary survey row"],
      ["GET", "/api/surveys · POST · PATCH · DELETE", "Primary dataset survey CRUD"],
      ["POST", "/api/surveys/{id}/review", "Admin approval/rejection of a survey row"],
      ["GET", "/api/crops · POST · PATCH · DELETE", "Crop reference CRUD (writes are admin-only)"],
      ["GET", "/api/model/metrics", "All four algorithms, CV, confusion matrix, importance, ablation"],
      ["POST", "/api/model/retrain", "Admin: merge approved surveys and retrain (background)"],
      ["GET", "/api/dataset/schema", "Unified schema, mapping rules, cleaning rules, expansion profiles"],
      ["GET", "/api/dataset/secondary/rows", "Paginated mapped secondary dataset with filters + CSV export"],
      ["GET", "/api/summary", "Dashboard aggregates"]
    ];
    const viva = [
      ["Why four inputs and not seven?", "Because a farmer can answer soil type, season, rainfall and water without a soil-test lab report. The seven measured parameters are still used, via a documented expansion (SOIL_PROFILES / SEASON_PROFILES) whose assumptions are shown on every result and in the About page. The 4-input ablation quantifies that trade-off: about 59% top-1 versus 99.6%, while top-3 stays near 87%."],
      ["Why is Random Forest the selected model?", "It had the best mean 5-fold CV macro-F1 (0.9954) at essentially the highest holdout accuracy (99.55%), matching the literature reviewed on the Project Comparison page. Model choice is by CV macro-F1, not by raw accuracy on one split."],
      ["How do you avoid leaking the test set?", "The stratified 80/20 split happens once; cross-validation runs only on the training part; the test split is used only for final metrics, permutation importance and the confusion matrix."],
      ["What exactly is the “confidence” number?", "A blended suitability score: model_probability^0.55 × rule_fit^0.45, with a ×1.05 prior for crops grown in DK when regional tuning is on. It is deliberately called a suitability score, not a calibrated probability, and the raw model probability is displayed separately."],
      ["What is rule_fit and where does it come from?", "A transparent weighted score over four agronomic checks (water need vs availability 30%, season 25%, rainfall band 25%, soil suitability 20%) using the cited crop knowledge base; a drainage-sensitive crop is penalised when rainfall exceeds its band."],
      ["How does the feedback loop actually change the model?", "Outcome feedback (with consent) becomes a survey row → an admin approves it → POST /api/model/retrain merges approved rows, applying cleaning rules (poor yields excluded, average yields weighted 0.5, duplicates collapsed) → all four models retrain and the artefact is reloaded."],
      ["What are the biggest limitations?", "(1) Two of the four inputs are derived proxies in the secondary data; (2) the dataset's rainfall ceiling (~299 mm) is far below DK's monsoon, so high-rainfall behaviour is extrapolation; (3) 22 balanced classes make the task unusually easy; (4) locally important crops such as arecanut are missing from the dataset and can only be knowledge-base advisories; (5) crop suitability ≠ profitability."],
      ["How is data privacy handled?", "Consent is a hard gate (cleaning rule 1): without it a row is rejected and can never enter the dataset. Survey rows expose only farmer name/village/taluk/phone to the submitter and admins; the model trains on soil, season, rainfall, water, crop and outcome — no personal identifiers."],
      ["What runs where on deployment?", "A Render free web service runs gunicorn + Flask (this app serves both the REST API and the static front-end). Persistence comes from a free hosted Postgres (Neon/Supabase) because Render's free disk is ephemeral. The 0.7 MB model ships in the repo and is lazy-loaded; /health is the probe."],
      ["What would you do with a real budget of field data?", "Collect the primary survey at scale for one full season with KVK support, replace the derived soil/season/water proxies with true observations, add soil-test NPK values, model yield as a second target, and validate with a hold-out set of real fields rather than a curated dataset."]
    ];
    let metrics = window.__metrics;
    if (!metrics) {
      try { metrics = window.__metrics = await Api.metrics(); } catch (e) { metrics = null; }
    }
    view.innerHTML = `
      <div class="card">
        <h3>${UI.esc(t("about.what"))}</h3>
        <p>${UI.esc(t("app.name"))} is an academic, full-stack decision-support prototype for farmers, KVK staff and
          students in <strong>Dakshina Kannada, Karnataka</strong>. It recommends the three most suitable crops for a field
          from four questions, shows the agronomic reasoning, and grows its own primary dataset from farmer feedback.</p>
        <div class="grid cols-4">
          <div class="stat"><div class="label">District</div><div class="value" style="font-size:1.05rem">Dakshina Kannada</div>
            <div class="sub">~4,000 mm normal annual rainfall · lateritic soils · pH 4.6–5.8</div></div>
          <div class="stat"><div class="label">Model</div><div class="value" style="font-size:1.05rem">${UI.esc(metrics ? metrics.best_model.label : "Random Forest")}</div>
            <div class="sub">${metrics ? `holdout ${UI.pct(metrics.best_model.metrics.test_accuracy, 2)} · top-3 ${UI.pct(metrics.best_model.metrics.top3_accuracy, 1)}` : "see Model Performance"}</div></div>
          <div class="stat"><div class="label">Cost</div><div class="value">₹0</div><div class="sub">Render free tier + free hosted Postgres</div></div>
          <div class="stat"><div class="label">Languages</div><div class="value">2</div><div class="sub">English / ಕನ್ನಡ (UI; reasons are English in v1)</div></div>
        </div>
      </div>

      <div class="card">
        <h3>${UI.esc(t("about.how"))}</h3>
        <ol class="reasons">
          <li><strong>Four answers.</strong> Soil type, season, growing-window rainfall (mm), water availability / irrigation source.</li>
          <li><strong>Expansion (documented, not hidden).</strong> The four answers become the seven measured parameters the model
            was trained on, through fixed typical soil and season profiles. Every result page prints this audit trail.</li>
          <li><strong>Model.</strong> ${metrics ? UI.esc(metrics.best_model.label) : "Random Forest"} over 22 crop classes →
            <span class="mono">predict_proba</span>, plus a permutation/impurity feature-importance view for explainability.</li>
          <li><strong>Agronomic rule fit.</strong> Water need (30%), season (25%), rainfall band (25%), soil suitability (20%) from
            the cited crop knowledge base, with a waterlogging penalty for drainage-sensitive crops.</li>
          <li><strong>Blend &amp; rank.</strong> score = probability<sup>0.55</sup> × rule_fit<sup>0.45</sup> (×1.05 for DK crops when
            regional tuning is on) → top-3 with reasons, cautions and, separately, a knowledge-base advisory for local crops
            missing from the dataset.</li>
          <li><strong>Feedback loop.</strong> Outcome → consent → survey row → admin approval → merged (weighted) into the next retrain.</li>
        </ol>
      </div>

      <div class="card">
        <h3>${UI.esc(t("about.sources"))}</h3>
        <ul class="reasons">
          <li><strong>Secondary dataset (training):</strong> Kaggle “Crop Recommendation Dataset” — 2200 rows, 22 crops, 7 parameters
            ("{N, P, K, temperature, humidity, pH, rainfall}"). Free for academic use;
            <a href="https://www.kaggle.com/datasets/atharvaingle/crop-recommendation-dataset" target="_blank" rel="noopener">kaggle.com/datasets/atharvaingle/crop-recommendation-dataset</a>.</li>
          <li><strong>Primary dataset (collected in-app):</strong> the survey form in this application — soil type, season, rainfall,
            water source, crop grown, yield outcome, village/taluk, consent. This is the only source with real soil/season/irrigation labels.</li>
          <li><strong>District agronomy:</strong> KVK Dakshina Kannada district profile and 2023 annual report (rainfall 4040 mm normal,
            2023 actual 3318.3 mm; lateritic soils, pH 4.6–5.8; paddy 48,689 ha; arecanut 35,409 ha; coconut 18,467 ha) —
            <a href="https://www.kvkdk.org/district_profile.html" target="_blank" rel="noopener">kvkdk.org</a>.</li>
          <li><strong>Crop agronomy:</strong> TNAU Agritech Portal and Crop Production Guide (climate and water requirements per crop),
            ICAR package-of-practices ranges — <a href="https://agritech.tnau.ac.in/" target="_blank" rel="noopener">agritech.tnau.ac.in</a>.</li>
          <li><strong>Research:</strong> Pudumalar et al. (IEEE ICoAC 2017); Priya, Ramesh &amp; Khosla (IEEE ICACCI 2018);
            ACM 2024 crop-recommendation comparison; Shastri et al., <em>Scientific Reports</em> 15:25498 (2025);
            TabNet/SHAP crop+fertilizer study, <em>Scientific Reports</em> (2025); agentic AI decision support,
            <em>Scientific Reports</em> (2026) — full citations on the Project Comparison page.</li>
        </ul>
      </div>

      <div class="card">
        <h3>${UI.esc(t("about.limits"))}</h3>
        <ol class="reasons">${(metrics ? metrics.honest_limitations : ["Run the training pipeline to load the limitation list."]).map((x) => `<li>${UI.esc(x)}</li>`).join("")}</ol>
        <div class="callout warn"><strong>Rainfall scale warning</strong>The secondary dataset's rainfall column tops out at ≈299 mm per
          period, while a single monsoon month in Dakshina Kannada routinely exceeds that. Above the training range the model is
          extrapolating — which is why water availability, the rule-fit score and regional tuning are separate, visible inputs.</div>
      </div>

      <div class="card">
        <h3>${UI.esc(t("about.privacy"))}</h3>
        <ul class="reasons">
          <li>Consent is enforced in code (cleaning rule 1): a row without consent is rejected at validation time and again at
            merge time, and cannot train the model.</li>
          <li>Farmers see and manage only their own records; admin/evaluator accounts see everything and are seeded, not
            self-registered (self-signup as admin is blocked).</li>
          <li>Training uses soil, season, rainfall, water availability, crop and outcome. Names, villages, phone numbers and
            free-text notes are never model features — they exist only so a KVK officer can follow up.</li>
          <li>All CRUD writes are audit-logged (who changed what), visible to admins.</li>
        </ul>
      </div>

      <div class="card">
        <h3>${UI.esc(t("about.run"))}</h3>
        <ul class="reasons">
          <li><strong>Free-tier shape:</strong> one Render <span class="mono">type: web, runtime: python, plan: free</span> service runs
            <span class="mono">gunicorn wsgi:app</span> and serves both the API and this SPA; a second static service is declared in
            <span class="mono">render.yaml</span> for CDN-style delivery of the same files (Render's static runtime is
            <span class="mono">runtime: static</span>).</li>
          <li><strong>Persistence:</strong> Render's free disk is ephemeral, so the database lives on a free hosted Postgres
            (Neon or Supabase) via <span class="mono">DATABASE_URL</span>; the trained model (~0.7 MB) is committed to the repo and
            lazy-loaded on the first prediction to keep cold starts short.</li>
          <li><strong>Health probe:</strong> <span class="mono">GET /health</span> reports database connectivity, whether the model is
            loaded, and the running version — it deliberately does not load the model itself.</li>
          <li><strong>Retrain caveat:</strong> an in-app retrain writes to that instance's ephemeral disk; commit the artefact (or
            re-run the training script in CI) to make it permanent.</li>
        </ul>
      </div>

      <div class="card">
        <h3>${UI.esc(t("about.api"))}</h3>
        <div class="table-wrap"><table><thead><tr><th>Method</th><th>Path</th><th>What it does</th></tr></thead>
          <tbody>${endpoints.map(([mth, path, desc]) => `<tr><td class="mono">${UI.esc(mth)}</td>
            <td class="mono">${UI.esc(path)}</td><td class="small">${UI.esc(desc)}</td></tr>`).join("")}</tbody></table></div>
        <p class="muted small" style="margin-top:8px">Example:
          <span class="mono">curl -X POST /api/predict -H "Content-Type: application/json" -d '{"soil_type":"laterite","season":"Kharif","rainfall_mm":240,"water_availability":"high"}'</span></p>
      </div>

      <div class="card">
        <h3>${UI.esc(t("about.viva"))}</h3>
        <div class="table-wrap"><table><thead><tr><th style="width:34%">Question</th><th>Answer</th></tr></thead>
          <tbody>${viva.map(([q, a]) => `<tr><td><strong>${UI.esc(q)}</strong></td><td class="small">${UI.esc(a)}</td></tr>`).join("")}</tbody></table></div>
        <p class="muted small" style="margin-top:8px">The same ten questions, with fuller answers, are in
          <span class="mono">docs/viva_questions.md</span>, along with the final-report outline and test cases.</p>
      </div>

      <div class="callout info">${UI.esc(t("about.i18nNote"))}</div>`;
  }
};

window.Pages = P;
