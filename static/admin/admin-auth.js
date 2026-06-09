/**
 * Admin API fetch: explicitly sets Authorization: Basic header on every request.
 * Chrome 87+ and Firefox no longer forward cached Basic-auth credentials in
 * fetch() calls. Credentials are stored in sessionStorage and injected on every
 * request. No window.prompt() — the page provides a proper login form instead.
 */
(function (global) {
  const BASIC_KEY = "webaiassistant_admin_basic";
  const TOKEN_KEY = "webaiassistant_admin_token";

  function ss() { return global.sessionStorage || null; }

  function getBasic() { return (ss() && ss().getItem(BASIC_KEY)) || ""; }
  function getToken() { return (ss() && ss().getItem(TOKEN_KEY)) || ""; }

  function setBasic(user, pass) {
    if (!ss()) return;
    if (user && pass != null) {
      const b64 = global.btoa(unescape(encodeURIComponent(user + ":" + pass)));
      ss().setItem(BASIC_KEY, b64);
    } else {
      ss().removeItem(BASIC_KEY);
    }
  }

  function setToken(value) {
    if (!ss()) return;
    const v = (value || "").trim();
    if (v) ss().setItem(TOKEN_KEY, v);
    else ss().removeItem(TOKEN_KEY);
  }

  function authHeaders() {
    const h = {};
    const b = getBasic();
    if (b) h["Authorization"] = "Basic " + b;
    const t = getToken();
    if (t) h["X-Admin-Token"] = t;
    return h;
  }

  async function adminFetch(url, options) {
    const opts = Object.assign({ credentials: "same-origin" }, options || {});
    opts.headers = Object.assign({}, opts.headers || {}, authHeaders());
    const response = await fetch(url, opts);
    if (response.status === 401) {
      // Clear wrong credentials so the login form shows fresh.
      if (ss()) ss().removeItem(BASIC_KEY);
    }
    return response;
  }

  global.AdminAuth = {
    fetch: adminFetch,
    getToken,
    setToken,
    clearToken: function () { setToken(""); },
    getBasic,
    setBasic,
    clearBasic: function () { if (ss()) ss().removeItem(BASIC_KEY); },
  };
})(typeof window !== "undefined" ? window : globalThis);
