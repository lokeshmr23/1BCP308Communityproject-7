# Viva questions and answers

Ten questions an examiner is most likely to ask, with complete answers, followed by six likely
follow-ups. Every number quoted here is reproduced by the code in this repository — nothing is
rounded up and nothing is invented. (The same table appears in-app on the **About** page, so you can
demonstrate the answers live.)

---

### Q1. Why only four inputs? A model cannot predict a crop without soil nutrients and pH.

You are right that the *model* needs N, P, K, pH, temperature and humidity — and it gets all seven.
The design question is what we ask a **farmer**. Most smallholders in Dakshina Kannada cannot quote N,
P, K or pH from memory, and soil-health-card reports are not always at hand.

So the app collects four inputs a farmer *can* answer from memory — soil type, season, growing-window
rainfall and water availability — and expands them deterministically into the seven measured
parameters using documented typical profiles for the district's six soil types and three seasons
(`backend/app/ml/features.py`, published live at `GET /api/expansion-rules`).

Crucially, the app **does not hide this**: every recommendation shows the expansion audit
("laterite → pH 5.3, N 60, P 50, K 55"), and the Model Performance page reports a **4-input ablation**
that quantifies the cost of the shortcut. This is the project's central methodological choice, and it
is disclosed rather than buried.

---

### Q2. Your holdout accuracy is 99.55 %. Is that realistic? How do you know the model works in the field?

It is realistic *for this dataset* and I deliberately do not claim it is realistic for a field.

The secondary dataset is a curated, balanced set of 2200 rows with exactly 100 rows per crop and 22
crops, and its feature distributions are fairly separable. Published work on the same dataset reports
98.86 % for Random Forest (Shastri et al., *Scientific Reports* 2025), so 99.55 % here is consistent
with the literature rather than suspicious.

The honest test is the **ablation**: when the same four algorithms are trained on only the four
inputs the app actually collects (with soil type, season and water availability derived), holdout
accuracy falls from **99.55 % to ~59 %** while top-3 accuracy only falls to **~87 %**. That gap is the
real message: the dataset's power comes largely from the seven measured parameters, and a four-question
interface cannot recover all of it.

That is exactly why the product does not return a single label. It returns a **ranked top-3 with
reasons**, a rule-fit score, an explicit confidence band, a low-confidence flag, and a disclaimer
pointing to the KVK. It behaves like a decision *support* tool, not an oracle.

---

### Q3. The dataset has no soil-type, season or irrigation columns. How can you show those as inputs?

By deriving them with documented, deterministic rules and labelling them as **derived** everywhere
they appear (`docs/dataset_schema.md` §4, `GET /api/dataset/schema`, and the honesty table in
`metrics.json`):

- soil type ← pH and the N/P/K pattern, matched against the documented profiles of coastal Karnataka
  soils (lateritic pH 4.6–5.8, K-rich; leached coastal sands; fertile alluvial valleys);
- season ← temperature and rainfall bands following the district's monsoon/cool/hot calendar;
- water availability ← rainfall band adjusted for the soil's water retention
  (`effective = rainfall × (1 + retention × 0.4)`).

Only the **primary** dataset contains genuinely observed soil, season and water-source labels, and the
app reports how many such rows exist. When the primary dataset is large enough, the same pipeline can
be re-run on observed labels instead of derived ones — the merge layer treats them identically.

---

### Q4. Walk me through the recommendation you just ran. Why is rice at the top?

(Run the demo, then:) the app took the four answers and executed five visible steps.

1. **Expansion** — `laterite, Kharif, 240 mm, high water` became pH 5.3, N 60, P 50, K 55, 26.5 °C,
   88 % RH and rainfall `min(300, 240 × 1.15) = 276`.
2. **Model** — the Random Forest's `predict_proba` over 22 classes gave rice its class probability
   (shown on the card, ~33 % — the app never pretends a probability is a certainty).
3. **Rule fit** — the cited knowledge base scores the crop on four weighted criteria: water need 30 %,
   season suitability 25 %, rainfall band 25 %, soil suitability 20 %. Rice scores 1.00 here because
   lateritic soil, the Kharif window and a high-water regime are exactly its published envelope
   (TNAU: transplanted rice needs 1200–1400 mm per crop).
4. **Blend** — `score = prob^0.55 × rule_fit^0.45 × 1.05 × (waterlogging penalty if applicable)`.
   The geometric form means a crop with a poor rule fit cannot reach the top on probability alone.
5. **Rank and explain** — top 3 with reasons, cautions, and a labelled advisory block for local crops
   (arecanut, black pepper, cocoa) that are absent from the secondary dataset's 22 classes.

The card also shows the district context: laterite is the district's dominant soil, paddy occupies
48,689 ha, and rice's high water need is flagged against the reported 240 mm growing-window rainfall —
which is why an irrigation advisory appears under "Field cautions".

---

### Q5. Why Random Forest, and why do you report four algorithms?

Four algorithms are implemented in `train.py` — Decision Tree, Random Forest, KNN and Gaussian Naive
Bayes — all trained on the same stratified 80/20 split with a 5-fold `StratifiedKFold`
cross-validation on the training split only. Selection uses the **highest mean CV macro-F1**, with
test macro-F1 as the tie-breaker, so the choice does not depend on one lucky split.

Random Forest wins on this data, and its CV spread is also the tightest (±0.0014 vs ±0.0082 for the
tree and ±0.0125 for KNN), which is the real reason to prefer it: not just a higher mean, but a more
stable one. It is also the algorithm the reviewed literature converges on — Shastri et al. (2025)
report 98.86 % for RF on this same dataset, and the 2026 agentic-AI paper also settles on RF — so
the comparison lets me show where this project sits relative to published results on identical data.

Reporting all four also exposes the trade-off: Naive Bayes matches Random Forest on holdout accuracy
here (99.55 %) but is worse under cross-validation (0.9943 vs 0.9954), which is precisely the kind of
single-split illusion cross-validation exists to catch.

---

### Q6. How does explainability work — and what is the difference between the two importance charts?

Two independent methods are reported on the Model Performance page:

1. **Impurity (Gini) importance** — computed inside the fitted forest over the seven model features.
   Result: rainfall 22.7 %, humidity 21.4 %, K 18.1 %, P 14.4 %, N 11.0 %, temperature 7.2 %,
   pH 5.3 %.
2. **Permutation importance** — each feature is shuffled in the untouched test split (20 repeats) and
   the accuracy drop is measured. Result: humidity 0.279, N 0.238, rainfall 0.198, K 0.153,
   P 0.110, temperature 0.011, pH 0.011.

They agree on the headline (moisture dominates) and disagree on the second tier — Gini splits credit
across correlated features while permutation measures the damage from losing real information. That
disagreement is worth reporting rather than hiding. Both match the SHAP-based finding in Shastri et
al. (2025) that rainfall and humidity dominate.

Beyond model-level importance, this app also explains **each individual prediction**: the rule-fit
breakdown (water/season/rain/soil weights), the reasons drawn from the crop's cited envelope, the
field cautions (waterlogging, salinity, duration vs. the growing window), and the expansion audit.

---

### Q7. What happens when a farmer's feedback contradicts the model? Could the loop corrupt the training set?

Four safeguards, all visible in the code and the UI:

1. **Human in the loop.** Feedback with consent becomes a survey row with `status = pending`. It
   cannot train anything until an admin/evaluator approves it, and rejections keep a review note.
2. **No silent poisoning.** Rows where `yield_outcome = poor` (rule 7) are *excluded* from training —
   a failed crop is not evidence that the crop suits the field, since the failure may be pest, labour
   or water-timing related. Average outcomes enter at `sample_weight = 0.5`, good/excellent at 1.0.
3. **Deduplication (rule 6)** collapses repeated farmer + village + season + crop + rainfall
   submissions so one enthusiastic contributor cannot dominate the weights.
4. **Auditability.** `clean_training_rows()` is lossless — every row is either accepted with the rules
   it passed, or dropped with a reason and a rule id — and `GET /api/surveys/cleaning-report` shows the
   counts live. The retrain endpoint reports how many primary rows were merged and how many fell
   outside the model's label space (e.g. arecanut is a real DK crop but not one of the 22 classes).

And importantly, the loop is currently *small*: with a handful of approved rows the retrained model is
statistically almost identical to the base model, and the app says so instead of claiming improvement
(see `external_check.note` in `metrics.json`).

---

### Q8. Which parts of this are genuinely new compared with the existing projects you reviewed?

The Project Comparison page lists five comparable systems and states what each does better and what I
borrowed. The pieces I have not seen combined anywhere in the reviewed set:

1. **Season and water availability as first-class inputs** for a coastal, monsoon-heavy district —
   the reviewed systems take N/P/K/pH/temperature/humidity/rainfall only.
2. **Top-3 with reasons instead of a single label**, plus a rule-fit breakdown, a confidence band and
   a low-confidence flag.
3. **Regional tuning** in which the district's documented cropping pattern both lifts local crops
   (×1.05) and demotes crops documented as not viable here (×0.90 — apple, cotton, grapes, mothbean).
4. **An honest 4-input ablation**: the same four algorithms retrained on the farmer-answerable inputs,
   published as a first-class metric (99.55 % → ~59 %) rather than hidden.
5. **A consent-gated feedback loop that grows the district's own primary dataset** and retrains the
   models, with cleaning rules, sample weighting and human review.
6. **A knowledge-base advisory channel** that surfaces local crops the dataset lacks (arecanut, black
   pepper, cashew, cocoa, rubber) clearly labelled as *not* model output.
7. **Deployment on a genuine zero-cost stack** — Render free web + free static + free hosted Postgres,
   a 714 KB committed model and lazy loading — engineered specifically for cold starts and ephemeral
   disks.

What I explicitly did **not** adopt from the literature: deep models (TabNet, LSTM) and IoT sensing
layers, because there is no instrumented data here, no GPU budget and no path to validate them offline
— claiming a deep model in these conditions would be decoration.

---

### Q9. Why do you show ~99.55 % accuracy, and how do you stop a reviewer thinking it is field accuracy?

The number is exactly what the holdout evaluation produces, and it is scoped explicitly: "7 measured
parameters, 2197 curated rows, stratified 80/20, 22 classes." Next to it the page shows the ablation
(~59 % on the four collected inputs), the class balance (100 rows/class) and the fact that three of the
four user inputs are derived columns. `metrics.json` ships with an `honest_limitations` array that the
UI renders verbatim, and the same caveats appear in the disclaimer under every recommendation.

In other words, the app's default posture is to pre-empt the over-claiming critique rather than invite
it. That is also why the README reports the sanity-benchmark result (70 % top-1 / 85 % top-3 agreement
with district cropping expectations on 20 replay profiles) instead of the holdout number as the
headline claim about usefulness.

---

### Q10. Why is the accuracy only ~59 % in your ablation, and is the app therefore useless?

It is not useless, but it is not a lab-grade predictor either — and the numbers say exactly where the
value lies.

The ablation trains on the four inputs the app collects, deriving soil type, season and water
availability rather than measuring them. In that setting:

- **top-1** accuracy falls to about 59 % — i.e. if the app showed only its first choice, it would be
  wrong roughly two times in five;
- **top-3** accuracy stays at about **87 %** — the right crop is in the three shown cards most of the
  time.

That is precisely why the interface returns three ranked options with reasons and cautions, why the
rule-fit layer exists (a well-known agronomic envelope can veto a statistically attractive but
agronomically wrong crop), why regional tuning demotes crops that do not grow here, and why local
crops outside the dataset's label space appear as advisories. The user is never handed a bare label;
they get a shortlist, an explanation, and a phone number for their Krishi Vigyan Kendra.

The honest framing for the report: **this is a decision-support and data-collection platform whose ML
component is deliberately transparent about the cost of a farmer-friendly interface — and whose
feedback loop is the mechanism intended to close that gap over time.**

---

## Likely follow-ups

### F1. Where exactly do your data-cleaning rules live, and can I see them applied?

`backend/app/cleaning.py` holds the ten primary rules and the sample-weight function;
`features.load_secondary()` holds the five secondary rules. Both are published by the API
(`/api/cleaning-rules`, `/api/dataset/schema`) and rendered in the app. The admin view
**Surveys → Cleaning report** shows, live: approved rows, rows merging now, rows dropped and the rule
counts. Every survey detail modal lists the rules that row passed or the reason it was rejected.

### F2. How do you know the class probabilities you display are meaningful?

They are the Random Forest's `predict_proba` values and are labelled "Model probability" to keep them
distinct from the blended "Suitability score". Two honest caveats are shown on the card: the model is
trained on a **balanced** 22-class set (so priors are uniform by construction rather than by reality),
and its high-rainfall inputs are extrapolations. The blended score and the probability are always
displayed side by side so the difference is visible, not hidden.

### F3. What stops a farmer from entering nonsense or abusive data?

Validation happens server-side (`ApiError` with structured `code`/`details`): vocabulary checks on
soil/season/water source, numeric range checks on rainfall and area, a required-crop check, a consent
hard gate, and duplicate detection returning HTTP 409 with the existing row id. Free-text fields are
escaped in the UI. Rate-limiting and CAPTCHA are **not** implemented — a genuine limitation for public
deployment, listed on the About page.

### F4. How is the app secured?

JWT bearer tokens (HS256, `JWT_SECRET` from the environment, generated by Render in production),
`werkzeug` password hashing, role checks on every admin route (`admin_required`), owner scoping on
history and survey rows (an admin may pass `scope=all`), structured audit logging of writes, and no
personal identifiers in any training feature. Known gaps: no refresh-token rotation, no rate limiting,
and the demo credentials must be rotated before a public launch.

### F5. What does the app do about the fact that arecanut, cashew and black pepper are the district's
real cash crops but are missing from the dataset?

They are first-class in the **knowledge base** (`knowledge.py`, sourced from TNAU/ICAR/KVK-DK agronomy)
and are surfaced on every relevant recommendation as "Regional advisory (knowledge base) — KB only",
with a rule-fit score and reasons, and with an explicit disclaimer that they are *not* model output
because the classifier has no such class. The same crops can also be recorded in surveys; the retrain
report counts them as `primary_rows_outside_label_space` so the gap is quantified rather than ignored.

### F6. What would you do next if you had another semester?

1. Collect ~300+ approved primary rows across the ten taluks so the observed soil/season/water labels
   can replace the derived ones, and re-run the external sanity check on a real holdout.
2. Wire in `data.gov.in` district statistics and IMD taluk rainfall so rainfall comes from records
   instead of recall.
3. Add season-long yield tracking (sowing → harvest) to turn the feedback loop into a genuine
   outcome dataset with revenue estimates from local APMC prices.
4. Ship a lightweight offline/PWA mode for low-connectivity villages, and an SMS/USSD entry path.
5. Add SHAP explanations per prediction and a proper calibration curve for the probabilities.
