/**
 * Social-proof live updater for r/SpainDaily subscriber count.
 *
 * Threads (threads.com/@spaindaily) has no public API and no CORS-friendly
 * endpoint — the number is baked into the HTML at build time and never
 * updated by this script.
 *
 * Reddit provides a public JSON endpoint at
 *   https://www.reddit.com/r/SpainDaily/about.json
 * which returns { data: { subscribers: N } }.  We fetch it client-side and
 * replace the static badge value so visitors always see the latest count.
 */
(function () {
  "use strict";

  function formatCount(n) {
    if (n >= 1000) {
      var k = n / 1000;
      // One decimal, strip trailing ".0"
      var s = k.toFixed(1).replace(/\.0$/, "");
      return s + "K";
    }
    return String(n);
  }

  document.addEventListener("DOMContentLoaded", function () {
    var controller = new AbortController();
    var timeoutId = setTimeout(function () { controller.abort(); }, 8000);

    fetch("https://www.reddit.com/r/SpainDaily/about.json", {
      signal: controller.signal,
    })
      .then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(function (json) {
        var n = json && json.data && json.data.subscribers;
        if (typeof n !== "number") return;
        var text = formatCount(n);
        var nodes = document.querySelectorAll('[data-live="reddit"]');
        for (var i = 0; i < nodes.length; i++) {
          nodes[i].textContent = text;
        }
      })
      .catch(function () {
        // Silently keep the build-time values.
      })
      .finally(function () {
        clearTimeout(timeoutId);
      });
  });
})();
