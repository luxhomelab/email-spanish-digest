// Native subscribe form → Listmonk public API.
// Auto-binds every [data-subscribe-form] when loaded as a module
// (subscribe page + quiz gate). Pure helpers exported for unit tests.
//
// Contract (verified live 2026-09-22): POST JSON {email, list_uuids} to
//   https://api.spanified.com/api/public/subscription
//   200 {"data":{"has_optin":true}}  → success (double opt-in email sent)
//   400 {"message":"..."}            → error, message shown inline

const DEFAULT_ERROR = 'Something went wrong. Please try again.'
// Fallback endpoint when the form has no data-endpoint. The real value is
// baked into data-endpoint at build time (build.py --listmonk).
const ENDPOINT = 'https://api.spanified.com/api/public/subscription'

export function subscribePayload(email, listUuid) {
  return { email: email.trim().toLowerCase(), list_uuids: [listUuid] }
}

export function errorMessage(bodyText, fallback = DEFAULT_ERROR) {
  try {
    const data = JSON.parse(bodyText)
    if (data && typeof data.message === 'string' && data.message.trim()) {
      return data.message.trim()
    }
  } catch { /* non-JSON body */ }
  return fallback
}

export async function postSubscription(email, listUuid, endpoint = ENDPOINT) {
  const res = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(subscribePayload(email, listUuid)),
  })
  if (res.ok) return { ok: true }
  const text = await res.text().catch(() => '')
  return { ok: false, message: errorMessage(text) }
}

export function initSubscribeForm(form) {
  if (form.dataset.subscribeBound) return
  form.dataset.subscribeBound = '1'

  const emailInput = form.querySelector('input[name="email"]')
  const consentInput = form.querySelector('input[name="consent"]')
  const hp = form.querySelector('input[name="company"]')
  const errorEl = form.querySelector('[data-subscribe-error]')
  const button = form.querySelector('[type="submit"]')
  const listUuid = form.dataset.listUuid
  const endpoint = form.dataset.endpoint || ENDPOINT
  // Empty data-success-url (quiz gate) → unlock via event, no redirect.
  const successUrl = form.dataset.successUrl || ''
  if (!emailInput || !listUuid) return

  const showError = msg => {
    if (!errorEl) return
    errorEl.textContent = msg
    errorEl.hidden = false
  }

  // Emit a success event instead of redirecting (quiz gate needs to unlock).
  // Must bubble: listeners sit on wrapper divs (e.g. #quiz-gate-form),
  // not on the <form> itself (CustomEvent defaults to bubbles:false).
  const fireSuccess = email => {
    form.dispatchEvent(new CustomEvent('subscription:success', { bubbles: true, detail: { email } }))
  }

  form.addEventListener('submit', async e => {
    e.preventDefault()
    if (errorEl) { errorEl.textContent = ''; errorEl.hidden = true }

    // Honeypot: bots fill the invisible field; humans can't see it. Silent no-op.
    if (hp && hp.value.trim() !== '') return

    const email = emailInput.value.trim()
    if (!email) return showError('Please enter your email address.')
    if (!emailInput.checkValidity()) return showError('Please enter a valid email address.')
    if (consentInput && !consentInput.checked) return showError('Please agree to receive Spain Daily to subscribe.')

    const originalLabel = button ? button.textContent : ''
    if (button) { button.disabled = true; button.textContent = 'Subscribing…' }
    try {
      const res = await postSubscription(email, listUuid, endpoint)
      if (res.ok) {
        if (successUrl) {
          window.location.assign(successUrl)
        } else {
          fireSuccess(email)
        }
        return
      }
      showError(res.message)
    } catch {
      showError('Network error — check your connection and try again.')
    } finally {
      if (button) { button.disabled = false; button.textContent = originalLabel }
    }
  })
}

if (typeof document !== 'undefined') {
  for (const form of document.querySelectorAll('[data-subscribe-form]')) initSubscribeForm(form)
}