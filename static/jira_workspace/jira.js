(function () {
  function markActiveNav() {
    var currentPath = window.location.pathname;
    document.querySelectorAll(".nav-link").forEach(function (link) {
      var href = link.getAttribute("href");
      if (!href || href === "#") {
        return;
      }

      if (href === currentPath) {
        link.classList.add("active");
      }
    });
  }

  function stampRailPlaceholders() {
    document.querySelectorAll("[data-rail-empty]").forEach(function (node) {
      node.setAttribute("data-rail-state", "empty");
    });
  }

  function resolveTarget(trigger) {
    var selector = trigger.getAttribute("data-partial-target");
    if (selector) {
      return document.querySelector(selector);
    }
    return document.querySelector("[data-partial-target]");
  }

  async function refreshPartial(trigger) {
    var url = trigger.getAttribute("data-partial-url") || trigger.getAttribute("href");
    var target = resolveTarget(trigger);

    if (!url || !target || url === "#") {
      return;
    }

    trigger.setAttribute("aria-busy", "true");

    try {
      var response = await fetch(url, {
        headers: {
          "X-Requested-With": "XMLHttpRequest"
        }
      });

      if (!response.ok) {
        throw new Error("Partial refresh failed with status " + response.status);
      }

      target.innerHTML = await response.text();
    } catch (error) {
      window.console.error(error);
    } finally {
      trigger.removeAttribute("aria-busy");
    }
  }

  document.addEventListener("click", function (event) {
    var trigger = event.target.closest("[data-partial-trigger]");
    if (!trigger) {
      return;
    }

    event.preventDefault();
    refreshPartial(trigger);
  });

  document.addEventListener("DOMContentLoaded", function () {
    markActiveNav();
    stampRailPlaceholders();
  });
})();
