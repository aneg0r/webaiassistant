/**
 * Survey choice buttons for chat UIs.
 * Expects API: { reply, buttons: [{ label, value }, ...] }
 */
(function (global) {
  "use strict";

  function normalizeButtons(raw) {
    if (!raw || !Array.isArray(raw)) return [];
    var out = [];
    for (var i = 0; i < raw.length; i++) {
      var b = raw[i];
      if (!b || typeof b !== "object") continue;
      var label = b.label != null ? String(b.label).trim() : "";
      var value = b.value != null ? String(b.value).trim() : "";
      if (!label) continue;
      if (!value) value = label;
      out.push({ label: label, value: value });
    }
    return out;
  }

  /**
   * @param {HTMLElement} container
   * @param {Array<{label:string,value:string}>} buttons
   * @param {{ interactive?: boolean, onSelect?: function(string,string) }} options
   */
  function appendChoiceButtons(container, buttons, options) {
    options = options || {};
    var list = normalizeButtons(buttons);
    if (!list.length || !container) return null;

    var wrap = document.createElement("div");
    wrap.className = "ixchat-choice-buttons";
    wrap.setAttribute("role", "group");
    wrap.setAttribute("aria-label", "Choices");

    var interactive = options.interactive !== false;

    list.forEach(function (btn) {
      var el = document.createElement("button");
      el.type = "button";
      el.className = "ixchat-choice-btn";
      el.textContent = btn.label;
      el.setAttribute("data-value", btn.value);
      if (!interactive) {
        el.disabled = true;
      } else if (typeof options.onSelect === "function") {
        el.addEventListener("click", function () {
          var siblings = wrap.querySelectorAll(".ixchat-choice-btn");
          for (var j = 0; j < siblings.length; j++) {
            siblings[j].disabled = true;
          }
          options.onSelect(btn.value, btn.label);
        });
      }
      wrap.appendChild(el);
    });

    container.appendChild(wrap);
    return wrap;
  }

  function disableChoiceButtons(container) {
    if (!container) return;
    var nodes = container.querySelectorAll(".ixchat-choice-btn");
    for (var i = 0; i < nodes.length; i++) {
      nodes[i].disabled = true;
    }
  }

  global.ChatAgentUI = {
    normalizeButtons: normalizeButtons,
    appendChoiceButtons: appendChoiceButtons,
    disableChoiceButtons: disableChoiceButtons,
  };
})(typeof window !== "undefined" ? window : this);
