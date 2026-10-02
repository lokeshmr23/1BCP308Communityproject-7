# Final report outline

A ready-to-fill structure for the academic report. Every number below is marked with **where to get
it**, so nothing has to be invented and every claim can be traced back to a file the examiner can
open. Page targets assume a 45–60 page report.

---

## Front matter

| Item | Source |
|---|---|
| Title page, certificate, declaration, acknowledgement | your institution's format |
| Abstract (250 words) | solved problem, four-input design, 99.55 % holdout on the secondary data, **~59 % honest 4-input ablation**, top-3 ~87 %, feedback loop, free deployment |
| Table of contents, list of figures, list of tables, abbreviations | — |

---

## Chapter 1 — Introduction (4–6 pages)

1.1 Background — agriculture in Dakshina Kannada: 4770 km², 27 % forest, ~1.31 lakh ha net sown,
annual rainfall ≈4000 mm (KVK DK; 2023 actual 3318 mm), lateritic and coastal-sandy soils.
**Source:** KVK DK district profile, cited in `docs/dataset_schema.md` §4 and the About page.

1.2 Problem statement — crop choice today relies on memory and word of mouth; soil-test reports are
scarce; existing recommendation apps assume the farmer knows N/P/K/pH and ignore season and water
availability.

1.3 Objectives (numbered, testable) —
(1) a four-question recommendation interface with top-3 + reasons;
(2) train and compare four classical algorithms on a free secondary dataset, honestly evaluated;
(3) build a primary survey dataset with cleaning rules, merge it, and close a feedback loop;
(4) compare with 3–5 published systems and state what is new;
(5) deploy the whole stack at zero cost with a documented architecture.

1.4 Scope and limitations — coastal Karnataka focus; secondary dataset is balanced/curated; three of
the four inputs are expanded, not measured.

1.5 Organisation of the report.

---

## Chapter 2 — Literature survey (6–8 pages)

**Table 2.1 — review matrix** (columns: study, inputs, dataset & size, algorithm, reported accuracy,
protocol stated?, explainability, regional support, deployment):

| Study | Inputs | Dataset | Algorithm | Reported accuracy | Notes / caveats |
|---|---|---|---|---|---|
| Pudumalar et al., ICACCI 2016/17 | N,P,K,temp,humidity,rainfall | district soil data | ensemble majority voting (Random Tree, CHAID, KNN, NB) | 88 % | protocol partially stated |
| Priya, Ramesh, Khosla, ICACCI 2018 | N,P,K,pH,rainfall | India regional belts | Naïve Bayes on MapReduce | unverified (paywalled) | map-reduce scaling angle |
| ACM 2024 comparison (doi 10.1145/3659677.3659701) | N,P,K,temp,humidity,pH,rainfall | Kaggle-type set | DT, RF, SVM, KNN, NB, LR, LightGBM | RF/NB/LightGBM ranked top | multiple algorithms, same feature set |
| Shastri et al., *Scientific Reports* 15:25498 (2025) | same 7 parameters | Kaggle 2200 × 22 | gradient boosting + XAI (SHAP/LIME) | 99.27 % claim; RF 98.86 % | 70:30 split; lit-review figures 87.62–99.59 % |
| *Sci. Rep.* (2025), TabNet | same 7 | benchmark set | TabNet vs RF | 96.21 % vs 85.34 % | deep model needs more data to justify itself |
| *Sci. Rep.* (2026), agentic AI | farm/market signals | multi-source | RF + agents | 92.4 % | SHAP: P > K > humidity > rainfall |
| **This project** | **4 collected inputs → 7 expanded** | **2197 secondary + primary survey** | **DT, RF, KNN, NB** | **99.55 % (7 params) / ~59 % (4 inputs)** | **top-3 ~87 %; region-tuned; feedback loop; free deploy** |

2.1–2.6 one subsection per study: what it does, what it does well, what it does not address.
2.7 Research gap → the seven innovations listed on the Project Comparison page.
**Source of every row:** `frontend/js/pages-info.js` → `Pages.comparison`, and §14 of the README.

---

## Chapter 3 — System analysis and design (8–10 pages)

3.1 Requirement analysis — functional requirements table (FR-01…FR-20) from the feature list;
non-functional (free hosting, < 1 s API latency, lazy model load, mobile width, bilingual,
consent-aware).

3.2 **Architecture diagram** — reuse the Mermaid block in README §3 (or its rendered PNG).
3.3 **Sequence diagram** for one recommendation — README §3 second diagram.
3.4 **ER diagram** — `users 1—* predictions`, `users 1—* survey_entries`, `crop_references`
(referenced by key), `audit_log`; draw from `backend/app/models.py`.
3.5 Module design — expansion layer, knowledge base, registry/blend, cleaning, API blueprints,
SPA pages.
3.6 **Use-case diagram** — farmer (recommend, history, feedback, survey), admin (review, crop CRUD,
retrain, metrics, all user data).
3.7 Design decisions and their justifications:
(a) four inputs (farmer-answerable) — defended by the ablation;
(b) geometric blend `prob^0.55 × rule^0.45` — an additive blend let papaya outrank rice in a monsoon
profile, so the geometric form is deliberate;
(c) managed-fertility soil profiles;
(d) human-in-the-loop feedback;
(e) lazy model + committed 714 KB artefact for free-tier cold starts.

---

## Chapter 4 — Implementation (10–12 pages)

4.1 Technology stack and why (Flask + SQLAlchemy, scikit-learn, vanilla-JS SPA, Postgres/SQLite).
4.2 Backend structure — blueprint list, error contract, `/health`.
4.3 The mapping layer — the soil/season/water derivation rules with their basis, and the honesty note.
4.4 The expansion layer — the 4→7 table (soil → pH/N/P/K, season → temp/RH, water → index), clamp.
4.5 The knowledge base — 33 crops, `dk_local` flags, waterlogging-sensitive set, rule weights
(0.30/0.25/0.25/0.20), reason generation, advisories.
4.6 Training pipeline — stratified 80/20, 5-fold CV, four algorithms, sample weights, artefact
compression, metrics JSON schema.
4.7 Serving path — lazy registry, thread lock, blend, bands, low-confidence flag, per-rec keys.
4.8 Primary data pipeline — cleaning rules 1–10 with code references, sample weighting, merge.
4.9 Front-end — routes, i18n (EN/ಕನ್ನಡ), empty/loading states, optimistic updates, charts hand-rolled
as SVG/CSS (no CDN, so the app works offline and on the free tier).
4.10 Seed data — 8 users, 16 predictions, 20 surveys, 37 crops, audit rows.

---

## Chapter 5 — Results and discussion (10–12 pages)

**Table 5.1 — model comparison** (copy verbatim from `backend/data/models/metrics.json`):

| Algorithm | Accuracy | Precision | Recall | F1 | CV F1 | Top-3 |
|---|---|---|---|---|---|---|
| Decision Tree | 98.86 % | 98.92 % | 98.86 % | 98.85 % | 98.05 ± 0.82 | 99.09 % |
| **Random Forest ⭐** | **99.55 %** | **99.57 %** | **99.55 %** | **99.55 %** | **99.54 ± 0.14** | **100 %** |
| KNN (k=7) | 97.05 % | 97.21 % | 97.05 % | 97.01 % | 97.07 ± 1.25 | 100 % |
| Gaussian NB | 99.55 % | 99.59 % | 99.55 % | 99.54 % | 99.43 ± 0.26 | 100 % |

**Figure 5.1** confusion matrix (22×22) — screenshot from the Model Performance page.
**Figure 5.2** feature importance — Gini (rainfall 22.7 %, humidity 21.4 %, K 18.1 % …) **and**
permutation (humidity 0.279, N 0.238, rainfall 0.198 …) side by side, with a paragraph on why they
differ for correlated features.
**Table 5.3 — the honest core of the report:** the 4-input ablation (best ≈ 59 % accuracy, ~87 %
top-3) with the interpretation that the interface's convenience costs accuracy and that top-3 +
explanations are the mitigation.
**Table 5.4 — sanity benchmark:** 20 DK field profiles → 70 % top-1 / 85 % top-3 agreement with
district cropping expectations (`scripts/evaluate_predictions.py`), explicitly *not* an independent
test set.
**Figure 5.3** the recommend screen with the expansion audit and the KB advisory.
**Section 5.x — feedback loop results:** rows merged, outside-label-space count, the `external_check`
block, and the note that a handful of primary rows cannot yet move the metrics.
**Section 5.y — usability:** 96 automated tests, 48 headless-UI assertions with 0 console errors,
Kannada coverage, responsive checks.
**Section 5.z — discussion:** comparison with the literature (this work reproduces the 98–99 % range
on the same public data that Shastri et al. report 98.86 % for), and where the design differs.

---

## Chapter 6 — Testing (5–6 pages)

6.1 Strategy — unit, API, integration, ML-contract, UI, and script-level verification.
6.2 Table of test cases — summary of `docs/test_cases.md` (67 cases) plus the pytest module map.
6.3 Automated run output — paste the `96 passed` line and the headless-UI summary.
6.4 Defect log with the real bugs found and fixed during development (these are strong viva material):
(a) SQLAlchemy `AmbiguousForeignKeysError` on the user↔survey relationship → explicit `foreign_keys`;
(b) **NaN crash on retrain** — primary rows carried only four inputs and were concatenated by index,
so KNN failed on missing values → primary rows are now expanded *before* reindexing;
(c) connection-pool exhaustion under repeated authenticated requests → a request-scoped session is
now closed in a teardown handler;
(d) a duplicate-review bug where the API 404 fell through to the SPA fallback and returned HTML to an
API client;
(e) a DB unique constraint that contradicted the documented `force=true` duplicate override;
(f) an additive blend letting papaya outrank rice → replaced with the geometric blend.
6.5 Coverage and limitations of testing (no load testing, no field validation, no cross-browser
matrix beyond Chromium/Firefox-width checks).

---

## Chapter 7 — Deployment (4–5 pages)

7.1 Zero-cost architecture: Render free web (Python) + Render free static + free hosted Postgres
(Neon/Supabase), with the reasoning that Render's free disk is ephemeral.
7.2 `render.yaml` walkthrough — `type: web` + `runtime: python` + `plan: free` for the API; the static
service as `type: web` + **`runtime: static`**, noting that `type: static` is invalid.
7.3 Environment variables, secrets (`generateValue`, `sync: false`), health-check path.
7.4 Cold starts: 714 KB model, lazy loading, `WARM_MODEL`, background-thread retraining for the 30 s
free request timeout.
7.5 Data persistence: hosted Postgres + committed artefacts; what happens on redeploy.
7.6 Cost table — every line ₹0 with the free-tier limits named.
7.7 Screenshots of the deployed service and `/health` output.

---

## Chapter 8 — Conclusion and future work (3–4 pages)

8.1 Objectives achieved — map each of the five objectives to a result and a file.
8.2 Contributions — the seven innovation points.
8.3 Limitations restated honestly (the eight items in README §7).
8.4 Future work — collect 300+ primary rows to replace derived labels; `data.gov.in`/IMD integration
for recorded rainfall; APMC price layer; SHAP per prediction; probability calibration; PWA/offline
mode for low-connectivity villages.

---

## References (IEEE style — use these exact sources)

1. S. Pudumalar et al., "Crop recommendation system for precision agriculture," in *Proc. IEEE 6th
   Int. Conf. Advanced Computing (ICoAC)*, 2016, pp. 32–36.
2. R. Priya, D. Ramesh, E. Khosla, "Crop prediction on the region belts of India: A Naïve Bayes
   MapReduce precision agricultural model," in *Proc. IEEE ICACCI*, 2018, pp. 99–104.
3. "Crop recommendation using machine learning algorithms: A comparative study," in *Proc. ACM*, 2024,
   doi: 10.1145/3659677.3659701.
4. S. Shastri, S. Kumar, V. Mansotra, R. Salgotra, "Advancing crop recommendation system with
   supervised machine learning and explainable artificial intelligence," *Scientific Reports*, vol. 15,
   art. 25498, 2025.
5. "Interpretable deep learning models for independent fertilizer and crop recommendation,"
   *Scientific Reports*, 2025.
6. "Agentic AI-driven autonomous decision support system for smart agriculture," *Scientific Reports*,
   2026.
7. A. Ingle, "Crop recommendation dataset," Kaggle, 2020. [Online].
   https://www.kaggle.com/datasets/atharvaingle/crop-recommendation-dataset
8. Krishi Vigyan Kendra, Dakshina Kannada — District profile. [Online].
   https://www.kvkdk.org/district_profile.html
9. KVK Dakshina Kannada, *Annual Report 2023* (rainfall, soil and cropping-area statistics).
10. Tamil Nadu Agricultural University, *Crop Production Guide* and Agritech Portal — crop climate and
    water requirements. [Online]. https://agritech.tnau.ac.in/
11. Government of India, Open Government Data Platform — district-wise Area, Production and
    Productivity statistics. [Online]. https://data.gov.in
12. Pedregosa et al., "Scikit-learn: Machine learning in Python," *JMLR*, vol. 12, pp. 2825–2830, 2011.
13. J. D. Hunter, "Matplotlib — a 2D graphics environment," *Computing in Science & Engineering*,
    vol. 9, no. 3, pp. 90–95, 2007. *(if you export figures with Matplotlib)*
14. Render, "Blueprint specification" and "Free tier limits" documentation. [Online].
    https://render.com/docs
15. Neon / Supabase free-tier Postgres documentation. [Online].

> **Rule for the report:** every accuracy quoted from another paper must carry that paper's dataset
> and protocol in the same sentence, and any figure you could not verify must be marked "not
> verified" — exactly as the app does on the Project Comparison page.

---

## Appendices

- **A** — `metrics.json` (full JSON), generated by `python -m app.ml.train`.
- **B** — Complete REST API table (README §8) plus sample `curl` requests and responses.
- **C** — Cleaning rules and mapping rules tables (`docs/dataset_schema.md` §2–§3).
- **D** — Test-case table (`docs/test_cases.md`, 67 cases), the pytest module map and the headless-Chrome UI test (`tests/ui_smoke.js`).
- **E** — `render.yaml` with annotations.
- **F** — Screenshots of all eight pages plus the Kannada UI (`docs/screenshots/`).
- **G** — Seed data inventory (users, 16 predictions, 20 surveys, 37 crops).
- **H** — Viva question bank (`docs/viva_questions.md`).

---

## Figures checklist

| # | Figure | How to produce |
|---|---|---|
| 1 | Architecture | README §3 Mermaid (render to PNG) |
| 2 | Recommendation sequence diagram | README §3 Mermaid |
| 3 | Feedback-loop diagram | `docs/dataset_schema.md` §7 Mermaid |
| 4 | ER diagram | draw from `backend/app/models.py` |
| 5 | Use-case diagram | draw from §3.6 |
| 6 | Recommend screen (top 3 + audit + advisory) | `docs/screenshots/03-recommend-results.png` |
| 7 | Confusion matrix | `docs/screenshots/07-model-performance.png` or `metrics.json` → plotted |
| 8 | Feature importance (Gini + permutation) | same |
| 9 | Dataset explorer / merge preview | `docs/screenshots/06-dataset-secondary.png` |
| 10 | Project comparison table | `docs/screenshots/08-comparison.png` |
| 11 | Kannada UI | `docs/screenshots/10-about-kannada.png` |
| 12 | Reviewed-papers accuracy comparison | plot Table 2.1 with dataset/protocol annotations |
| 13 | Deployment diagram + `/health` output | Render dashboard |
