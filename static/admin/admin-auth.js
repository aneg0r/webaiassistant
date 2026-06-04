/**
 * Admin API fetch: sends session Bearer (ADMIN_TOKEN) + browser Basic (nginx / same-origin).
 * Token stored in sessionStorage after first 401 or via AdminAuth.setToken().
 */
(function (global) {
  const STORAGE_KEY = "webaiassistant_admin_token";

  function getToken() {
    return (global.sessionStorage && sessionStorage.getItem(STORAGE_KEY)) || "";
  }

  function setToken(value) {
    if (!global.sessionStorage) return;
    const v = (value || "").trim();
    if (v) sessionStorage.setItem(STORAGE_KEY, v);
    else sessionStorage.removeItem(STORAGE_KEY);
  }

  function authHeaders() {
    const t = getToken();
    if (!t) return {};
    // X-Admin-Token keeps nginx/browser Basic in Authorization intact.
    return { "X-Admin-Token": t };
  }

  async function adminFetch(url, options) {
    const opts = Object.assign({ credentials: "same-origin" }, options || {});
    opts.headers = Object.assign({}, opts.headers || {}, authHeaders());
    let response = await fetch(url, opts);
    if (response.status === 401 && !getToken()) {
      const entered = global.prompt(
        "Token admin requis (valeur de ADMIN_TOKEN dans .env), en plus du login :"
      );
      if (entered && entered.trim()) {
        setToken(entered.trim());
        opts.headers = Object.assign({}, opts.headers || {}, authHeaders());
        response = await fetch(url, opts);
      }
    }
    return response;
  }

  global.AdminAuth = {
    fetch: adminFetch,
    getToken: getToken,
    setToken: setToken,
    clearToken: function () {
      setToken("");
    },
  };
})(typeof window !== "undefined" ? window : globalThis);
