// Pure consent-record logic for the cookie banner (cookie-consent.js wires it
// to the DOM; tests/cookie-consent-logic.test.js covers it).
//
// EU rules (ePrivacy art. 5(3), Spain's LSSI art. 22.2, AEPD cookie guide):
// non-essential cookies (Google Analytics, Meta Pixel) may load only after an
// explicit opt-in, rejecting must be as easy as accepting, and the choice can
// be changed or withdrawn at any time. The record itself is strictly
// necessary storage (it remembers the refusal too) and needs no consent.

export const CONSENT_KEY = 'spanified_cookie_consent'
// Bump when the set of categories or vendors changes: everyone is asked again.
export const CONSENT_VERSION = 1
// The AEPD recommends re-asking after at most 24 months; we re-ask after 12.
export const CONSENT_MAX_AGE_MS = 365 * 24 * 60 * 60 * 1000
export const CATEGORIES = ['analytics', 'marketing']

// Choice from raw storage, or null when the visitor must be asked (no record,
// garbage, older version, expired, or a timestamp from the future).
export function parseConsent (raw, now = Date.now()) {
  if (typeof raw !== 'string' || !raw) return null
  let rec
  try { rec = JSON.parse(raw) } catch { return null }
  if (!rec || typeof rec !== 'object') return null
  if (rec.v !== CONSENT_VERSION) return null
  if (typeof rec.ts !== 'number' || !Number.isFinite(rec.ts)) return null
  if (rec.ts > now + 60 * 1000 || now - rec.ts > CONSENT_MAX_AGE_MS) return null
  const choice = {}
  for (const c of CATEGORIES) choice[c] = rec[c] === true
  return choice
}

export function serializeConsent (choice, now = Date.now()) {
  const rec = { v: CONSENT_VERSION, ts: now }
  for (const c of CATEGORIES) rec[c] = !!(choice && choice[c] === true)
  return JSON.stringify(rec)
}

export function allChoice (value) {
  const choice = {}
  for (const c of CATEGORIES) choice[c] = !!value
  return choice
}

// True when a category that was granted is now denied: its scripts are
// already running, so the page must drop their cookies and reload.
export function isWithdrawal (prev, next) {
  if (!prev) return false
  return CATEGORIES.some((c) => prev[c] === true && !(next && next[c] === true))
}

// First-party cookies the vendors set on our domain, to clear on withdrawal.
export function vendorCookieNames (cookieString, choice) {
  const names = String(cookieString || '').split(';')
    .map((p) => p.split('=')[0].trim()).filter(Boolean)
  return names.filter((n) => {
    if (!(choice && choice.analytics) && /^(_ga($|_)|_gid$|_gat($|_))/.test(n)) return true
    if (!(choice && choice.marketing) && /^(_fbp|_fbc)$/.test(n)) return true
    return false
  })
}
