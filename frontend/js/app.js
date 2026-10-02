/* App shell: auth, routing, i18n binding, nav, session handling. */
const App = {
  user: null,
  meta: null,
  route: "recommend",
  isAdmin: false,
  pageTitles: {},

  async boot() {
    this.bindAuth();
    this.bindShell();
    document.addEventListener("langchange", () => { this.applyI18n(); this.render(); });

    // restore a session if a token exists
    if (Api.getToken()) {
      try {
        const me = await Api.me();
        this.user = me.user;
      } catch (e) { Api.setToken(null); }
    }
    await this.loadMeta();
    this.applyI18n();

    if (this.user) this.showApp();
    else this.showAuth();

    window.addEventListener("ca:unauthorised", () => {
      this.user = null;
      UI.toast("Your session expired — please sign in again", "warn", 5000);
      this.showAuth();
    });
    window.addEventListener("hashchange", () => this.render());
  },

  async loadMeta() {
    try {
      this.meta = await Api.meta();
      const kb = await Api.cropReferencePublic();
      this.meta.crops_all = kb.crops.map((c) => ({
        value: c.crop, label: `${c.name}${c.kb_only ? " (KB advisory)" : ""}`, label_kn: c.name_kn, category: c.category
      })).sort((a, b) => a.label.localeCompare(b.label));
    } catch (e) {
      UI.toast("Could not load app metadata: " + e.message, "err", 8000);
    }
  },

  // ------------------------------------------------------------------ auth
  bindAuth() {
    const langHost = document.getElementById("auth-lang");
    this.renderLangSwitch(langHost);

    document.querySelectorAll("[data-auth-tab]").forEach((tab) => tab.addEventListener("click", () => {
      document.querySelectorAll("[data-auth-tab]").forEach((x) => x.classList.toggle("active", x === tab));
      document.getElementById("login-form").classList.toggle("hidden", tab.dataset.authTab !== "login");
      document.getElementById("register-form").classList.toggle("hidden", tab.dataset.authTab !== "register");
    }));

    document.querySelectorAll("[data-demo]").forEach((chip) => chip.addEventListener("click", () => {
      const isEval = chip.dataset.demo === "eval";
      document.getElementById("login-form").querySelector('[name="email"]').value = isEval ? "admin@cropadvisor.in" : "ravi@example.com";
      document.getElementById("login-form").querySelector('[name="password"]').value = isEval ? "admin123" : "farmer123";
      document.querySelector('[data-auth-tab="login"]').click();
      UI.toast(isEval ? "Evaluator credentials filled — press Sign in" : "Farmer credentials filled — press Sign in", "info", 2600);
    }));

    document.getElementById("login-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const err = document.getElementById("login-error");
      err.textContent = "";
      const data = UI.readForm(e.target);
      const btn = e.target.querySelector("button[type=submit]");
      btn.disabled = true; btn.innerHTML = `<span class="spinner"></span>`;
      try {
        const out = await Api.login(data.email, data.password);
        Api.setToken(out.token);
        this.user = out.user;
        UI.toast(`Welcome, ${out.user.name}`, "ok", 2600);
        this.showApp();
      } catch (ex) {
        err.textContent = ex.message;
      } finally {
        btn.disabled = false; btn.textContent = t("auth.signIn");
      }
    });

    document.getElementById("register-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const err = document.getElementById("register-error");
      err.textContent = "";
      const data = UI.readForm(e.target);
      const btn = e.target.querySelector("button[type=submit]");
      btn.disabled = true; btn.innerHTML = `<span class="spinner"></span>`;
      try {
        const out = await Api.register({ ...data, role: "farmer" });
        Api.setToken(out.token);
        this.user = out.user;
        UI.toast(`Account created — welcome, ${out.user.name}`, "ok", 3000);
        this.showApp();
      } catch (ex) {
        err.textContent = ex.details && ex.details.length ? `${ex.message}: ${ex.details.join("; ")}` : ex.message;
      } finally {
        btn.disabled = false; btn.textContent = t("auth.register");
      }
    });

    // the taluk select in the register form is filled by applyI18n()
  },

  // ------------------------------------------------------------------ shell
  bindShell() {
    this.renderLangSwitch(document.getElementById("app-lang"));
    document.getElementById("logout").addEventListener("click", () => {
      Api.setToken(null); this.user = null; this.isAdmin = false;
      UI.toast("Signed out", "info", 1800);
      this.showAuth();
    });
    const sidebar = document.getElementById("sidebar");
    const backdrop = document.getElementById("nav-backdrop");
    const closeNav = () => { sidebar.classList.remove("open"); backdrop.classList.remove("show"); };
    document.getElementById("open-nav").addEventListener("click", () => { sidebar.classList.add("open"); backdrop.classList.add("show"); });
    document.getElementById("close-nav").addEventListener("click", closeNav);
    backdrop.addEventListener("click", closeNav);
    document.getElementById("nav").addEventListener("click", (e) => { if (e.target.closest(".nav-item")) closeNav(); });

    // keyboard shortcut: 1..8 jump between pages (handy during a demo)
    document.addEventListener("keydown", (e) => {
      if (e.target.matches("input, select, textarea") || e.metaKey || e.ctrlKey) return;
      const order = ["recommend", "history", "surveys", "dataset", "model", "comparison", "crops", "about"];
      const idx = parseInt(e.key, 10);
      if (idx >= 1 && idx <= order.length) location.hash = "#/" + order[idx - 1];
    });
  },

  renderLangSwitch(host) {
    if (!host) return;
    host.innerHTML = `<button data-lang="en" class="${Lang.current === "en" ? "active" : ""}">EN</button>
      <button data-lang="kn" class="${Lang.current === "kn" ? "active" : ""}">ಕನ್ನಡ</button>`;
    host.querySelectorAll("[data-lang]").forEach((b) => b.addEventListener("click", () => Lang.set(b.dataset.lang)));
  },

  applyI18n() {
    document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
    this.renderLangSwitch(document.getElementById("app-lang"));
    this.renderLangSwitch(document.getElementById("auth-lang"));
    const tab = document.getElementById("register-taluk");
    if (tab && this.meta) tab.innerHTML = UI.options(this.meta.taluks, "");
    this.pageTitles = {
      recommend: ["nav.recommend", "sub.recommend"], history: ["nav.history", "sub.history"],
      surveys: ["nav.surveys", "sub.surveys"], dataset: ["nav.dataset", "sub.dataset"],
      model: ["nav.model", "sub.model"], comparison: ["nav.comparison", "sub.comparison"],
      crops: ["nav.crops", "sub.crops"], about: ["nav.about", "sub.about"]
    };
  },

  showAuth() {
    document.getElementById("auth-screen").classList.remove("hidden");
    document.getElementById("app").classList.add("hidden");
    this.applyI18n();
  },

  showApp() {
    document.getElementById("auth-screen").classList.add("hidden");
    document.getElementById("app").classList.remove("hidden");
    this.isAdmin = this.user && this.user.role === "admin";
    const chip = document.getElementById("user-chip");
    chip.innerHTML = `<strong>${UI.esc(this.user.name)}</strong>
      <span>${UI.esc(this.user.village ? this.user.village + ", " : "")}${UI.esc(this.user.taluk || "Dakshina Kannada")}</span>
      <span class="role-badge ${this.isAdmin ? "role-admin" : "role-farmer"}">${UI.esc(this.isAdmin ? "admin / evaluator" : "farmer")}</span>`;
    this.render();
    // populate the model pill + cache metrics for the comparison page
    Api.metrics().then((m) => {
      window.__metrics = m;
      const pill = document.getElementById("model-pill");
      if (pill) pill.textContent = `${m.best_model.label} · acc ${UI.pct(m.best_model.metrics.test_accuracy, 1)} · top-3 ${UI.pct(m.best_model.metrics.top3_accuracy, 0)}`;
    }).catch(() => {
      const pill = document.getElementById("model-pill");
      if (pill) pill.textContent = "model metrics unavailable";
    });
  },

  currentRoute() {
    const hash = (location.hash || "").replace("#/", "").split("?")[0];
    const known = ["recommend", "history", "surveys", "dataset", "model", "comparison", "crops", "about"];
    return known.includes(hash) ? hash : "recommend";
  },

  render() {
    if (!this.user) return this.showAuth();
    const route = this.currentRoute();
    this.route = route;
    document.querySelectorAll(".nav-item").forEach((a) => a.classList.toggle("active", a.dataset.route === route));
    const [titleKey, subKey] = (this.pageTitles[route] || ["nav.recommend", ""]);
    document.getElementById("page-title").textContent = t(titleKey);
    document.getElementById("page-sub").textContent = t(subKey);
    const view = document.getElementById("view");
    const page = window.Pages[route];
    view.innerHTML = UI.skeleton(5);
    try {
      page.render(view);
    } catch (e) {
      view.innerHTML = `<div class="card"><div class="callout danger"><strong>Something went wrong rendering this page</strong>
        ${UI.esc(e.message)}</div></div>`;
      console.error(e);
    }
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
};

/* expose for console debugging and for the automated UI smoke test */
window.App = App;

document.addEventListener("DOMContentLoaded", () => App.boot());
