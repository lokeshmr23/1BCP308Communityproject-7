# Test cases

62 test cases with steps and expected results. The **Automation** column says where each case is
enforced, so you can demo it live:

- `pytest tests/…` — executed by `python -m pytest -q` (**96 tests** across 6 files)
- `curl` — paste into a shell against the running server
- `UI` — drive it in the browser; the same flows are executed automatically by
  **`node tests/ui_smoke.js`** (headless Chrome, **58 checks, 0 console errors**)
- `script` — `scripts/evaluate_predictions.py`, `scripts/download_secondary_dataset.py --check`,
  `scripts/check_i18n.js`, `scripts/check_artifacts.py`
- `verify_all.sh` — one command that runs every script-level case

Everything below is reproducible with `bash scripts/verify_all.sh --with-ui` while the app is running.

Legend: **P** = priority (1 critical, 2 important, 3 nice-to-have).

## A. Health, auth and access control

| # | P | Test case | Steps | Expected result | Automation |
|---|---|---|---|---|---|
| TC-01 | 1 | Health probe | `curl /health` | `200`, `status: ok`, DB engine + `persistent` flag, `model.lazy: true`, **model not loaded** by the probe | `test_health_endpoint` |
| TC-02 | 1 | Health warns on ephemeral DB | start locally with the default SQLite DB and call `/health` | `database.persistent: false` with a note that Render's free disk is ephemeral | `test_health_reports_sqlite_as_non_persistent` |
| TC-03 | 1 | Farmer registration | POST `/api/auth/register` with name/email/password/village | `201`, role is forced to `farmer`, a JWT is returned | `test_register_and_login_flow` |
| TC-04 | 1 | Admin self-signup blocked | POST register with `"role": "admin"` | `400 invalid_request` — admins are provisioned by the seeder or another admin | `test_self_registration_as_admin_is_blocked` |
| TC-05 | 1 | Weak password rejected | register with `"password": "123"` | `400 weak_password` | `test_weak_password_rejected` |
| TC-06 | 1 | Wrong password | login with a bad password | `400 invalid_credentials` (no user-enumeration hint) | `test_login_rejects_wrong_password` |
| TC-07 | 1 | Unauthenticated read | GET `/api/auth/me` with no header | `401` | `test_me_requires_a_token` |
| TC-08 | 1 | Tampered token | GET `/api/auth/me` with `Bearer not-a-jwt` | `401 invalid_token` | `test_expired_or_garbage_token_is_rejected` |
| TC-09 | 1 | Farmer blocked from admin routes | GET `/api/auth/users`, `/api/surveys/review-queue`, `/api/surveys/cleaning-report`, POST `/api/model/retrain` as a farmer | all `403 forbidden` | `test_farmer_cannot_use_admin_endpoints` |
| TC-10 | 1 | Farmer cannot write crop reference | POST `/api/crops` as farmer | `403 forbidden` | `test_farmer_cannot_write_crop_reference` |
| TC-11 | 2 | JSON errors for unknown paths | GET `/api/does-not-exist` (and DELETE `/health`) | JSON `404 not_found` / `405 method_not_allowed` — never the SPA HTML | `test_unknown_endpoint_and_method_errors_are_json` |
| TC-12 | 2 | Nobody can read another user's history | GET another farmer's `/api/history/{id}` | `404`; the admin `scope=all` view does include it | `test_history_is_scoped_to_the_owner` |

## B. Recommendation engine

| # | P | Test case | Steps | Expected result | Automation |
|---|---|---|---|---|---|
| TC-13 | 1 | Anonymous prediction | POST `/api/predict` with the four inputs | `200`, exactly 3 ranked recommendations, decreasing score, each with a model probability, rule fit, 4 rule components, ≥4 reasons and a status band | `test_predict_anonymous_returns_top3_with_reasons` |
| TC-14 | 1 | Local crops are advisory, never predictions | inspect the response of TC-13 | `regional_advisory` non-empty for the DK profile, each entry flagged "NOT in the secondary dataset", and no advisory crop appears in the top 3 | `test_predict_includes_knowledge_base_advisory_flagged_as_not_model_output` |
| TC-15 | 1 | Determinism | POST the same payload twice | identical crops **and** identical scores | `test_deterministic_for_same_input` |
| TC-16 | 1 | Laterite + Kharif + 240 mm + high water | POST that payload | top-1 = **Rice** with a plausible score (~0.77), reasons mentioning the 100–300 mm band, an arecanut/black pepper advisory, and a rainfall-vs-need caution | UI, `evaluate_predictions.py` |
| TC-17 | 1 | Coastal sandy + Kharif + 240 mm | POST that payload | top-1 = **Coconut** (light soil, low retention) — proves soil type changes the ranking | `evaluate_predictions.py`, UI |
| TC-18 | 2 | Irrigation source overrides the water field | POST with `water_availability: high` **and** `irrigation_source: rainfed` | `input.water_availability = low` — the source is the single source of truth | `test_irrigation_source_drives_water_availability` |
| TC-19 | 2 | Regional tuning toggle | POST twice with `regional_tuning` true/false | different `blend.regional_prior`, and advisories only when tuning is on | `test_regional_tuning_changes_the_ranking_priors` |
| TC-20 | 1 | Input validation | POST invalid soil / season / water / non-numeric rainfall / rainfall 5000 | `400` with codes `invalid_soil_type`, `invalid_season`, `invalid_water_availability`, `invalid_rainfall`, `rainfall_out_of_range` | `test_validation_errors_are_structured` |
| TC-21 | 2 | Helpful rainfall message | POST `rainfall_mm: 3900` (the district's *annual* figure) | `400` explaining that the field is the **growing-window (monthly)** figure | `test_rainfall_error_message_explains_the_district_scale` |
| TC-22 | 1 | Save requires a session | POST `/api/predict` with `save: true`, no token | `400 login_required_to_save` | `test_save_requires_login` |
| TC-23 | 1 | Save writes history | POST with `save: true` and a farmer token, then GET `/api/history/{id}` | `200`; the row's `top_crop` equals the first recommendation | `test_save_persists_history_row` |
| TC-24 | 2 | Transparency endpoints | GET `/api/expansion-rules`, `/api/cleaning-rules`, `/api/meta` | soil/season profiles, 10 cleaning rules, 22 model crops, formula string — all readable without auth | `test_expansion_rules_and_cleaning_rules_are_public`, `test_meta_returns_form_vocabularies` |
| TC-25 | 2 | Expansion is monotonic and clamped | call `expand_to_agronomic` with low/medium/high water, and with rainfall 1000 mm | higher water ⇒ higher model rainfall; the value is clamped to 300 | `test_expansion_is_monotonic_in_water_availability`, `test_expansion_produces_the_seven_model_parameters` |

## C. CRUD, review workflow and the feedback loop

| # | P | Test case | Steps | Expected result | Automation |
|---|---|---|---|---|---|
| TC-26 | 1 | Prediction history CRUD | create → list → patch note → delete → re-read | `201`, present in list, note updated, `200` on delete, `404` afterwards | `test_history_crud_round_trip` |
| TC-27 | 2 | History filters + CSV | `?season=Kharif&limit=1`, then `/api/history/export` | filtered page respects the limit; export is `text/csv` containing `top_crop` | `test_history_filters_and_summary`, `test_history_export_is_csv` |
| TC-28 | 1 | Survey CRUD | POST a valid survey (consent ticked) → patch → delete | `201` with `status: pending`, `water_availability` derived from the source; patch and delete succeed | `test_survey_crud_and_pending_status` |
| TC-29 | 1 | Consent is a hard gate | POST with `consent: false` | `400 cleaning_rules_failed` with `consent_required` in `details` | `test_survey_without_consent_is_rejected` |
| TC-30 | 2 | Validation details are actionable | POST with rainfall 5000 and soil `sand` | `400` with `rainfall_out_of_range` **and** `invalid_vocabulary` in one response | `test_survey_validation_details_are_actionable` |
| TC-31 | 2 | Duplicate detection + force | submit the same row twice, then again with `force: true` | `201`, then `409` with `duplicate_of`, then `201` | `test_duplicate_survey_returns_409_then_force_creates` |
| TC-32 | 1 | Admin review workflow | view the review queue → approve with a note → read the row | row appears in the queue, becomes `approved`; an invalid status returns `400` | `test_admin_review_workflow` |
| TC-33 | 2 | Cleaning report is lossless | GET `/api/surveys/cleaning-report` | approved ≥ merging, 10 rules listed, and a note that poor outcomes are excluded | `test_cleaning_report_shows_merge_and_drop_counts`, `test_cleaning_report_is_lossless` |
| TC-34 | 1 | Feedback with consent | POST `/api/history/{id}/feedback` with actual crop, outcome and consent | `201`; prediction updated; a **pending** survey row is created with `crop_grown` = actual crop and weight 1.0 | `test_feedback_loop_writes_survey_row_when_consented` |
| TC-35 | 1 | Feedback without consent | same but `consent: false` | `400 survey_rejected` — nothing enters the dataset | `test_feedback_without_consent_does_not_enter_the_dataset` |
| TC-36 | 2 | Feedback validation | post an invented outcome value | `400 invalid_yield_outcome` | `test_feedback_rejects_bad_outcome` |
| TC-37 | 2 | Sample weights by outcome | unit-test `sample_weight_for` | excellent/good → 1.0, average → 0.5, poor → 0.0 (excluded) | `test_sample_weight_from_yield_outcome` |

## D. ML pipeline, metrics and artefacts

| # | P | Test case | Steps | Expected result | Automation |
|---|---|---|---|---|---|
| TC-38 | 1 | Four algorithms trained | `python -m app.ml.train` | `metrics.json` contains decision_tree, random_forest, knn, naive_bayes | `test_all_four_algorithms_are_compared` |
| TC-39 | 1 | Metrics contract | inspect every model block | accuracy, macro P/R/F1, weighted F1, CV mean ± std, top-3, per-class table, all in [0,1] | `test_every_model_reports_the_required_metrics` |
| TC-40 | 1 | Protocol is honest | read `dataset.protocol` | "stratified 80/20 (random_state=42) + 5-fold StratifiedKFold CV on the train split"; train+test = total rows; 22 classes | `test_protocol_is_a_stratified_split_with_cross_validation` |
| TC-41 | 1 | Model selection rule | compare `best_model.key` with all CV macro-F1 means | the maximum wins | `test_selected_model_is_chosen_by_cv_macro_f1` |
| TC-42 | 2 | Confusion matrix integrity | sum the 22×22 matrix | equals the test-row count; top-3 ≥ top-1 for every algorithm | `test_confusion_matrix_shape_matches_the_label_space`, `test_top3_accuracy_is_not_below_top1` |
| TC-43 | 1 | Ablation is reported and weaker | compare `ablation_four_inputs.best.test_accuracy` with the main best | strictly lower, with a farmer-answerable-inputs note | `test_ablation_track_is_reported_honestly` |
| TC-44 | 1 | Artefact stays small | check the `.joblib` size | < 3 MB and matches `artifacts.model_size_kb` (currently 714 KB) | `test_model_size_stays_small_enough_to_commit` |
| TC-45 | 1 | Lazy loading | construct a fresh registry | `is_loaded` false until first use; `status.lazy` true; 22 classes reported | `test_registry_is_lazy_but_loaded_after_first_use` |
| TC-46 | 1 | Geometric blend penalises a bad rule fit | score rice on alluvial/Kharif/240/high vs coastal_sandy/Zaid/25/low | good ≈ 1.0, bad < 0.5 — a high probability cannot rescue a bad fit | `test_geometric_blend_penalises_poor_rule_fit` |
| TC-47 | 2 | Waterlogging penalty is selective | score papaya and rice at 280 mm/high | papaya penalised, rice not | `test_waterlogging_penalty_only_hits_sensitive_crops` |
| TC-48 | 1 | Retrain merges primary rows safely | run the slow test (temp dir) with 4 raw rows incl. a poor yield and an arecanut row | 3 accepted (1 excluded), 1 outside the label space, frame = secondary + primary, artefact written, **no NaN crash** | `test_train_and_save_merges_primary_rows_into_a_temp_artifact` (`-m slow`) |
| TC-49 | 1 | Admin edits really change the score | import defaults, edit rice to `water_need: low`, 10–50 mm, then score it | rule fit drops below 0.75 — the knowledge base is live, not decoration | `test_editing_a_crop_changes_the_rule_fit_score` |

## E. Dataset, knowledge base and UI

| # | P | Test case | Steps | Expected result | Automation |
|---|---|---|---|---|---|
| TC-50 | 1 | Secondary dataset integrity | `python scripts/download_secondary_dataset.py --check` | 2200 rows, 22 balanced classes, 0 missing values, correct columns | `script` |
| TC-51 | 2 | Loader rejects a wrong schema | point `load_secondary()` at a 3-column CSV | `ValueError: missing required columns` | `test_load_secondary_rejects_a_wrong_schema` |
| TC-52 | 1 | Every model class has a knowledge-base entry | import the KB | 22 model classes ⊆ 33 KB crops; every entry has EN + KN names, a source and an ordered rainfall band | `test_knowledge_base_covers_every_model_class` |
| TC-53 | 2 | No placeholder text in reasons | build reasons for all 33 crops | no `None` token, no `{` braces, no `nan` | `test_reasons_never_contain_placeholders` |
| TC-54 | 2 | Crop reference public list flags KB-only crops | GET `/api/crops/reference` | ≥30 crops; `kb_only` ⟺ not in the model label space | `test_crop_reference_public_marks_kb_only_crops` |
| TC-55 | 2 | Crop CRUD + duplicate key | create → patch → delete; then create a duplicate key | `201`, patch applies, `200` delete, `404` after; duplicate → `400 duplicate_crop_key` | `test_crop_crud_round_trip`, `test_duplicate_crop_key_is_rejected` |
| TC-56 | 1 | UI: every route renders without a JS exception | sign in, visit all 8 routes | each view renders > 900 chars of HTML and none contains the error panel | `UI` (headless-Chrome run) |
| TC-57 | 1 | UI: the whole journey works | demo chip → run a recommendation → save → open history | result cards with reasons and audit, "saved" confirmation, row visible in history, feedback action present | `UI` (`tests/ui_smoke.js`) |
| TC-58 | 2 | UI: Kannada toggle | switch to ಕನ್ನಡ, visit pages, switch back | page title, form labels and content render in Kannada; 0 console errors | `UI` (`tests/ui_smoke.js`) |
| TC-59 | 2 | UI: role-aware navigation | sign in as a farmer, then as an admin | farmers see no review queue / retrain control; admins see the queue, the retrain button and all users' data | `UI` (`tests/ui_smoke.js`) |
| TC-60 | 2 | UI: responsive layout | open at 414 × 896 in the test harness | **0 px horizontal overflow**; sidebar collapses, the form stacks | `UI` (`tests/ui_smoke.js`) |
| TC-61 | 3 | UI: empty and loading states | new farmer account | skeletons while loading, empty-state cards with a call to action on history/surveys | `UI` (manual) |
| TC-62 | 2 | Serving-path sanity benchmark | `python scripts/evaluate_predictions.py` | 20 DK profiles replayed; 70 % top-1 / 85 % top-3 agreement with the district reference crops; low-confidence flag on the weak profiles; output states it is not an independent test set | `script` |
| TC-63 | 1 | Bilingual coverage | `node scripts/check_i18n.js` | 238 keys referenced, 238 present in EN and in KN, 0 empty, 0 unreferenced → exit 0 | `script` |
| TC-64 | 1 | No raw i18n key reaches the DOM | the UI test reads `document.body.innerText` on all 8 routes, in EN and KN | no `nav.…`/`rec.…`/`common.…`-style key strings visible in any view | `UI` (`tests/ui_smoke.js`) |
| TC-65 | 1 | Model/licence artefact integrity | `python scripts/check_artifacts.py` | model < 3 MB, 4 algorithms compared, recorded size matches the file, row accounting consistent, protocol line present | `script` |
| TC-66 | 2 | Lazy load and probe cost | start with `PORT=5099 WARM_MODEL=0`, poll `/health`, then predict | `/health` never loads the model (~2 ms); the first prediction loads it (0.13 s); later predictions ~40 ms | `script` (see verification.md §8) |
| TC-67 | 2 | Full reproduction in one command | `bash scripts/verify_all.sh` | 7/7 steps pass; exit code 0 | `verify_all.sh` |

### How to run everything

```bash
cd crop-advisor
python -m pytest -q                     # TC-01…TC-55 (96 tests, ~16 s)
python -m pytest -q -m slow             # adds TC-48
python scripts/download_secondary_dataset.py --check     # TC-50
python scripts/evaluate_predictions.py  # TC-62
node scripts/check_i18n.js              # TC-63
python scripts/check_artifacts.py       # TC-65
npm --prefix tests install puppeteer && node tests/ui_smoke.js   # TC-56…TC-60, TC-64
bash scripts/verify_all.sh --with-ui    # TC-67 — everything at once (needs the app running)
```
