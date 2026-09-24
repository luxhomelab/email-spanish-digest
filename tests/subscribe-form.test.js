import { describe, it, after } from 'node:test'
import assert from 'node:assert/strict'
import { errorMessage, collectFields, postForm, initSubscribeForm } from '../static/js/subscribe-form.js'

// ── errorMessage ────────────────────────────────────────────────────────
describe('errorMessage', () => {
  it('maps HTTP 403 (Worker Turnstile reject) to a captcha message', () => {
    assert.equal(errorMessage('Forbidden', 403), 'Captcha verification failed. Please try again.')
  })
  it('extracts the message from the Listmonk JSON error body', () => {
    assert.equal(
      errorMessage('{"message":"No valid lists selected to subscribe."}', 400),
      'No valid lists selected to subscribe.',
    )
  })
  it('falls back for non-JSON bodies', () => {
    assert.equal(errorMessage('<html>oops</html>', 500), 'Something went wrong. Please try again.')
  })
})

// ── collectFields ───────────────────────────────────────────────────────
describe('collectFields', () => {
  it('picks up named fields, skips unchecked checkboxes and submit buttons', () => {
    const form = {
      querySelectorAll: () => [
        { name: 'email', type: 'email', value: 'a@b.com', disabled: false },
        { name: 'l', type: 'hidden', value: 'list-1', disabled: false },
        { name: 'next', type: 'hidden', value: '/confirm', disabled: false },
        { name: 'nonce', type: 'text', value: '', disabled: false },
        { name: 'consent', type: 'checkbox', value: 'on', checked: true, disabled: false },
        { name: 'cf-turnstile-response', type: 'hidden', value: 'tok-123', disabled: false },
        { name: '', type: 'submit', value: 'Subscribe', disabled: false },
      ],
    }
    assert.deepEqual(collectFields(form), {
      email: 'a@b.com',
      l: 'list-1',
      next: '/confirm',
      nonce: '',
      consent: 'on',
      'cf-turnstile-response': 'tok-123',
    })
  })
})

// ── postForm ────────────────────────────────────────────────────────────
describe('postForm', () => {
  const originalFetch = global.fetch

  it('returns ok on HTTP 200', async () => {
    global.fetch = async () => ({ ok: true })
    const res = await postForm('https://newsletter.spanified.com/api/public/subscription', { email: 'a@b.com' })
    assert.deepEqual(res, { ok: true })
  })

  it('sends urlencoded body with the form fields', async () => {
    let sent = null
    global.fetch = async (url, opts) => {
      sent = { url, opts }
      return { ok: true }
    }
    await postForm('https://newsletter.spanified.com/api/public/subscription', {
      email: 'a@b.com', l: 'list-1', 'cf-turnstile-response': 'tok-123',
    })
    assert.equal(sent.url, 'https://newsletter.spanified.com/api/public/subscription')
    assert.equal(sent.opts.method, 'POST')
    assert.equal(sent.opts.headers['Content-Type'], 'application/x-www-form-urlencoded')
    const body = new URLSearchParams(sent.opts.body)
    assert.equal(body.get('email'), 'a@b.com')
    assert.equal(body.get('l'), 'list-1')
    assert.equal(body.get('cf-turnstile-response'), 'tok-123')
  })

  it('returns the API message on HTTP 400', async () => {
    global.fetch = async () => ({ ok: false, status: 400, text: async () => '{"message":"Invalid email"}' })
    const res = await postForm('https://x.test/sub', {})
    assert.deepEqual(res, { ok: false, status: 400, message: 'Invalid email' })
  })

  it('maps HTTP 403 to the captcha message', async () => {
    global.fetch = async () => ({ ok: false, status: 403, text: async () => 'Forbidden' })
    const res = await postForm('https://x.test/sub', {})
    assert.equal(res.ok, false)
    assert.match(res.message, /Captcha verification failed/)
  })

  after(() => { global.fetch = originalFetch })
})

// ── initSubscribeForm ───────────────────────────────────────────────────
describe('initSubscribeForm', () => {
  const originalFetch = global.fetch
  const originalWindow = global.window

  function fakeInputs({ token = 'tok-123', nonce = '', next = '/confirm' } = {}) {
    return [
      { name: 'email', type: 'email', value: 'a@b.com', disabled: false },
      { name: 'l', type: 'hidden', value: 'list-1', disabled: false },
      { name: 'next', type: 'hidden', value: next, disabled: false },
      { name: 'nonce', type: 'text', value: nonce, disabled: false },
      { name: 'cf-turnstile-response', type: 'hidden', value: token, disabled: false },
    ]
  }

  function fakeForm({ next = '/confirm', token = 'tok-123', nonce = '', captcha = '1' } = {}) {
    const handlers = {}
    const errorEl = { textContent: '', hidden: true }
    const form = {
      action: 'https://newsletter.spanified.com/api/public/subscription',
      dataset: { captcha },
      querySelectorAll: () => fakeInputs({ token, nonce, next }),
      querySelector: sel => {
        if (sel === '[data-subscribe-error]') return errorEl
        if (sel === '[type="submit"]') return { disabled: false, textContent: 'Subscribe' }
        return null
      },
      addEventListener: (name, fn) => { handlers[name] = fn },
    }
    return { form, handlers, errorEl }
  }

  it('redirects to `next` on success (subscribe page → /confirm)', async () => {
    let assigned = null
    global.fetch = async () => ({ ok: true })
    global.window = { location: { assign: url => { assigned = url } } }
    const { form, handlers } = fakeForm({ next: '/confirm' })
    initSubscribeForm(form)
    await handlers.submit({ preventDefault: () => {} })
    assert.equal(assigned, '/confirm')
  })

  it('redirects to the quiz-subscribed page on success (quiz gate)', async () => {
    let assigned = null
    global.fetch = async () => ({ ok: true })
    global.window = { location: { assign: url => { assigned = url } } }
    const { form, handlers } = fakeForm({ next: 'https://spanified.com/quiz/ai-or-real-subscribed' })
    initSubscribeForm(form)
    await handlers.submit({ preventDefault: () => {} })
    assert.equal(assigned, 'https://spanified.com/quiz/ai-or-real-subscribed')
  })

  it('shows an inline error and redirects nowhere on API failure', async () => {
    let assigned = null
    global.fetch = async () => ({ ok: false, status: 400, text: async () => '{"message":"Invalid email"}' })
    global.window = { location: { assign: url => { assigned = url } } }
    const { form, handlers, errorEl } = fakeForm()
    initSubscribeForm(form)
    await handlers.submit({ preventDefault: () => {} })
    assert.equal(assigned, null)
    assert.equal(errorEl.hidden, false)
    assert.equal(errorEl.textContent, 'Invalid email')
  })

  it('blocks submit with an inline error when the captcha token is missing (no fetch)', async () => {
    let fetched = false
    global.fetch = async () => { fetched = true; return { ok: true } }
    global.window = { location: { assign: () => { throw new Error('must not redirect') } } }
    const { form, handlers, errorEl } = fakeForm({ token: '' })
    initSubscribeForm(form)
    await handlers.submit({ preventDefault: () => {} })
    assert.equal(fetched, false)
    assert.equal(errorEl.hidden, false)
    assert.match(errorEl.textContent, /captcha/)
  })

  it('mimics success without fetch when the honeypot is filled', async () => {
    let fetched = false
    let assigned = null
    global.fetch = async () => { fetched = true; return { ok: true } }
    global.window = { location: { assign: url => { assigned = url } } }
    const { form, handlers, errorEl } = fakeForm({ nonce: 'bot' })
    initSubscribeForm(form)
    await handlers.submit({ preventDefault: () => {} })
    assert.equal(fetched, false)
    assert.equal(assigned, '/confirm')
    assert.equal(errorEl.hidden, true)
  })

  it('skips the captcha check on local builds (data-captcha="0", no token)', async () => {
    let fetched = false
    let assigned = null
    global.fetch = async () => { fetched = true; return { ok: true } }
    global.window = { location: { assign: url => { assigned = url } } }
    const { form, handlers, errorEl } = fakeForm({ token: '', captcha: '0' })
    initSubscribeForm(form)
    await handlers.submit({ preventDefault: () => {} })
    assert.equal(fetched, true)
    assert.equal(assigned, '/confirm')
    assert.equal(errorEl.hidden, true)
  })

  it('writes the site-wide subscribed flag on success (any form unlocks quizzes)', async () => {
    let assigned = null
    const store = new Map()
    global.fetch = async () => ({ ok: true })
    global.window = {
      location: { assign: url => { assigned = url } },
      localStorage: { getItem: k => store.get(k) ?? null, setItem: (k, v) => { store.set(k, v) } },
    }
    const { form, handlers } = fakeForm({ next: '/confirm' })
    initSubscribeForm(form)
    await handlers.submit({ preventDefault: () => {} })
    assert.equal(assigned, '/confirm')
    const raw = JSON.parse(store.get('spanified_subscribed'))
    assert.equal(raw.subscribed, true)
    assert.equal(raw.email, 'a@b.com')
  })

  after(() => {
    global.fetch = originalFetch
    global.window = originalWindow
  })
})
