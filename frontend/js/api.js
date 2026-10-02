/* Thin API client: token handling, JSON, friendly errors, CSV download. */
const Api = (() => {
  const TOKEN_KEY = "ca_token";
  let token = localStorage.getItem(TOKEN_KEY) || null;

  function setToken(tk) {
    token = tk || null;
    if (tk) localStorage.setItem(TOKEN_KEY, tk);
    else localStorage.removeItem(TOKEN_KEY);
  }
  const getToken = () => token;

  class ApiError extends Error {
    constructor(message, status, code, details) {
      super(message);
      this.status = status; this.code = code; this.details = details || [];
    }
  }

  async function request(path, { method = "GET", body, auth = true, raw = false } = {}) {
    const headers = {};
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (auth && token) headers["Authorization"] = "Bearer " + token;

    const res = await fetch(path, {
      method, headers, body: body === undefined ? undefined : JSON.stringify(body)
    });

    if (raw) {
      if (!res.ok) throw new ApiError("Download failed", res.status, "download_failed");
      return res;
    }
    let payload = null;
    const text = await res.text();
    if (text) { try { payload = JSON.parse(text); } catch { payload = { raw: text }; } }

    if (!res.ok) {
      const err = (payload && payload.error) || {};
      if (res.status === 401) {
        // expired / invalid token: drop it so the shell shows the login screen again
        setToken(null);
        window.dispatchEvent(new CustomEvent("ca:unauthorised"));
      }
      throw new ApiError(err.message || `Request failed (${res.status})`, res.status, err.code, err.details);
    }
    return payload;
  }

  const qs = (params) => {
    const p = Object.entries(params || {})
      .filter(([, v]) => v !== undefined && v !== null && v !== "")
      .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`);
    return p.length ? "?" + p.join("&") : "";
  };

  return {
    setToken, getToken, ApiError,
    // auth
    login: (email, password) => request("/api/auth/login", { method: "POST", body: { email, password }, auth: false }),
    register: (payload) => request("/api/auth/register", { method: "POST", body: payload, auth: false }),
    me: () => request("/api/auth/me"),
    updateMe: (payload) => request("/api/auth/me", { method: "PUT", body: payload }),
    users: (params) => request("/api/auth/users" + qs(params)),
    // meta + predict
    meta: () => request("/api/meta", { auth: false }),
    health: () => request("/health", { auth: false }),
    predict: (payload) => request("/api/predict", { method: "POST", body: payload }),
    expansionRules: () => request("/api/expansion-rules", { auth: false }),
    cleaningRules: () => request("/api/cleaning-rules", { auth: false }),
    cropReferencePublic: () => request("/api/crops/reference", { auth: false }),
    // history
    history: (params) => request("/api/history" + qs(params)),
    historySummary: (params) => request("/api/history/summary" + qs(params)),
    historyItem: (id) => request(`/api/history/${id}`),
    savePrediction: (payload) => request("/api/history", { method: "POST", body: payload }),
    updateHistory: (id, payload) => request(`/api/history/${id}`, { method: "PATCH", body: payload }),
    deleteHistory: (id) => request(`/api/history/${id}`, { method: "DELETE" }),
    feedback: (id, payload) => request(`/api/history/${id}/feedback`, { method: "POST", body: payload }),
    // surveys
    surveys: (params) => request("/api/surveys" + qs(params)),
    createSurvey: (payload) => request("/api/surveys", { method: "POST", body: payload }),
    updateSurvey: (id, payload) => request(`/api/surveys/${id}`, { method: "PATCH", body: payload }),
    deleteSurvey: (id) => request(`/api/surveys/${id}`, { method: "DELETE" }),
    reviewSurvey: (id, payload) => request(`/api/surveys/${id}/review`, { method: "POST", body: payload }),
    cleaningReport: () => request("/api/surveys/cleaning-report"),
    // crops
    crops: (params) => request("/api/crops" + qs(params)),
    createCrop: (payload) => request("/api/crops", { method: "POST", body: payload }),
    updateCrop: (id, payload) => request(`/api/crops/${id}`, { method: "PATCH", body: payload }),
    deleteCrop: (id) => request(`/api/crops/${id}`, { method: "DELETE" }),
    importCrops: () => request("/api/crops/import-defaults", { method: "POST" }),
    // model
    metrics: () => request("/api/model/metrics", { auth: false }),
    modelStatus: () => request("/api/model/status", { auth: false }),
    retrain: (payload) => request("/api/model/retrain", { method: "POST", body: payload }),
    retrainStatus: () => request("/api/model/retrain/status", { auth: false }),
    featureImportance: () => request("/api/model/feature-importance", { auth: false }),
    // datasets
    dsSummary: () => request("/api/dataset/secondary/summary", { auth: false }),
    dsRows: (params) => request("/api/dataset/secondary/rows" + qs(params), { auth: false }),
    dsSchema: () => request("/api/dataset/schema", { auth: false }),
    mergedPreview: () => request("/api/dataset/merged/preview"),
    // dashboard
    summary: (params) => request("/api/summary" + qs(params)),
    // downloads (browser handles the file; token passed as query param)
    download: (path, params) => {
      const url = path + qs({ ...(params || {}), token: getToken() });
      const a = document.createElement("a");
      a.href = url; a.rel = "noopener";
      document.body.appendChild(a); a.click(); a.remove();
    }
  };
})();

window.Api = Api;
