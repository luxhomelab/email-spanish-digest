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

// Second line of defence (after the build-time window.SPANIFIED_ANALYTICS
// flag rendered by templates/base.html): a dist/ output opened locally still
// has the snippets inlined, so never send events from a local origin.
export function isLocalHostname() {
  try {
    const loc = window.location
    if (!loc || loc.protocol === 'file:') return true
    const host = (loc.hostname || '').toLowerCase()
    if (!host) return true
    return /^(localhost$|127(\.\d+){0,3}$|0\.0\.0\.0$|\[::1\]$)/.test(host)
  } catch { return true }
}

// Form families that need their own GA4 event (and their own Meta content_name)
// are tagged in the templates as data-form-kind on the <form> — one distinct
// event per family, no pathname parsing:
//   digest.html                       → digest_subscribe
//   calculator-autonomo.html          → calc_autonomo_lead
//   calculator-property-buying-cost   → calc_property_lead
//   calculator-electricity.html       → calc_electricity_lead
// Forms without the attribute (site/subscribe page, footer) keep 'subscribe';
// quiz forms keep 'quiz_subscribe' (their `next` points at /quiz/…).
const FORM_EVENTS = new Map([
  ['digest', 'digest_subscribe'],
  ['calc-autonomo', 'calc_autonomo_lead'],
  ['calc-property', 'calc_property_lead'],
  ['calc-electricity', 'calc_electricity_lead'],
])

// Fire a subscribe GA4 event (and the matching Meta Pixel 'Lead') before the
// redirect. GA4 transport_type 'beacon' lets the hit survive
// window.location.assign(); fbq queues internally and is best-effort. Quiz
// forms redirect to /quiz/<slug>-subscribed — slug is parsed from `next`;
// plain site forms get the generic 'subscribe' event with quiz:'site'.
// `form` (the submitting <form>) is optional: when it carries data-form-kind
// the distinct digest/calc_* event is used for both GA4 (event name) and Meta
// (Lead content_name), so the two channels stay comparable.
export function trackSubscribe(fields, form) {
  try {
    if (typeof window === 'undefined') return
    // Build-time flag (templates/base.html, always rendered): false on local
    // builds → no events. Primary gate; the hostname check below is fallback.
    if (window.SPANIFIED_ANALYTICS === false) return
    if (isLocalHostname()) return
    const next = fields.next || ''
    const isQuiz = next.indexOf('/quiz/') !== -1
    let slug = 'site'
    const m = /\/quiz\/([^/?#]+)/.exec(next)
    if (m) slug = m[1].replace(/-subscribed$/, '')
    // Known data-form-kind on a non-quiz form → distinct event; otherwise the
    // pre-existing quiz_subscribe / subscribe branches (params unchanged).
    const kind = (form && form.dataset && form.dataset.formKind) || ''
    const kindEvent = !isQuiz ? FORM_EVENTS.get(kind) : undefined
    if (typeof window.gtag === 'function') {
      window.gtag('event', kindEvent || (isQuiz ? 'quiz_subscribe' : 'subscribe'), {
        transport_type: 'beacon',
        method: 'post',
        ...(kindEvent ? { form_kind: kind } : { quiz: slug }),
      })
    }
    // Meta Pixel: always 'Lead'; content_name carries the distinct form name
    // (digest_subscribe / calc_*_lead), or the quiz slug / 'site' otherwise.
    if (typeof window.fbq === 'function') {
      window.fbq('track', 'Lead', { content_name: kindEvent || slug })
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
        trackSubscribe(fields, form)
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
