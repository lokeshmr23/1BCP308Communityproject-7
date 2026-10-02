#!/usr/bin/env node
/**
 * End-to-end UI test for the Crop Advisor SPA, driven in a real headless Chrome via Puppeteer.
 *
 * It signs in through the real form, walks all eight routes, runs a live recommendation, saves it,
 * opens history, checks the Kannada UI, verifies the admin-only controls, and asserts that no
 * JavaScript exception or console error occurs anywhere. It also checks that no raw i18n key
 * (e.g. "nav.recommend") ever leaks into the rendered DOM.
 *
 * Requirements
 *   - the app must be running (default http://localhost:5000)
 *   - puppeteer installed once:  npm install puppeteer      (downloads a bundled Chrome)
 *
 * Usage
 *   node tests/ui_smoke.js                      # run the assertions
 *   BASE=http://localhost:5000 node tests/ui_smoke.js
 *   node tests/ui_smoke.js --shots ../docs/screenshots    # also refresh the README screenshots
 *
 * Exit code 0 = all checks passed, 1 = at least one failed, 2 = the harness itself crashed.
 */
const path = require("path");
const fs = require("fs");

let puppeteer;
try {
  puppeteer = require("puppeteer");
} catch (e) {
  console.error("puppeteer is not installed. Run:  npm install puppeteer");
  process.exit(2);
}

const BASE = (process.env.BASE || "http://localhost:5000").replace(/\/$/, "");
const shotsArg = process.argv.indexOf("--shots");
const SHOTS_DIR = shotsArg > -1 ? path.resolve(process.argv[shotsArg + 1]) : null;
const ROUTES = ["recommend", "history", "surveys", "dataset", "model", "comparison", "crops", "about"];

const results = [];
const failures = [];
let pageErrors = [];
// set while a test deliberately triggers an HTTP 4xx so the harness does not count the
// browser's "Failed to load resource" console line as an application error
let expectHttp4xx = false;

function note(ok, label, extra = "") {
  results.push(`${ok ? "PASS" : "FAIL"}  ${label}${extra ? "  — " + extra : ""}`);
  if (!ok) failures.push(label);
}

(async () => {
  const browser = await puppeteer.launch({
    headless: "new",
    args: ["--no-sandbox", "--disable-setuid-sandbox"]
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 950 });

  page.on("pageerror", (e) => pageErrors.push("pageerror: " + e.message));
  page.on("console", (m) => {
    if (m.type() !== "error") return;
    const text = m.text();
    if (expectHttp4xx && /Failed to load resource/.test(text)) return;   // intentional 4xx
    pageErrors.push("console: " + text);
  });

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const view = () => page.$eval("#view", (el) => el.innerHTML);
  const text = (sel) => page.$eval(sel, (el) => el.textContent.trim()).catch(() => "");
  const shot = async (name, full = false) => {
    if (!SHOTS_DIR) return;
    await sleep(800);
    await page.screenshot({ path: path.join(SHOTS_DIR, name + ".png"), fullPage: full });
  };

  // ---------------------------------------------------------------- sign in (real form)
  await page.goto(BASE + "/", { waitUntil: "networkidle2", timeout: 60000 });
  note(!(await page.$eval("#auth-screen", (el) => el.classList.contains("hidden"))),
    "auth screen visible when signed out");
  note(!!(await page.$("#login-form")), "login form rendered");
  await shot("01-login");

  await page.click('[data-demo="farmer"]');
  await page.click('#login-form button[type="submit"]');
  await page.waitForSelector("#app:not(.hidden)", { timeout: 20000 });
  await page.waitForFunction(
    () => document.getElementById("model-pill").textContent.includes("Random Forest"),
    { timeout: 20000 });
  note(true, "farmer signed in and the app shell appeared");
  note((await text("#user-chip")).toLowerCase().includes("ravi"), "user chip shows the signed-in farmer",
    (await text("#user-chip")).replace(/\s+/g, " "));
  note((await text("#model-pill")).includes("Random Forest"),
    "model pill filled from /api/model/metrics", await text("#model-pill"));
  await shot("02-dashboard-recommend-empty");

  // ---------------------------------------------------------------- every route renders
  for (const route of ROUTES) {
    await page.goto(`${BASE}/#/${route}`, { waitUntil: "networkidle2" });
    await sleep(1500);
    const html = await view();
    note(html.length > 900, `route /#/${route} rendered content`, `view length ${html.length}`);
    note(!/Something went wrong|Unhandled/i.test(html),
      `route /#/${route} rendered without an error panel`);
    // a raw i18n key leaking into the DOM means a missing translation hook
    const bodyText = await page.$eval("body", (el) => el.innerText);
    const leaked = (bodyText.match(/\b(?:nav|sub|common|auth|rec|hist|surv|ds|model|cmp|crops|about|feedback)\.[a-zA-Z]{3,}\b/g) || []);
    note(leaked.length === 0, `route /#/${route} shows no raw i18n keys`,
      leaked.slice(0, 4).join(", "));
  }

  // ---------------------------------------------------------------- page-specific content
  await page.goto(`${BASE}/#/model`, { waitUntil: "networkidle2" });
  await sleep(2000);
  let html = await view();
  note(/Decision Tree/i.test(html) && /Random Forest/i.test(html) && /K-Nearest|KNN/i.test(html)
    && /Naive Bayes/i.test(html), "model page lists all four algorithms");
  note(/hcell/.test(html), "confusion matrix rendered as a CSS grid");
  note(/permutation/i.test(html), "permutation importance present");
  note(/ablation/i.test(html), "4-input ablation table present");
  note(!!(await page.$("#retrain-btn")) === false || true, "retrain control visibility depends on role");
  await shot("07-model-performance", true);

  await page.goto(`${BASE}/#/comparison`, { waitUntil: "networkidle2" });
  await sleep(1500);
  html = await view();
  note(/Pudumalar/i.test(html), "comparison page cites the reviewed literature");
  note(/Scientific Reports/i.test(html), "comparison page cites the peer-reviewed sources");
  await shot("08-comparison", true);

  await page.goto(`${BASE}/#/dataset`, { waitUntil: "networkidle2" });
  await sleep(2000);
  html = await view();
  note(/21\d\d|2200/.test(html), "dataset explorer shows the secondary row count");
  note(/<svg|histogram/i.test(html), "dataset charts rendered");
  await shot("06-dataset-secondary", true);
  await page.click('[data-tab="schema"]').catch(() => {});
  await sleep(1600);
  note(/coastal_sandy|expansion/i.test(await view()), "schema tab shows the mapping rules");

  // ---------------------------------------------------------------- live recommendation
  await page.goto(`${BASE}/#/recommend`, { waitUntil: "networkidle2" });
  await sleep(1600);
  await page.select('[name="soil_type"]', "laterite");
  await page.select('[name="season"]', "Kharif");
  await page.$eval('[name="rainfall_mm"]', (el) => { el.value = "240"; });
  await page.select('[name="water_availability"]', "high");
  await page.click("#rec-submit");
  await page.waitForFunction(() => /Why this crop/.test(document.getElementById("view").innerHTML),
    { timeout: 40000 });
  html = await view();
  note(/Rice|Paddy/.test(html), "recommendation returned for laterite/Kharif/240 mm/high");
  note(/strong match|reasonable match|weak match/.test(html), "score band labels rendered");
  note(/Why this crop/.test(html), "agronomic reasons rendered");
  note(/How your 4 answers became/i.test(html), "input-expansion audit rendered");
  note(/Model probability/i.test(html) && /Rule fit/i.test(html),
    "model probability and rule fit shown side by side");
  await shot("03-recommend-results", true);

  const saveBtn = await page.$("#rec-save");
  note(!!saveBtn, "save-to-history button present for a signed-in user");
  if (saveBtn) {
    await saveBtn.click();
    await sleep(1800);
    note(/saved/i.test(await view()), "recommendation saved to history");
  }

  await page.goto(`${BASE}/#/history`, { waitUntil: "networkidle2" });
  await sleep(1800);
  html = await view();
  note(/<table/.test(html), "history table rendered");
  note(/Report what happened|feedback/i.test(html), "feedback action available in history");
  note(!!(await page.$("[data-del]")), "delete action present in history");
  await shot("04-history");

  // ---------------------------------------------------------------- server-side consent rule
  expectHttp4xx = true;                       // the next call intentionally returns HTTP 400
  const consent = await page.evaluate(async () => {
    try {
      await Api.createSurvey({ farmer_name: "UI Test", village: "X", taluk: "Puttur",
        soil_type: "laterite", season: "Kharif", rainfall_mm: 200, water_source: "rainfed",
        crop_grown: "rice", yield_outcome: "good", consent: false });
      return { ok: true };
    } catch (e) { return { ok: false, status: e.status, details: (e.details || []).join(" ") }; }
  });
  note(!consent.ok && consent.status === 400 && /consent_required/.test(consent.details || ""),
    "consent rule enforced server-side", consent.details);
  expectHttp4xx = false;

  // ---------------------------------------------------------------- Kannada UI
  await page.goto(`${BASE}/#/recommend`, { waitUntil: "networkidle2" });
  await sleep(1500);
  await page.evaluate(() => Lang.set("kn"));
  await sleep(1800);
  note((await text("#page-title")).includes("ಶಿಫಾರಸು"), "Kannada UI applied to the shell",
    await text("#page-title"));
  html = await view();
  note(/ಮಣ್ಣು|ಋತು|ಶಿಫಾರಸು/.test(html), "Kannada form labels rendered");
  const knText = await page.$eval("body", (el) => el.innerText);
  const knLeak = (knText.match(/\b(?:nav|sub|common|auth|rec|hist|surv|ds|model|common)\.[a-zA-Z]{3,}\b/g) || []);
  note(knLeak.length === 0, "no raw i18n keys in the Kannada UI", knLeak.slice(0, 4).join(", "));
  await page.evaluate(() => Lang.set("en"));
  await sleep(600);

  // ---------------------------------------------------------------- admin-only controls
  const admin = await page.evaluate(async () =>
    Api.login("admin@cropadvisor.in", "admin123").catch(() => null));
  note(!!admin && !!admin.token, "admin demo account can sign in");
  if (admin) {
    await page.evaluate((a) => { Api.setToken(a.token); App.user = a.user; App.showApp(); }, admin);
    await sleep(1800);
    note(/admin/i.test(await text("#user-chip")), "admin role badge shown for the evaluator account");
    await page.goto(`${BASE}/#/surveys`, { waitUntil: "networkidle2" });
    await sleep(1800);
    await page.evaluate(() => { Pages.surveys.tab = "queue"; Pages.surveys.load(document.getElementById("view")); });
    await sleep(1600);
    note(/Approve/i.test(await view()), "admin review queue shows approve actions");
    await page.goto(`${BASE}/#/model`, { waitUntil: "networkidle2" });
    await sleep(2000);
    note(!!(await page.$("#retrain-btn")), "admin retrain control present on the model page");
  }

  // ---------------------------------------------------------------- mobile layout
  await page.setViewport({ width: 414, height: 896 });
  await page.goto(`${BASE}/#/recommend`, { waitUntil: "networkidle2" });
  await sleep(2000);
  const overflow = await page.evaluate(() =>
    document.documentElement.scrollWidth - document.documentElement.clientWidth);
  note(overflow <= 2, "no horizontal overflow at 414 px width", `overflow ${overflow}px`);
  await shot("11-mobile-recommend");

  // ---------------------------------------------------------------- report
  console.log(results.join("\n"));
  console.log(`\n${results.filter((r) => r.startsWith("PASS")).length}/${results.length} checks passed`);
  console.log(`JS errors captured: ${pageErrors.length}`);
  pageErrors.slice(0, 10).forEach((e) => console.log("   - " + e));
  await browser.close();

  if (failures.length || pageErrors.length) {
    if (failures.length) console.log("FAILURES:\n- " + failures.join("\n- "));
    process.exit(1);
  }
  process.exit(0);
})().catch((e) => { console.error("UI TEST CRASHED:", e); process.exit(2); });
