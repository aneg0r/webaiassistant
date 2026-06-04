/**
 * Embeddable chat + page feedback widgets.
 * Chat: window.CHAT_API_URL, window.CHAT_WELCOME_TEXT — requires /static/agent.js (ChatAgentUI).
 * Feedback: window.FEEDBACK_PAGE_API_URL, #ixfeedback-widget-root — POST /agent/feedback-page.
 */
(function (global) {
  "use strict";

  var API_URL = global.CHAT_API_URL || "/agent/prompt";
  var FETCH_MS = 28000;
  var POLL_MS = 5000;
  var MAX_HISTORY_MESSAGES = 20;
  var WELCOME_TEXT =
    global.CHAT_WELCOME_TEXT || "Hello. How can I help you?";

  function initWidget() {
    var ui = global.ChatAgentUI;
    var root = document.getElementById("ixchat-widget-root");
    var panel = document.getElementById("ixchat-widget-panel");
    var toggle = document.getElementById("ixchat-widget-toggle");
    var closeBtn = document.getElementById("ixchat-widget-close");
    if (!root || !panel || !toggle) return;

    function setOpen(open) {
      root.setAttribute("data-open", open ? "true" : "false");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      panel.setAttribute("aria-hidden", open ? "false" : "true");
      if (open) {
        var inp = document.getElementById("ixchat-input");
        if (inp) setTimeout(function () { inp.focus(); }, 320);
      }
    }

    toggle.addEventListener("click", function () {
      setOpen(root.getAttribute("data-open") !== "true");
    });
    if (closeBtn) {
      closeBtn.addEventListener("click", function () { setOpen(false); });
    }
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && root.getAttribute("data-open") === "true") {
        setOpen(false);
        toggle.focus();
      }
    });

    var box = document.getElementById("ixchat-messages");
    var form = document.getElementById("ixchat-form");
    var input = document.getElementById("ixchat-input");
    var btn = document.getElementById("ixchat-send");
    if (!box || !form || !input || !btn) return;

    var serverSyncedCount = 0;
    var fetchInFlight = false;
    var welcomeActive = true;
    var conversationHistory = [];
    var activeChoiceMessageEl = null;

    function generateSessionId() {
      if (typeof crypto !== "undefined" && crypto.randomUUID) {
        return crypto.randomUUID();
      }
      return "s" + Date.now().toString(36) + Math.random().toString(36).slice(2, 14);
    }

    var sessionId = localStorage.getItem("sessionId");
    if (!sessionId) {
      sessionId = generateSessionId();
      localStorage.setItem("sessionId", sessionId);
    }

    function formatTime(ts) {
      var d = ts != null ? new Date(ts) : new Date();
      return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    }

    function disableActiveChoiceButtons() {
      if (activeChoiceMessageEl && ui && ui.disableChoiceButtons) {
        ui.disableChoiceButtons(activeChoiceMessageEl);
      }
      activeChoiceMessageEl = null;
    }

    /**
     * @param {string} text
     * @param {boolean} isUser
     * @param {number} timestamp
     * @param {{ human?: boolean, prenom?: string, buttons?: Array, interactiveButtons?: boolean, onButtonSelect?: function }} [opts]
     */
    function addMessage(text, isUser, timestamp, opts) {
      opts = opts || {};
      var messageDiv = document.createElement("div");
      if (isUser) {
        messageDiv.className = "ixchat-message ixchat-user-message";
      } else if (opts.human) {
        messageDiv.className = "ixchat-message ixchat-human-message";
        var badge = document.createElement("span");
        badge.className = "ixchat-human-badge";
        var pn = opts.prenom && String(opts.prenom).trim();
        badge.textContent = pn ? "Human — " + pn : "Human";
        messageDiv.appendChild(badge);
      } else {
        messageDiv.className = "ixchat-message ixchat-bot-message";
      }
      var textSpan = document.createElement("span");
      textSpan.className = "ixchat-message-text";
      textSpan.textContent = text;
      messageDiv.appendChild(textSpan);

      var buttons = ui ? ui.normalizeButtons(opts.buttons) : [];
      if (!isUser && buttons.length && ui) {
        var interactive = opts.interactiveButtons !== false;
        ui.appendChoiceButtons(messageDiv, buttons, {
          interactive: interactive,
          onSelect: interactive ? opts.onButtonSelect : undefined,
        });
        if (interactive) {
          disableActiveChoiceButtons();
          activeChoiceMessageEl = messageDiv;
        }
      }

      if (timestamp != null) {
        var timeSpan = document.createElement("span");
        timeSpan.className = "ixchat-timestamp";
        timeSpan.textContent = formatTime(timestamp);
        messageDiv.appendChild(timeSpan);
      }
      box.appendChild(messageDiv);
      box.scrollTop = box.scrollHeight;
      return messageDiv;
    }

    function tsFromServerMsg(m) {
      if (m && m.at) {
        var x = Date.parse(m.at);
        if (!isNaN(x)) return x;
      }
      return Date.now();
    }

    function conversationTurnsFromServer(messages) {
      var out = [];
      for (var i = 0; i < messages.length; i++) {
        var m = messages[i];
        if (!m || typeof m.role !== "string") continue;
        var role = m.role.toLowerCase();
        var content = m.content != null ? String(m.content) : "";
        if (role === "user") out.push({ role: "user", content: content });
        else if (role === "assistant") {
          var turn = { role: "assistant", content: content };
          if (m.from_human === true) {
            turn.from_human = true;
            if (m.prenom != null && String(m.prenom).trim()) {
              turn.prenom = String(m.prenom).trim();
            }
          }
          out.push(turn);
        }
      }
      return out.slice(-MAX_HISTORY_MESSAGES);
    }

    function renderOneServerMessage(m, msgIndex, allMessages) {
      if (!m || typeof m.role !== "string") return;
      var role = m.role.toLowerCase();
      var text = m.content != null ? String(m.content) : "";
      var ts = tsFromServerMsg(m);
      if (role === "user") {
        addMessage(text, true, ts);
        return;
      }
      if (role !== "assistant") return;
      var buttons = m.buttons;
      var interactiveButtons =
        Array.isArray(buttons) &&
        buttons.length > 0 &&
        msgIndex === allMessages.length - 1;
      addMessage(text, false, ts, {
        human: m.from_human === true,
        prenom: m.prenom != null ? String(m.prenom).trim() : "",
        buttons: buttons,
        interactiveButtons: interactiveButtons,
        onButtonSelect: interactiveButtons
          ? function (value, label) {
              sendUserTurn(value, label);
            }
          : undefined,
      });
    }

    function pollUrl() {
      return API_URL + "?sessionId=" + encodeURIComponent(sessionId);
    }

    function pollOnce() {
      fetch(pollUrl(), { credentials: "same-origin" })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (!data || !Array.isArray(data.messages)) return;
          var msgs = data.messages;
          if (msgs.length === 0) return;
          if (serverSyncedCount === 0 && msgs.length > 0) {
            box.innerHTML = "";
            welcomeActive = false;
            activeChoiceMessageEl = null;
            for (var j = 0; j < msgs.length; j++) {
              renderOneServerMessage(msgs[j], j, msgs);
            }
            serverSyncedCount = msgs.length;
            conversationHistory = conversationTurnsFromServer(msgs);
            return;
          }
          if (fetchInFlight) return;
          if (msgs.length > serverSyncedCount) {
            for (var k = serverSyncedCount; k < msgs.length; k++) {
              renderOneServerMessage(msgs[k], k, msgs);
            }
            serverSyncedCount = msgs.length;
            conversationHistory = conversationTurnsFromServer(msgs);
          }
        })
        .catch(function () {});
    }

    function applyLocalNewSession() {
      sessionId = generateSessionId();
      localStorage.setItem("sessionId", sessionId);
      serverSyncedCount = 0;
      welcomeActive = true;
      conversationHistory = [];
      activeChoiceMessageEl = null;
      box.innerHTML = "";
      addMessage(WELCOME_TEXT, false, Date.now());
      pollOnce();
    }

    function resetSession() {
      var closingId = sessionId;
      fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: "Closed session",
          sessionId: closingId,
          messages: [],
        }),
        credentials: "same-origin",
        keepalive: true,
      })
        .catch(function () {})
        .finally(applyLocalNewSession);
    }

    var newSessionBtn = document.getElementById("ixchat-widget-new-session");
    if (newSessionBtn) newSessionBtn.addEventListener("click", resetSession);

    addMessage(WELCOME_TEXT, false, Date.now());
    setInterval(pollOnce, POLL_MS);
    pollOnce();

    function detailFromJson(data) {
      if (!data || data.detail === undefined || data.detail === null) return "";
      var d = data.detail;
      if (typeof d === "string") return d;
      try { return JSON.stringify(d); } catch (e) { return String(d); }
    }

    function handleAgentResponse(data, userPrompt, userDisplay) {
      var reply = data && data.reply != null ? String(data.reply) : "";
      var humanLocked = data && data.human_in_charge === true;
      var hasAssistantReply = !humanLocked && reply.trim() !== "";
      var buttons = data && data.buttons;
      if (hasAssistantReply) {
        addMessage(reply, false, Date.now(), {
          buttons: buttons,
          interactiveButtons: true,
          onButtonSelect: function (value, label) {
            sendUserTurn(value, label);
          },
        });
      }
      serverSyncedCount += hasAssistantReply ? 2 : 1;
      conversationHistory.push({ role: "user", content: userPrompt });
      if (hasAssistantReply) {
        conversationHistory.push({ role: "assistant", content: reply });
      }
      if (conversationHistory.length > MAX_HISTORY_MESSAGES) {
        conversationHistory = conversationHistory.slice(-MAX_HISTORY_MESSAGES);
      }
    }

    function sendUserTurn(promptValue, displayLabel) {
      var prompt = (promptValue || "").trim();
      if (!prompt || fetchInFlight) return;
      var shown =
        displayLabel != null && String(displayLabel).trim()
          ? String(displayLabel).trim()
          : prompt;

      if (welcomeActive) {
        welcomeActive = false;
        box.innerHTML = "";
        activeChoiceMessageEl = null;
      }

      disableActiveChoiceButtons();
      addMessage(shown, true, Date.now());
      input.value = "";
      btn.disabled = true;

      var controller = new AbortController();
      var timeoutId = setTimeout(function () { controller.abort(); }, FETCH_MS);
      var prior = conversationHistory.slice(-MAX_HISTORY_MESSAGES);
      fetchInFlight = true;

      fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: prompt, sessionId: sessionId, messages: prior }),
        signal: controller.signal,
      })
        .finally(function () { clearTimeout(timeoutId); })
        .then(function (r) {
          return r.json().then(function (data) {
            if (!r.ok) throw new Error(detailFromJson(data) || "Error " + r.status);
            return data;
          });
        })
        .then(function (data) {
          handleAgentResponse(data, prompt, shown);
        })
        .catch(function (err) {
          var msg =
            err && err.name === "AbortError"
              ? "Timeout (" + FETCH_MS / 1000 + " s)."
              : err && err.message
                ? err.message
                : String(err);
          addMessage("Error: " + msg, false, Date.now());
        })
        .finally(function () {
          fetchInFlight = false;
          btn.disabled = false;
          input.focus();
        });
    }

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var t = (input.value || "").trim();
      if (!t) return;
      sendUserTurn(t, t);
    });

    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        form.requestSubmit();
      }
    });
  }

  var FEEDBACK_API_URL = global.FEEDBACK_PAGE_API_URL || "/agent/feedback-page";
  var FEEDBACK_STORAGE_KEY = "ixfeedback_session_id";

  function feedbackSessionId() {
    try {
      var sid = localStorage.getItem(FEEDBACK_STORAGE_KEY);
      if (!sid) {
        sid = "fb-" + Math.random().toString(36).slice(2, 12) + Date.now().toString(36);
        localStorage.setItem(FEEDBACK_STORAGE_KEY, sid);
      }
      return sid;
    } catch (e) {
      return null;
    }
  }

  function feedbackPagePath() {
    return global.location.pathname + global.location.search + global.location.hash;
  }

  function initFeedbackWidget() {
    var root = document.getElementById("ixfeedback-widget-root");
    if (!root) return;

    root.setAttribute("data-open", "false");
    root.className = "feedback-widget-root";
    root.innerHTML =
      '<button type="button" class="feedback-widget-tab" id="ixfeedback-tab" aria-expanded="false" aria-controls="ixfeedback-modal">' +
      '  <span class="feedback-widget-tab-chevron" aria-hidden="true">' +
      '    <svg width="10" height="16" viewBox="0 0 10 16" fill="none" xmlns="http://www.w3.org/2000/svg">' +
      '      <path d="M8 2L2 8L8 14" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>' +
      "    </svg>" +
      "  </span>" +
      '  <span class="feedback-widget-tab-label">Donnez votre avis</span>' +
      "</button>" +
      '<div class="feedback-widget-overlay" id="ixfeedback-overlay" hidden></div>' +
      '<div class="feedback-widget-modal" id="ixfeedback-modal" role="dialog" aria-modal="true" aria-labelledby="ixfeedback-title" hidden>' +
      '  <div class="feedback-widget-header">' +
      '    <h2 id="ixfeedback-title">Votre avis nous intéresse</h2>' +
      '    <button type="button" class="feedback-widget-close" id="ixfeedback-close" aria-label="Fermer">' +
      "      Fermer <span aria-hidden=\"true\">×</span>" +
      "    </button>" +
      "  </div>" +
      '  <div class="feedback-widget-body">' +
      '    <div class="feedback-widget-step" data-step="scope">' +
      "      <h3>Partagez vos commentaires</h3>" +
      '      <p class="feedback-widget-hint">Ce formulaire est directement connecté au chat : utilisez le même outil pour les feedbacks et le chat ! Simplifier votre système d\'information.</p>' +
      '      <button type="button" class="feedback-widget-scope-btn" data-scope="product">' +
      "        Avis sur le produit" +
      '        <span class="feedback-widget-arrow" aria-hidden="true">›</span>' +
      "      </button>" +
      '      <button type="button" class="feedback-widget-scope-btn" data-scope="site">' +
      "        Avis sur le site web" +
      '        <span class="feedback-widget-arrow" aria-hidden="true">›</span>' +
      "      </button>" +
      '      <button type="button" class="feedback-widget-scope-btn" data-scope="page">' +
      "        Avis sur cette page" +
      '        <span class="feedback-widget-arrow" aria-hidden="true">›</span>' +
      "      </button>" +
      "    </div>" +
      '    <div class="feedback-widget-step" data-step="rating" hidden>' +
      "      <h3>Quelle est votre expérience ?</h3>" +
      '      <p class="feedback-widget-hint" id="ixfeedback-scope-label"></p>' +
      '      <div class="feedback-widget-stars" role="group" aria-label="Note de 1 à 5 étoiles" id="ixfeedback-stars"></div>' +
      '      <div class="feedback-widget-comment">' +
      '        <label for="ixfeedback-comment">Commentaire (facultatif)</label>' +
      '        <textarea id="ixfeedback-comment" maxlength="2000" placeholder="Précisez ce qui vous a plu ou déplu…"></textarea>' +
      "      </div>" +
      '      <div class="feedback-widget-actions">' +
      '        <button type="button" class="feedback-widget-btn-secondary" id="ixfeedback-back">Retour</button>' +
      '        <button type="button" class="feedback-widget-btn-primary" id="ixfeedback-submit" disabled>Envoyer</button>' +
      "      </div>" +
      '      <div class="feedback-widget-error" id="ixfeedback-error" hidden></div>' +
      "    </div>" +
      '    <div class="feedback-widget-step" data-step="thanks" hidden>' +
      '      <div class="feedback-widget-thanks">' +
      '        <div class="feedback-widget-thanks-icon" aria-hidden="true">✓</div>' +
      "        <p><strong>Merci !</strong> Votre avis a bien été enregistré.</p>" +
      "      </div>" +
      "    </div>" +
      "  </div>" +
      "</div>";

    var state = { scope: null, notation: 0, open: false };
    var tab = root.querySelector("#ixfeedback-tab");
    var overlay = root.querySelector("#ixfeedback-overlay");
    var modal = root.querySelector("#ixfeedback-modal");
    var closeBtn = root.querySelector("#ixfeedback-close");
    var starsEl = root.querySelector("#ixfeedback-stars");
    var submitBtn = root.querySelector("#ixfeedback-submit");
    var backBtn = root.querySelector("#ixfeedback-back");
    var errEl = root.querySelector("#ixfeedback-error");
    var scopeLabel = root.querySelector("#ixfeedback-scope-label");

    for (var i = 1; i <= 5; i++) {
      (function (n) {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "feedback-widget-star";
        btn.setAttribute("aria-pressed", "false");
        btn.setAttribute("aria-label", n + " étoile" + (n > 1 ? "s" : ""));
        btn.textContent = "★";
        btn.addEventListener("click", function () {
          state.notation = n;
          starsEl.querySelectorAll(".feedback-widget-star").forEach(function (s, idx) {
            var on = idx < n;
            s.setAttribute("aria-pressed", on ? "true" : "false");
            s.classList.toggle("feedback-widget-star--on", on);
          });
          submitBtn.disabled = false;
        });
        starsEl.appendChild(btn);
      })(i);
    }

    function showStep(name) {
      root.querySelectorAll(".feedback-widget-step").forEach(function (el) {
        el.hidden = el.getAttribute("data-step") !== name;
      });
    }

    function setOpen(open) {
      state.open = open;
      root.setAttribute("data-open", open ? "true" : "false");
      tab.setAttribute("aria-expanded", open ? "true" : "false");
      modal.hidden = !open;
      overlay.hidden = !open;
      if (open) {
        showStep(state.scope ? "rating" : "scope");
        closeBtn.focus();
      } else {
        document.body.style.overflow = "";
      }
    }

    function resetForm() {
      state.scope = null;
      state.notation = 0;
      root.querySelector("#ixfeedback-comment").value = "";
      submitBtn.disabled = true;
      errEl.hidden = true;
      starsEl.querySelectorAll(".feedback-widget-star").forEach(function (s) {
        s.setAttribute("aria-pressed", "false");
        s.classList.remove("feedback-widget-star--on");
      });
      showStep("scope");
    }

    tab.addEventListener("click", function () {
      setOpen(!state.open);
      if (state.open) document.body.style.overflow = "hidden";
    });
    overlay.addEventListener("click", function () {
      setOpen(false);
      resetForm();
    });
    closeBtn.addEventListener("click", function () {
      setOpen(false);
      resetForm();
    });

    root.querySelectorAll("[data-scope]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        state.scope = btn.getAttribute("data-scope");
        if (state.scope === "product") {
          scopeLabel.textContent = "Avis sur le produit";
        } else if (state.scope === "site") {
          scopeLabel.textContent = "Avis sur le site web";
        } else {
          scopeLabel.textContent = "Avis sur cette page : " + feedbackPagePath();
        }
        showStep("rating");
      });
    });

    backBtn.addEventListener("click", function () {
      state.notation = 0;
      submitBtn.disabled = true;
      errEl.hidden = true;
      showStep("scope");
    });

    submitBtn.addEventListener("click", function () {
      if (!state.scope || state.notation < 1) return;
      submitBtn.disabled = true;
      errEl.hidden = true;

      var payload = {
        scope: state.scope,
        notation: state.notation,
        remarques: root.querySelector("#ixfeedback-comment").value.trim(),
        sessionId: feedbackSessionId(),
      };
      if (state.scope === "page") {
        payload.page = feedbackPagePath();
      }

      fetch(FEEDBACK_API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify(payload),
      })
        .then(function (res) {
          return res.json().then(function (data) {
            if (!res.ok) {
              var msg = (data && data.detail) || res.statusText || "Erreur";
              throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
            }
            return data;
          });
        })
        .then(function () {
          showStep("thanks");
          setTimeout(function () {
            setOpen(false);
            resetForm();
          }, 2200);
        })
        .catch(function (e) {
          errEl.textContent = e.message || "Envoi impossible. Réessayez plus tard.";
          errEl.hidden = false;
          submitBtn.disabled = false;
        });
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && state.open) {
        setOpen(false);
        resetForm();
      }
    });
  }

  function initAll() {
    initWidget();
    initFeedbackWidget();
  }

  global.ChatWidget = {
    init: initWidget,
    initFeedback: initFeedbackWidget,
    initAll: initAll,
    API_URL: API_URL,
    FEEDBACK_API_URL: FEEDBACK_API_URL,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll);
  } else {
    initAll();
  }
})(typeof window !== "undefined" ? window : this);
