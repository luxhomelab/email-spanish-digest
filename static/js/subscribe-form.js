// AJAX submit for the native Listmonk subscribe form.
// The form itself is a plain native POST (method=post, urlencoded, action =
// Listmonk public API via a Cloudflare Worker that verifies the Turnstile
// token). When this module loads it intercepts submits on
// [data-subscribe-ajax] and POSTs the same fields via fetch so the browser
// stays on-site: HTTP 200 → redirect to the `next` field (/confirm,
// quiz-subscribed); error → inline message; Turnstile widget reset for retry.
// Without JS the native navigation still works (Listmonk/Worker response page).

const DEFAULT_ERROR = 'Something went wrong. Please try again.'

import { markSubscribed } from './subscription-store.js'

// Captcha is baked at build time: prod forms carry data-captcha="1",
// local builds (direct to the dev Listmonk, no Worker) carry "0".
// Absent attribute defaults to required — fail closed.
function captchaRequired(form) {
  return form.dataset.captcha !== '0'
}

// Any successful subscription counts site-wide (generic flag for quiz unlock).
function rememberSubscription(email) {
  try {
    if (typeof window !== 'undefined' && window.localStorage) {
      markSubscribed(window.localStorage, email || '')
    }
  } catch { /* private mode etc. — redirect still works */ }
}

export function errorMessage(bodyText, status = 0, fallback = DEFAULT_ERROR) {
  if (status === 403) return 'Captcha verification failed. Please try again.'
  try {
    const data = JSON.parse(bodyText)
    if (data && typeof data.message === 'string' && data.message.trim()) {
      return data.message.trim()
    }
  } catch { /* non-JSON body */ }
  return fallback
}

// Collect named fields (email, l, next, nonce honeypot, consent,
// cf-turnstile-response injected by the widget) into a plain object.
export function collectFields(form) {
  const fields = {}
  for (const el of form.querySelectorAll('[name]')) {
    if (!el.name || el.disabled) continue
    if (el.type === 'checkbox' && !el.checked) continue
    if (el.type === 'submit') continue
    fields[el.name] = el.value
  }
  return fields
}

// Second line of defence (after the build-time {% if analytics_enabled %}
// gate in templates/base.html): a dist/ output opened locally still has the
// snippets inlined, so never send events from a local origin.
export function isLocalHostname() {
  try {
    const loc = window.location
    if (!loc || loc.protocol === 'file:') return true
    const host = (loc.hostname || '').toLowerCase()
    if (!host) return true
    return /^(localhost$|127(\.\d+){0,3}$|0\.0\.0\.0$|\[::1\]$)/.test(host)
  } catch { return true }
}

// Fire a subscribe GA4 event (and the matching Meta Pixel 'Lead') before the
// redirect. GA4 transport_type 'beacon' lets the hit survive
// window.location.assign(); fbq queues internally and is best-effort. Quiz
// forms redirect to /quiz/<slug>-subscribed — slug is parsed from `next`;
// plain site forms get the generic 'subscribe' event with quiz:'site'.
export function trackSubscribe(fields) {
  try {
    if (typeof window === 'undefined') return
    if (isLocalHostname()) return
    const next = fields.next || ''
    const isQuiz = next.indexOf('/quiz/') !== -1
    let slug = 'site'
    const m = /\/quiz\/([^/?#]+)/.exec(next)
    if (m) slug = m[1].replace(/-subscribed$/, '')
    if (typeof window.gtag === 'function') {
      window.gtag('event', isQuiz ? 'quiz_subscribe' : 'subscribe', {
        transport_type: 'beacon',
        method: 'post',
        quiz: slug,
      })
    }
    // Meta Pixel: same 'Lead' for both form kinds; content_name carries the
    // quiz slug, or 'site' for the plain site form.
    if (typeof window.fbq === 'function') {
      window.fbq('track', 'Lead', { content_name: slug })
    }
  } catch { /* analytics must never break the redirect */ }
}

export async function postForm(action, fields) {
  const res = await fetch(action, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams(fields).toString(),
  })
  if (res.ok) return { ok: true }
  const text = await res.text().catch(() => '')
  return { ok: false, status: res.status, message: errorMessage(text, res.status) }
}

export function initSubscribeForm(form) {
  if (form.dataset.subscribeBound) return
  form.dataset.subscribeBound = '1'

  const errorEl = form.querySelector('[data-subscribe-error]')
  const button = form.querySelector('[type="submit"]')

  const showError = msg => {
    if (!errorEl) return
    errorEl.textContent = msg
    errorEl.hidden = false
  }

  form.addEventListener('submit', async e => {
    e.preventDefault()
    if (errorEl) { errorEl.textContent = ''; errorEl.hidden = true }

    const fields = collectFields(form)

    // Honeypot: bots fill the invisible field; mimic success without sending.
    if (fields.nonce && fields.nonce.trim() !== '') {
      window.location.assign(fields.next || '/confirm')
      return
    }

    // Turnstile: the widget injects cf-turnstile-response. No token → the
    // Worker would 403 anyway; stop early with an inline error.
    // Skipped on local builds (no captcha rendered, direct to Listmonk).
    if (captchaRequired(form) && (!fields['cf-turnstile-response'] || !fields['cf-turnstile-response'].trim())) {
      return showError('Please complete the captcha to subscribe.')
    }

    const originalLabel = button ? button.textContent : ''
    if (button) { button.disabled = true; button.textContent = 'Subscribing…' }
    try {
      const res = await postForm(form.action, fields)
      if (res.ok) {
        rememberSubscription(fields.email)
        trackSubscribe(fields)
        window.location.assign(fields.next || '/confirm')
        return
      }
      showError(res.message)
    } catch {
      showError('Network error — check your connection and try again.')
    } finally {
      if (button) { button.disabled = false; button.textContent = originalLabel }
      // Turnstile tokens are single-use: reset the widget after every
      // attempt so a retry gets a fresh token.
      try {
        if (typeof window !== 'undefined' && window.turnstile) window.turnstile.reset()
      } catch { /* widget not rendered (e.g. tests) */ }
    }
  })
}

if (typeof document !== 'undefined') {
  for (const form of document.querySelectorAll('[data-subscribe-ajax]')) initSubscribeForm(form)
}
