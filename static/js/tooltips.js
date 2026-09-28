// Shared tap-to-show hints for calculator `.tip` ("?") marks.
// Loaded as a classic deferred script on calculator pages. One file fixes every
// calculator at once: autonomo, property-buying-cost and electricity (including
// provider cards rendered dynamically — everything works through delegation,
// so no per-calculator wiring is needed).
//
// Behaviour:
// - Tap/click a "?" → custom popover with the hint text (taken from `title`).
//   Tap the same "?" again, tap anywhere else, or press Esc → closes.
// - Only one popover open at a time (single shared element).
// - Desktop hover is untouched: `title` stays, native tooltips keep working.
// - Accessibility: tips become focusable buttons (role/tabindex/aria-expanded),
//   the popover has role="status", the open trigger gets aria-describedby.
(function () {
  'use strict';

  var POP_ID = 'tip-pop';
  var MARGIN = 8;

  var pop = null;
  var current = null;

  function ensurePop() {
    if (pop) return pop;
    pop = document.createElement('div');
    pop.id = POP_ID;
    pop.className = 'tip-pop';
    pop.setAttribute('role', 'status');
    pop.hidden = true;
    document.body.appendChild(pop);
    // Tapping the popover itself dismisses it (it may cover its own trigger).
    pop.addEventListener('click', function () { close(); });
    return pop;
  }

  function textFor(el) {
    return (el.getAttribute && (el.getAttribute('data-tip') || el.getAttribute('title'))) || '';
  }

  function enhance(el) {
    if (!el || el._tipEnhanced) return;
    el._tipEnhanced = true;
    el.setAttribute('tabindex', '0');
    el.setAttribute('role', 'button');
    el.setAttribute('aria-expanded', 'false');
    if (!el.getAttribute('aria-label')) el.setAttribute('aria-label', 'Show hint');
  }

  function findTip(node) {
    if (!node || !node.closest) return null;
    var t = node.closest('.calc .tip');
    return t;
  }

  function place() {
    if (!current || !pop) return;
    var r = current.getBoundingClientRect();
    var pw = pop.offsetWidth;
    var ph = pop.offsetHeight;
    var vw = window.innerWidth;
    var vh = window.innerHeight;
    // Prefer below the mark, fall back above when there is no room.
    var top = r.bottom + MARGIN;
    if (top + ph > vh - MARGIN) top = r.top - ph - MARGIN;
    if (top < MARGIN) top = MARGIN;
    // Centre on the mark, clamped so the popover never leaves the screen.
    var left = r.left + r.width / 2 - pw / 2;
    left = Math.max(MARGIN, Math.min(left, vw - pw - MARGIN));
    if (vw - pw - MARGIN < MARGIN) left = MARGIN;
    pop.style.top = Math.round(top) + 'px';
    pop.style.left = Math.round(left) + 'px';
  }

  function open(el) {
    var text = textFor(el);
    if (!text) return;
    enhance(el);
    close();
    ensurePop();
    pop.textContent = text;
    pop.hidden = false;
    current = el;
    el.classList.add('on');
    el.setAttribute('aria-expanded', 'true');
    el.setAttribute('aria-describedby', POP_ID);
    place();
  }

  function close() {
    if (!current) return;
    current.classList.remove('on');
    current.setAttribute('aria-expanded', 'false');
    current.removeAttribute('aria-describedby');
    current = null;
    if (pop) pop.hidden = true;
  }

  function toggle(el) {
    if (current === el) close();
    else open(el);
  }

  function init() {
    // Upgrade server-rendered marks for keyboard/screen-reader users.
    // Dynamically added marks (electricity provider cards) are upgraded
    // lazily on first interaction — no observer or re-init needed.
    var tips = document.querySelectorAll('.calc .tip');
    for (var i = 0; i < tips.length; i++) enhance(tips[i]);

    document.addEventListener('click', function (e) {
      var t = findTip(e.target);
      if (t) {
        // The mark may sit inside a <label>: don't steal focus into the input.
        e.preventDefault();
        toggle(t);
        return;
      }
      if (pop && !pop.hidden && !pop.contains(e.target)) close();
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        if (current) {
          var el = current;
          close();
          if (el.focus) el.focus();
        }
        return;
      }
      if (e.key === 'Enter' || e.key === ' ') {
        var t = findTip(e.target);
        if (t) {
          e.preventDefault();
          toggle(t);
        }
      }
    });

    // Keep the popover glued to its mark; never let it drift off-screen.
    window.addEventListener('scroll', function () { if (current) place(); }, { passive: true });
    window.addEventListener('resize', function () { if (current) place(); });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
