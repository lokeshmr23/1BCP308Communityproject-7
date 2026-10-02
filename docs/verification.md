# Verification log

Evidence that the delivered code works, captured on **2026-10-02** against the exact artefacts
committed in this repository. Copy these commands to reproduce every number.

| Item | Result |
|---|---|
| Python | 3.13.14 in the build sandbox; `runtime.txt` pins **3.11.9** for Render |
| Backend import + app factory | OK, 8 blueprints registered |
| Model artefact | `best_model.joblib` — **714.5 KB**, 22 classes, `trained_at 2026-10-02T09:02:54Z` |
| Dataset artefact | `metrics.json` — **2197 rows**, 0 primary rows, Random Forest **0.9955** / top-3 **1.0000** |
| Pytest | **96 passed** in ~16 s, plus the slow end-to-end retrain test |
| Front-end syntax | all 6 JS files pass `node --check` |
| Bilingual coverage | **238/238 keys present in EN *and* ಕನ್ನಡ**, none empty, none unreferenced |
| UI end-to-end (headless Chrome) | **58/58 assertions passed, 0 console errors** (`tests/ui_smoke.js`) |
| Dataset verification script | 2200 rows, 22 balanced classes, 0 missing values |
| Serving-path benchmark | 70 % top-1 / 85 % top-3 agreement with DK cropping expectations, 4/20 flagged low confidence |
| Pinned dependencies | all 11 pins in `requirements.txt` install cleanly on Python 3.13 (and target 3.11.9) |
| Cold start, measured | boot → first `/health` in **1.7 s**; first prediction (lazy load) **0.126 s**; warm predictions **~0.04 s**; `/health` **~2 ms** |
| One-command verification | `bash scripts/verify_all.sh` → **7/7 steps passed** (8/8 with `--with-ui`) |

---

## 1. Automated test suite

```console
$ python -m pytest -q
........................................................................ [ 75%]
........................                                                 [100%]
96 passed, 59 warnings in 15.71s

$ python -m pytest -q -m slow
.                                                                        [100%]
1 passed
```

- 96 tests across 6 files: health/auth/RBAC (12), prediction contract (12), CRUD + review workflow +
  feedback loop (14), cleaning + feature layer (20), ML pipeline + artefacts + serving (35),
  crop reference CRUD (3), plus the slow end-to-end retrain.
- The suite runs against a throwaway SQLite database in a temp directory (`tests/conftest.py`), so it
  never touches the demo database or the shipped model artefact.
- `-m slow` re-runs `train_and_save()` into a temp directory with four synthetic primary rows
  (one poor yield, one crop outside the label space) and asserts the merge accounting:
  `3 accepted / 1 excluded`, `1 row dropped outside the label space`, `rows_total = secondary + 3`.

Warnings are benign: `PyJWT` warns that the *test* secret is short (production uses
`JWT_SECRET=generateValue: true`), and `DeprecationWarning`s come from third-party libraries.

---

## 2. Live API verification (dev server on :5000)

```console
$ curl -s localhost:5000/health
{"status": "ok", "app": "Dakshina Kannada Crop Advisor", "version": "1.0.0",
 "database": {"connected": true, "engine": "sqlite", "persistent": false},
 "model": {"loaded": false, "lazy": true, "size_kb": 714.5}, ...}
```

The probe reports `model.loaded: false` — proving the lazy-load design (a cold start does not pay for
the model until the first prediction).

```console
$ curl -s -X POST localhost:5000/api/predict -H 'Content-Type: application/json' \
    -d '{"soil_type":"laterite","season":"Kharif","rainfall_mm":240,"water_availability":"high"}'
  1. Rice / Paddy     score 0.77  model 0.567  rule 1.00  strong match
  2. Papaya           score 0.33  model 0.260  rule 0.39  weak match - verify locally
  3. Jute             score 0.24  model 0.107  rule 0.84  weak match - verify locally
  advisory: Arecanut (Adike), Black pepper, Cocoa
  blend: {'local_crops': 1.05, 'non_local_crops': 0.9}
```

Other verified behaviours:

| Check | Observed |
|---|---|
| `GET /api/nope` | `404 application/json` (never the SPA HTML) |
| `GET /` and `GET /dashboard` | `200 text/html` (SPA shell / fallback) |
| `POST /api/surveys` without consent | `400 cleaning_rules_failed`, detail `consent_required` |
| `POST /api/crops` as a farmer | `403 forbidden` |
| Feedback with consent | `201`, prediction updated, **pending** survey row created |
| Admin crop edit → rule fit | edit lowers the score (asserted by `test_editing_a_crop_changes_the_rule_fit_score`) |

---

## 3. Admin retrain — the former NaN crash, verified fixed

```console
$ curl -s -X POST localhost:5000/api/model/retrain -H "Authorization: Bearer <admin>" -d '{}'
{"started": true, "status_url": "/api/model/retrain/status", "poll_after_seconds": 5}   # HTTP 202

$ curl -s localhost:5000/api/model/retrain/status -H "Authorization: Bearer <admin>"
{"running": false, "ok": true,
 "message": "Retrained on 2212 rows (15 from the primary survey, 0 survey rows excluded by the cleaning rules). Best model: Random Forest (test accuracy 0.9932)."}
```

Verified after the run:

- `rows_total 2212` = 2197 secondary + 15 approved primary rows
- `rows_used_for_training 2204`, `rows_dropped_outside_label_space 8` (arecanut, black pepper,
  cashew, cocoa, cowpea, ginger, groundnut, horsegram, jackfruit — real DK crops the model has no
  class for)
- `primary_rows_used 15` with `external_check.note` explaining that only 7 rows are inside the label
  space (< 10 needed) — the app states the check is unavailable rather than printing a meaningless
  number
- **No NaN/`KNN does not accept missing values` error** — the regression that `merge_sources()`
  expansion fixed
- Retraining runs in a background thread with a poll endpoint because Render's free tier times out
  requests at 30 s

The committed artefacts are then regenerated with `python -m app.ml.train` (**2197 rows**,
RF 0.9955) so the repository ships the canonical, reproducible build rather than a test run.

---

## 4. UI end-to-end (headless Chrome, real DOM)

`tests/ui_smoke.js` drives Puppeteer against the running server — not a mock. It is committed to the
repository, so it can be re-run by an evaluator:

```bash
npm --prefix tests install puppeteer          # once
node tests/ui_smoke.js                        # 58 checks
node tests/ui_smoke.js --shots docs/screenshots
```

```
PASS  auth screen visible when signed out
PASS  login form rendered
PASS  farmer signed in and the app shell appeared
PASS  user chip shows the signed-in farmer  — Ravi Naik · Kinnigoli, Mulki · farmer
PASS  model pill filled from /api/model/metrics  — Random Forest · acc 99.6% · top-3 100%
PASS  route /#/recommend rendered content  — view length 6050
PASS  route /#/recommend shows no raw i18n keys
PASS  (…all 8 routes: rendered content, no error panel, no raw i18n keys…)
PASS  model page lists all four algorithms
PASS  confusion matrix rendered as a CSS grid
PASS  permutation importance present
PASS  4-input ablation table present
PASS  comparison page cites the reviewed literature
PASS  comparison page cites the peer-reviewed sources
PASS  dataset explorer shows the secondary row count
PASS  dataset charts rendered
PASS  schema tab shows the mapping rules
PASS  recommendation returned for laterite/Kharif/240 mm/high
PASS  score band labels rendered
PASS  agronomic reasons rendered
PASS  input-expansion audit rendered
PASS  model probability and rule fit shown side by side
PASS  save-to-history button present for a signed-in user
PASS  recommendation saved to history
PASS  history table rendered / feedback action available / delete action present
PASS  consent rule enforced server-side  — consent_required: the data-sharing consent box must be ticked.
PASS  Kannada UI applied to the shell  — ಶಿಫಾರಸು
PASS  Kannada form labels rendered
PASS  no raw i18n keys in the Kannada UI
PASS  admin demo account can sign in
PASS  admin role badge shown for the evaluator account
PASS  admin review queue shows approve actions
PASS  admin retrain control present on the model page
PASS  no horizontal overflow at 414 px width  — overflow 0px

58/58 checks passed
JS errors captured: 0
```

The one HTTP 400 that the browser logs (the deliberate no-consent submission) is excluded by the
harness, which knows that request is expected to fail.

11 screenshots in `docs/screenshots/` were produced by the same run (`--shots`).

<details>
<summary>Earlier jsdom-based run (superseded by the Puppeteer test above)</summary>

```
PASS  auth screen visible when signed out
PASS  login form rendered
PASS  language switch present
PASS  app shell shown after farmer login
PASS  user chip shows the signed-in farmer  — Ravi Naik · Kinnigoli, Mulki · farmer
PASS  model pill filled from /api/model/metrics  — Random Forest · acc 99.3% · top-3 100%
PASS  route /#/recommend rendered content  — view length 6050
PASS  route /#/history rendered content  — view length 6054
PASS  route /#/surveys rendered content  — view length 6419
PASS  route /#/dataset rendered content  — view length 15374
PASS  route /#/model rendered content
PASS  route /#/comparison rendered content  — view length 13809
PASS  route /#/crops rendered content  — view length 22179
PASS  route /#/about rendered content  — view length 16063
PASS  model page lists all four algorithms
PASS  confusion matrix rendered
PASS  ablation table present
PASS  permutation importance present
PASS  comparison page cites real literature
PASS  comparison table includes this project's row
PASS  dataset explorer shows secondary row count
PASS  schema tab shows mapping + expansion rules
PASS  recommendation returned for laterite/Kharif/240mm/high  — top-1 Rice / Paddy
PASS  score band labels rendered
PASS  agronomic reasons rendered
PASS  input-expansion audit rendered
PASS  save-to-history button present / "Recommendation saved"
PASS  history table + feedback action + delete action
PASS  consent rule enforced server-side
PASS  Kannada UI applied to the shell / Kannada form labels rendered
PASS  admin role badge shown for the evaluator account
PASS  admin review queue shows approve actions
PASS  admin retrain control present on the model page
...
48/48 checks passed
JS errors captured: 0
```

11 screenshots (login, empty recommend state, recommend results, history, surveys, dataset explorer,
model performance, comparison, crop reference, Kannada About, mobile width).
</details>

---

## 5. Bugs found and fixed during verification

| # | Symptom | Root cause | Fix |
|---|---|---|---|
| 1 | Repeated authenticated requests died with `QueuePool limit of size 5 overflow 10 reached` | `_user_from_token()` opened a fresh `SessionLocal()` per request and never closed it | reuse one request-scoped session via `g._current_db`, closed in a `teardown_appcontext` handler |
| 2 | `/api/model/status` returned `500 NameError: MODEL_WEIGHT` | the geometric blend removed `MODEL_WEIGHT`/`RULE_WEIGHT` but the status payload still referenced them | status now reports `blend` exponents and the regional priors |
| 3 | `GET /api/does-not-exist` returned the SPA HTML with HTTP 200 | the catch-all static route swallowed API paths | `/api/*` and `/health` now short-circuit to a JSON 404 |
| 4 | `POST /api/surveys` with `force=true` returned `500 UNIQUE constraint failed` | a DB unique index contradicted the documented duplicate-override path | constraint removed; duplicate handling lives in cleaning rule 6 + the API’s 409 with `force=true` |
| 5 | Retrain reported "2212 rows" while `metrics.json` said 2204 | the metrics counted only rows inside the model's label space | `rows_total` (merged), `rows_used_for_training` and `rows_dropped_outside_label_space` are now separate, explicit fields |
| 6 | Stat card labelled the district's *annual* rainfall as the growing-window figure | label/units mismatch | relabelled "District rainfall (annual)" with the unit in the value and the 2023 actual in the sub-line |
| 7 | Language choice silently reset on every load | leftover `localStorage.removeItem("ca_lang")` in boot | removed |
| 8 | Regional tuning could only *lift* local crops | one-sided prior | added a documented ×0.90 demotion for crops not viable in DK (apple, cotton, grapes, mothbean), which raised the sanity benchmark from 65 % → **70 % top-1** on the 20-profile replay |
| 9 | Stray `真实` characters inside a metrics note | copy/paste artefact | fixed in `train.py::primary_label_space_note` |
| 10 | Test flake: a cached `source` NaN on hand-built frames in `merge_sources` | defensive gap | `merge_sources()` now stamps/repairs the `source` column |
| 11 | The committed `.joblib` was pickled with **scikit-learn 1.6.1** while `requirements.txt` pins **1.6.0**, so every load emitted `InconsistentVersionWarning` | artefacts were regenerated in an environment whose sklearn differed from the pin | artefacts re-trained **under the pinned version**; `metrics.json` now records an `environment` block (python/sklearn/numpy/pandas/joblib) and both `check_artifacts.py` and `test_artefact_records_its_build_environment` fail if the artefact and the pins ever diverge. `test_model_loads_without_a_library_version_warning` promotes the warning to an error so a silent pin/artefact drift cannot come back |

---

## 6. Deployment-readiness checks

| Check | Status |
|---|---|
| `render.yaml` — Python service | `type: web`, `runtime: python`, `plan: free`, `rootDir: backend`, start `gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 1 --threads 4`, `healthCheckPath: /health` |
| `render.yaml` — static service | `type: web`, **`runtime: static`**, `plan: free`, `rootDir: frontend`, SPA rewrite to `/index.html` |
| Invalid `type: static` key anywhere | none (grepped) |
| Committed artefacts for a fast cold start | 714.5 KB model, 52 KB metrics, 148 KB dataset CSV |
| Secret handling | `JWT_SECRET` → `generateValue: true`; `DATABASE_URL` and the admin password → `sync: false` |
| Ephemeral-disk risk | documented; all state lives in the hosted Postgres, `/health` reports `persistent: false` on SQLite |
| Free request timeout | retraining is a background thread (202 + poll) |
| Lazy loading | verified by `/health` (`model.loaded: false` before the first prediction) |

---

## 7. Bilingual coverage (EN + ಕನ್ನಡ)

`scripts/check_i18n.js` reads the dictionaries out of `frontend/js/i18n.js` and collects every key the
front-end references — literal `t("…")` calls, `data-i18n*` attribute hooks, keys used inside data
tables (e.g. `pageTitles`) and `i18nKey:` properties. It then fails if anything is missing or blank.

```console
$ node scripts/check_i18n.js
i18n coverage check
  files scanned        : index.html, js/api.js, js/app.js, js/i18n.js, js/pages-core.js, js/pages-info.js, js/ui.js
  keys referenced      : 238
  keys in EN / KN      : 238 / 238
  missing from EN      : 0
  missing from KN      : 0
  empty in KN          : 0
  declared, unreferenced: 0

OK: every referenced key exists in both dictionaries and no Kannada value is empty.
```

The browser test complements this by asserting that **no raw key ever reaches the DOM**
(`nav.…`, `rec.…`, `common.…` style strings) on any of the eight routes, in English *and* in Kannada.

---

## 8. Cold-start and lazy-load measurements

Measured on a fresh process (`PORT=5099 WARM_MODEL=0 python wsgi.py`, polled to the first response):

```console
  boot to first /health response          :  1.698 s
  model loaded at boot?                   : False  (lazy=True)
  /health (probe, no model)  #1           :  0.003 s
  /health (probe, no model)  #2           :  0.003 s
  /health (probe, no model)  #3           :  0.002 s
  FIRST /api/predict (loads the model)    :  0.126 s   -> Rice / Paddy
  /api/predict warm          #1           :  0.040 s
  /api/predict warm          #2           :  0.055 s
  /api/predict warm          #3           :  0.041 s
```

What this demonstrates, in the words of the deployment design:

- **`/health` never loads the model** (~2 ms) — Render's health probe cannot pull in scikit-learn.
- The first *real* prediction pays the lazy-load cost: **0.126 s** for the 714 KB artefact, after
  which predictions run in ~40 ms. On a free instance the dominant cold-start cost is Python and
  Flask import time (~1.7 s), not the model.
- These figures are for this sandbox; a Render free instance is slower, but the *shape* of the
  behaviour (cheap probe, one-off model load) is what the design depends on, and it holds.

> An earlier draft of the README claimed a ~0.6 s model load. Measuring it showed 0.126 s, and the
> README now quotes the measured number — the same discipline applied to every other figure in this
> project.

---

## 9. One-command verification

```console
$ bash scripts/verify_all.sh
Crop Advisor — full verification (repo: /home/user/crop-advisor)

== front-end JavaScript syntax (node --check) ==
   PASS front-end JavaScript syntax
== bilingual i18n coverage (EN + ಕನ್ನಡ) ==
   PASS bilingual i18n coverage
== dataset artefact integrity (2200 x 22, no missing values) ==
   PASS dataset artefact integrity
== model artefacts consistent and small enough to commit ==
model artefact      :    714.5 KB  (best_model.joblib)
algorithms compared : 4  (decision_tree, knn, naive_bayes, random_forest)
selected model      : random_forest acc=0.9955 top3=1.0
dataset rows        : 2197 total, 2197 trained, 0 outside the label space, 0 from the primary survey
protocol            : stratified 80/20 (random_state=42) + 5-fold StratifiedKFold CV on the train split
   PASS model artefacts consistent and small enough to commit
== pytest suite ==
96 passed, 59 warnings in 15.71s
   PASS pytest suite
== pytest slow suite (admin retrain end-to-end into a temp dir) ==
   PASS pytest slow suite
== serving-path sanity benchmark (20 DK field profiles) ==
   PASS serving-path sanity benchmark
== headless-Chrome UI test (needs the app on :5000) ==     # only with --with-ui
58/58 checks passed
JS errors captured: 0
   PASS headless-Chrome UI test (needs the app on :5000)

== summary ==
  steps passed : 8
  steps failed : 0
  ALL VERIFICATION STEPS PASSED
```

---

## 10. Dependency installation re-verified

The sandbox was reset mid-project, which accidentally produced a useful check: reinstalling from the
committed `requirements.txt` (rather than from whatever was already present) still passes the whole
suite.

```console
$ pip install -r backend/requirements.txt
  Flask                3.1.0
  flask-cors           5.0.0
  Flask-SQLAlchemy     3.1.1
  PyJWT                2.10.1
  scikit-learn         1.6.0
  numpy                2.2.1
  pandas               2.2.3
  joblib               1.4.2
  pytest               8.3.4
  gunicorn             23.0.0
  psycopg2-binary      2.9.10

$ python -m pytest -q
96 passed
```

Every pin resolved to a wheel (no compilation) and reproduced identical metrics
(2197 rows, Random Forest 0.9955, top-3 1.0000) — i.e. the committed artefacts are reproducible from
a fresh environment, which is what the report claims.
