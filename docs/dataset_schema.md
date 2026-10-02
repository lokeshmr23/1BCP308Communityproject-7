# Dataset specification — secondary, primary, mapping, merging and the feedback loop

This document is the single source of truth for how data enters and leaves the Crop Advisor. It is
mirrored in the app under **Dataset Explorer → Schema & rules** (`GET /api/dataset/schema`), so a
farmer, a KVK officer or an examiner can read it without opening the code.

---

## 1. Two data sources

| | **Secondary** (for training) | **Primary** (collected in-app) |
|---|---|---|
| File / table | `backend/data/secondary/crop_recommendation.csv` | `survey_entries` (SQL) |
| Origin | Kaggle — *Crop Recommendation Dataset* (atharvaingle) | Farmers / KVK staff in Dakshina Kannada via the survey form |
| Licence / consent | Public, free for academic use | Explicit per-row consent checkbox (hard gate) |
| Size in demo | 2200 rows (2197 after cleaning) | 20 seeded rows; grows with real use |
| Ground-truth soil / season / irrigation labels | **None** — these are derived | **Yes** — real observations |
| Role in the project | Teaches the classifier the crop ↔ parameter relationship | Validates, extends and localises it; feeds the feedback loop |

**Why not train on the primary data alone?** Because it is small by nature. A district can generate
hundreds of survey rows in a season, not tens of thousands — and the model has 22 classes. The
secondary dataset supplies breadth; the primary data supplies trust, regional specificity and a
genuine feedback loop. Merging them is the honest middle path, and the app reports exactly how many
primary rows are in each training run.

---

## 2. Secondary dataset — field-level schema

| Column | Type | Range in the data | Meaning |
|---|---|---|---|
| `N` | int | 0–140 | soil nitrogen (kg/ha) |
| `P` | int | 5–145 | soil phosphorus (kg/ha) |
| `K` | int | 5–205 | soil potassium (kg/ha) |
| `temperature` | float | 8.8–43.7 | mean growing-period temperature (°C) |
| `humidity` | float | 14.3–100 | relative humidity (%) |
| `ph` | float | 3.5–9.9 | soil pH |
| `rainfall` | float | 20.2–298.6 | **growing-window rainfall (mm), dataset scale** |
| `label` | string | 22 values | crop class (100 rows each) |

Class list (model label space): apple, banana, blackgram, chickpea, coconut, coffee, cotton, grapes,
jute, kidneybeans, lentil, maize, mango, mothbeans, mungbean, muskmelon, orange, papaya, pigeonpeas,
pomegranate, rice, watermelon.

### 2.1 Cleaning rules (secondary) — implemented in `features.load_secondary()`

| Rule | Action | Rows affected |
|---|---|---|
| pH outside [3.0, 9.5] | drop | 1 |
| rainfall outside [0, 1000] mm | drop | 0 |
| temperature outside [−5, 50] °C | drop | 0 |
| exact duplicate rows | drop | 1 (plus 1 downstream overlap) |
| label text | trim → lowercase → snake_case | 0 (normalisation only) |

Net effect in this build: **2200 → 2197 rows**, printed by
`scripts/download_secondary_dataset.py --check` and reported in `metrics.json`.

### 2.2 ⚠️ Rainfall scale warning (stated in the UI)

The dataset's `rainfall` column stops at ≈299 mm per period. Dakshina Kannada's normal annual
rainfall is ≈4000 mm with most of it in June–September, so a single monsoon month can exceed the
dataset's maximum. Consequences, and what the project does about them:

1. The form asks for **growing-window (monthly) rainfall**, not the yearly total, and the API
   rejects >1000 mm with an explanatory message.
2. Model inputs are clamped to the dataset's own scale (0–300 mm).
3. Water availability, the rainfall-band rule fit and regional tuning are separate inputs precisely
   because the model's high-rainfall behaviour is extrapolation.
4. The limitation is printed in `metrics.json` and on the About page.

---

## 3. Primary dataset — field-level schema (`survey_entries`)

| Field | Type | Required | Notes |
|---|---|---|---|
| `farmer_name` | text | ✔ | identification for follow-up only — never a model feature |
| `village` | text | ✔ | used for duplicate detection and for KVK reporting |
| `taluk` | enum | ✔ | Dakshina Kannada taluks (Mangaluru, Ullal, Mulki, Moodabidri, Bantwal, Belthangady, Puttur, Sullia, Kadaba, other) |
| `phone` | text | ✖ | contact only |
| `soil_type` | enum | ✔ | **real observation**: laterite, red_loam, alluvial, coastal_sandy, black, coastal_saline |
| `season` | enum | ✔ | **real observation**: Kharif / Rabi / Zaid |
| `rainfall_mm` | float | ✔ | 0–1000 (growing window) |
| `water_source` | enum | ✔ | **real observation**: rainfed, open_well, borewell, drip_micro, tank, canal, river_lift |
| `water_availability` | enum | derived | mapped from `water_source` (single source of truth) |
| `crop_grown` | text | ✔ | **the label**: normalised to snake_case |
| `yield_outcome` | enum | ✔ | poor / average / good / excellent → drives `sample_weight` |
| `area_acres` | float | ✖ | 0.01–100 |
| `notes` | text | ✖ | free text, not a feature |
| `consent` | bool | ✔ | **hard gate** — false ⇒ the row can never enter the dataset |
| `status` | enum | auto | pending → approved / rejected by an admin/evaluator |
| `reviewed_by`, `reviewed_at`, `review_note` | — | auto | review audit trail |
| `sample_weight` | float | derived | see §4.3 |

### 3.1 Cleaning rules (primary) — implemented in `cleaning.py`

| # | Rule | Action | Code path |
|---|---|---|---|
| 1 | Consent not ticked | reject `consent_required` | `validate_survey_payload` + `clean_training_rows` |
| 2 | Missing soil/season/water/crop/outcome (or farmer/village/taluk) | reject `missing_required` | both |
| 3 | `rainfall_mm` outside 0–1000 | reject `rainfall_out_of_range` | both |
| 4 | `area_acres` ≤ 0 or > 100 | reject `area_out_of_range` | both |
| 5 | Value outside the controlled vocabularies | reject `invalid_vocabulary` | both |
| 6 | Same farmer + village + season + crop + rainfall submitted twice | collapse to the latest; API returns **409** unless `force=true` | both |
| 7 | `yield_outcome == poor` | excluded from training `excluded_poor_yield` | merge time |
| 8 | `yield_outcome == average` | `sample_weight = 0.5` `partial_confidence` | merge time |
| 9 | `yield_outcome` good / excellent | `sample_weight = 1.0` | merge time |
| 10 | `status != approved` | not merged | merge time |

Every application of a rule is logged on the row (`rules_applied`) or returned by
`GET /api/surveys/cleaning-report`, so nothing disappears silently. The report is **lossless**:
`accepted + dropped == approved rows` (asserted in the test suite).

**Why rule 7 exists.** A farmer who grew rice on laterite and reported a *poor* yield has not
demonstrated that rice suits laterite — the failure may come from pests, labour, water timing or
price. Excluding poor outcomes prevents noise from teaching the model the wrong lesson, while
average outcomes are kept at half weight instead of being thrown away.

---

## 4. Mapping: secondary rows → the four decision inputs

The secondary dataset has no soil-type, season or irrigation column, so these are **derived** with
deterministic rules. This is a modelling decision, not a measurement, and it is labelled as such in
the API, the UI and `metrics.json`.

### 4.1 `soil_type` ← pH and N/P/K

| Rule (first match wins) | Derived class |
|---|---|
| pH ≥ 8.0 and K < 40 | `coastal_saline` |
| pH ≥ 7.2 and K ≥ 55 | `black` |
| pH < 5.6 and K ≥ 40 | `laterite` |
| N ≥ 80 and 6.0 ≤ pH ≤ 7.2 | `alluvial` |
| pH ≥ 6.5 and K < 25 | `coastal_sandy` |
| otherwise | `red_loam` |

Basis: documented profiles of the soils of coastal Karnataka — lateritic soils are acidic (pH
4.6–5.8) and iron-rich; alluvial valley soils are fertile and near-neutral; coastal sands are
leached and low in potassium; black vertisols are neutral-alkaline with high K (rare in DK, ~5 %).
Sources: KVK Dakshina Kannada district profile / annual report; KSNDMC-NRDMS Dakshina Kannada
natural-resource report.
**Honesty note:** no ground-truth soil-type label exists in the secondary dataset.

### 4.2 `season` ← temperature and rainfall

| Rule | Derived season |
|---|---|
| rainfall ≥ 110 and not hot | `Kharif` (malnad/coastal monsoon window) |
| temperature ≤ 22 | `Rabi` (cool post-monsoon) |
| temperature ≥ 31, or ≥ 26 with rainfall < 55 | `Zaid` (hot summer) |
| otherwise rainfall ≥ 110 | `Kharif` |
| otherwise | `Rabi` |

**Honesty note:** no season column exists in the secondary dataset.

### 4.3 `water_availability` ← rainfall band + soil water retention

```
effective = rainfall × (1 + retention × 0.4)
retention by soil: alluvial .40, black .55, laterite .35, red_loam .30, coastal_saline .10, coastal_sandy .05
≥ 135 → high     78–135 → medium     < 78 → low
```

**At inference this proxy is not used.** The user picks a real irrigation source and the API maps
it directly: rainfed → low; open well / borewell / drip → medium; tank / canal / river lift → high.
The proxy exists only so that the secondary data can carry a water-availability feature at all.

### 4.4 `rainfall_mm` — the one 1:1 column

Used directly from the dataset (growing-window mm). No transformation.

---

## 5. Expansion: the four collected inputs → the seven model parameters

The model is trained on seven *measured* parameters; the form asks four *answerable* questions. The
bridge is a documented, deterministic expansion (`features.expand_to_agronomic`). It is printed on
every result page.

### 5.1 Soil → pH, N, P, K (representative profile after the standard fertilizer dose)

| Soil type | pH | N | P | K | Notes |
|---|---|---|---|---|---|
| laterite | 5.3 | 60 | 50 | 55 | dominant DK soil, acidic, K-rich |
| red_loam | 6.0 | 65 | 50 | 45 | moderately acidic, medium fertility |
| alluvial | 6.8 | 85 | 55 | 45 | fertile valley/river-bank soil |
| coastal_sandy | 6.6 | 50 | 45 | 25 | leached, low K, low retention |
| black | 7.6 | 55 | 60 | 80 | vertisol (rare in DK) |
| coastal_saline | 8.2 | 50 | 45 | 35 | saline coastal soils |

> **Why "after the standard dose"?** Every row of the secondary dataset was produced on a managed
> field, so its nutrient levels reflect fertilized soil. Feeding the app *depleted* soil-test values
> was tested and produced rankings that contradict DK agronomy (rice pushed below papaya in a
> monsoon profile). What genuinely differs between soil types — and what the farmer's answer
> actually conveys — is pH, potassium status and texture, which the table preserves. The choice is
> stated in `features.py`, in the API (`/api/expansion-rules`) and on the About page.

### 5.2 Season → temperature, humidity (coastal-belt envelope)

| Season | Temperature (°C) | RH (%) |
|---|---|---|
| Kharif | 26.5 | 88 |
| Rabi | 21.5 | 72 |
| Zaid | 32.0 | 55 |

### 5.3 Water availability → irrigation index on rainfall

| Water availability | Index |
|---|---|
| low (rainfed only) | ×0.85 |
| medium (well / borewell / drip) | ×1.00 |
| high (tank / canal / river lift) | ×1.15 |

Final model input: `min(300, max(0, rainfall_mm × index))` — clamped to the dataset's own scale.

---

## 6. Unified schema and the merge procedure

Both sources are reduced to the same seven columns:

| soil_type | season | rainfall_mm | water_availability | crop | source | sample_weight |
|---|---|---|---|---|---|---|

`source ∈ {secondary_kaggle, primary_survey}` so every row's provenance survives training, and the
API can report how many primary rows were actually used.

**Merge algorithm** (`features.merge_sources` → `train.train_and_save`):

1. Load and clean the secondary CSV (§2) → 2197 rows, `source = secondary_kaggle`,
   `sample_weight = 1.0`.
2. Fetch **approved** primary rows, apply cleaning rules 1–10 (`cleaning.clean_training_rows`),
   set `sample_weight` from the yield outcome.
3. Expand each primary row's four observed inputs into the seven agronomic parameters (same
   expansion layer used at serving time) so both sources live in one feature space.
4. Stack both frames; drop rows with `sample_weight = 0` (i.e. rule 7 exclusions).
5. Keep only crops inside the model's 22 classes; **count and report** the rows dropped for this
   reason (they are local crops such as arecanut, cashew, black pepper, ginger, cowpea, groundnut,
   horsegram, jackfruit — real observations that cannot train a classifier that has no such class).
6. Refit all four algorithms with a stratified 80/20 split + 5-fold CV; sample weights are applied
   for the tree models (KNN and GaussianNB do not accept `sample_weight` — stated in the metrics so
   the comparison stays honest).
7. Persist `best_model.joblib` + `metrics.json` (which now records `primary_rows_used`,
   `primary_rows_outside_label_space` and, when ≥10 in-class primary rows exist, an **external
   sanity check** comparing served recommendations with the crop actually grown).

---

## 7. Feedback loop (end to end)

```
Farmer saves a recommendation (My History)
        │
        ├─ reports the crop actually grown + yield outcome (+ consent)
        ▼
POST /api/history/{id}/feedback
        │   prediction row updated (actual_crop, yield_outcome, followed_advice, feedback_at)
        └─ consent given → a survey_entries row is created (status = pending)
        ▼
Admin/evaluator reviews   →   POST /api/surveys/{id}/review  (approved | rejected)
        ▼
POST /api/model/retrain   →   merge + clean + weight + retrain all four models (background thread)
        ▼
GET /api/model/metrics    →   primary_rows_used > 0, external_check block, updated confusion matrix
```

Design choices worth defending in a viva:

- **Human in the loop.** One farmer's claim never silently rewrites the model; an evaluator approves
  first. Rejected rows keep a `review_note` explaining why.
- **Weighted trust.** "Excellent/good" = 1.0, "average" = 0.5, "poor" = excluded (rule 7).
- **Deduplication.** Rule 6 prevents one enthusiastic submitter from dominating the training set.
- **Ephemeral-disk caveat.** On Render's free tier a retrain writes to that instance's ephemeral
  disk; commit the artefact (or retrain in CI) to make it permanent. The app says this in the UI.
- **Ethics.** Consent is a hard gate; training features contain no personal identifiers; every write
  is audit-logged.

---

## 8. Extending to other free Indian data sources

The merge layer is deliberately source-agnostic — any source that can be reduced to the unified
schema (§6) plus seven agronomic parameters drops in without touching the API or the UI:

| Source | How it would be used |
|---|---|
| `data.gov.in` — district-wise Area Production Statistics | ground-truth crop areas per taluk to weight or validate regional tuning |
| ICRISAT district-level data | soil and agro-climatic attributes for taluks outside the coastal belt |
| IMD rainfall | replace the user-reported rainfall with the taluk's recorded seasonal rainfall |
| State soil health card data | replace the assumed soil profiles in §5.1 with measured pH/N/P/K per village |

Each addition should follow the same discipline used here: document the mapping rule, label derived
columns as derived, and report the ablation so the reader can see what the extra data actually buys.
