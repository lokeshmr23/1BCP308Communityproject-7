#!/usr/bin/env node
/**
 * Bilingual coverage check for the SPA.
 *
 * Fails (exit 1) if any i18n key used by the front-end is missing from the English or Kannada
 * dictionary, or if a Kannada value is empty. Run it after touching js/i18n.js or any page module:
 *
 *     node scripts/check_i18n.js
 *
 * It parses the dictionaries straight out of js/i18n.js in a sandbox (no build step) and then
 * collects keys from four sources:
 *   1. literal calls           t("rec.top3")
 *   2. attribute hooks         data-i18n="auth.signIn", data-i18n-title, -placeholder, -aria
 *   3. keys referenced in data *   pageTitles = { recommend: ["nav.recommend", "sub.recommend"] }
 *   4. object properties       i18nKey: "…"
 * Anything left over is reported as "declared but not referenced" so the dictionaries stay honest.
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const FE = path.resolve(__dirname, "..", "frontend");
const NAMESPACES = ["app", "auth", "nav", "sub", "common", "rec", "hist", "surv", "ds", "model",
  "cmp", "crops", "about", "feedback", "lang"];

// ---- 1. load the dictionaries -------------------------------------------------------------
const sandbox = {
  localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  document: { addEventListener() {}, documentElement: { setAttribute() {} }, dispatchEvent() {} },
  CustomEvent: function () {}, console
};
sandbox.window = sandbox;
vm.createContext(sandbox);
const I18N = vm.runInContext(
  fs.readFileSync(path.join(FE, "js", "i18n.js"), "utf8") + "\nI18N;", sandbox);
if (!I18N || !I18N.en || !I18N.kn) {
  console.error("Could not read the I18N dictionaries from frontend/js/i18n.js");
  process.exit(2);
}

// ---- 2. collect every key reference ------------------------------------------------------
const files = ["index.html", ...fs.readdirSync(path.join(FE, "js")).map((f) => "js/" + f)];
const sources = files.map((f) => [f, fs.readFileSync(path.join(FE, f), "utf8")]);

const known = new Set([...Object.keys(I18N.en), ...Object.keys(I18N.kn)]);
const used = new Map();      // key -> file that references it
const keyRe = new RegExp(`["'\`]((?:${NAMESPACES.join("|")})\\.[A-Za-z0-9_]+)["'\`]`, "g");
for (const [file, src] of sources) {
  let m;
  while ((m = keyRe.exec(src))) if (!used.has(m[1])) used.set(m[1], file);
}

// ---- 3. compare --------------------------------------------------------------------------
const missingEn = [], missingKn = [], emptyKn = [], unreferenced = [];
for (const key of [...used.keys()].sort()) {
  const file = used.get(key);
  if (!(key in I18N.en)) missingEn.push(`${key}  (${file})`);
  if (!(key in I18N.kn)) missingKn.push(`${key}  (${file})`);
  else if (!String(I18N.kn[key]).trim()) emptyKn.push(`${key}  (${file})`);
}
for (const key of Object.keys(I18N.en).sort()) if (!used.has(key)) unreferenced.push(key);

console.log("i18n coverage check");
console.log("  files scanned        :", files.join(", "));
console.log("  keys referenced      :", used.size);
console.log("  keys in EN / KN      :", Object.keys(I18N.en).length, "/", Object.keys(I18N.kn).length);
console.log("  missing from EN      :", missingEn.length);
missingEn.forEach((k) => console.log("      - " + k));
console.log("  missing from KN      :", missingKn.length);
missingKn.forEach((k) => console.log("      - " + k));
console.log("  empty in KN          :", emptyKn.length);
emptyKn.forEach((k) => console.log("      - " + k));
console.log("  declared, unreferenced:", unreferenced.length);
if (unreferenced.length) console.log("      " + unreferenced.join(", "));

const failures = missingEn.length + missingKn.length + emptyKn.length;
if (failures) {
  console.error(`\nFAILED: ${failures} bilingual coverage problem(s).`);
  process.exit(1);
}
console.log("\nOK: every referenced key exists in both dictionaries and no Kannada value is empty.");
