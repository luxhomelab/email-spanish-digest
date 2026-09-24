// Site-wide subscription record (no DOM) — testable with node:test.
// Written on ANY successful subscription (subscribe page, any quiz gate,
// quiz-success double-opt-in click) and read to unlock quiz results.
// Storage shape: JSON { subscribed: true, email, at: <ISO timestamp> }.

export const SUBSCRIBED_KEY = 'spanified_subscribed'

export function markSubscribed(storage, email = '') {
  try {
    storage.setItem(SUBSCRIBED_KEY, JSON.stringify({ subscribed: true, email, at: new Date().toISOString() }))
    return true
  } catch {
    return false
  }
}

export function isSubscribed(storage) {
  try {
    const raw = storage.getItem(SUBSCRIBED_KEY)
    if (!raw) return false
    const data = JSON.parse(raw)
    return !!(data && data.subscribed)
  } catch {
    return false
  }
}
