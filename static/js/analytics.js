// Shared analytics gates for static/js modules AND the inline module on the
// quiz-success pages. Three copies of this logic used to live side by side:
//   * subscribe-form.js  → isLocalHostname() + the flag check in trackSubscribe()
//   * quiz.js            → local isLocal() + the flag check in track()
//   * quiz-success.html  → the analyticsLocal IIFE (flag || hostname probe)
// Keep exactly one copy here so the gates can never drift apart.

// Second line of defence (after the build-time window.SPANIFIED_ANALYTICS
// flag rendered by templates/base.html): a dist/ output opened locally still
// has the GA4/Meta snippets inlined, so never send events from a local origin
// (localhost / 127.x / 0.0.0.0 / [::1] / file:) or from a broken location.
export function isLocalHostname() {
  try {
    const loc = window.location
    if (!loc || loc.protocol === 'file:') return true
    const host = (loc.hostname || '').toLowerCase()
    if (!host) return true
    return /^(localhost$|127(\.\d+){0,3}$|0\.0\.0\.0$|\[::1\]$)/.test(host)
  } catch { return true }
}

// The one guard every tracker runs: build-time flag first (false on local
// builds → no events, no hostname sniffing needed), then the hostname probe
// as fallback. Never throws, so a broken location can't trip page fallbacks.
export function isAnalyticsEnabled() {
  try {
    if (typeof window === 'undefined') return false
    // Build-time flag (templates/base.html, always rendered).
    if (window.SPANIFIED_ANALYTICS === false) return false
    return !isLocalHostname()
  } catch { return false }
}

// Thin GA4 wrapper: same flag → hostname → gtag-present chain everywhere.
export function trackEvent(name, params = {}) {
  try {
    if (!isAnalyticsEnabled()) return
    if (typeof window.gtag === 'function') window.gtag('event', name, params)
  } catch { /* analytics must never break the page */ }
}

// Thin Meta Pixel wrapper ('Lead', 'CompleteRegistration', …): best-effort,
// fbq queues internally.
export function trackPixel(name, params = {}) {
  try {
    if (!isAnalyticsEnabled()) return
    if (typeof window.fbq === 'function') window.fbq('track', name, params)
  } catch { /* analytics must never break the page */ }
}
