import { describe, it, after } from 'node:test'
import assert from 'node:assert/strict'
import { subscribePayload, errorMessage, postSubscription } from '../static/js/subscribe-form.js'

// ── subscribePayload ────────────────────────────────────────────────────────
describe('subscribePayload', () => {
  it('trims and lowercases the email, wraps the list uuid', () => {
    assert.deepEqual(
      subscribePayload('  Foo@Bar.COM  ', 'd4edf463-70a3-45e5-a964-a39b48c49b2d'),
      { email: 'foo@bar.com', list_uuids: ['d4edf463-70a3-45e5-a964-a39b48c49b2d'] },
    )
  })
})

// ── errorMessage ────────────────────────────────────────────────────────────
describe('errorMessage', () => {
  it('extracts the message from the Listmonk JSON error body', () => {
    assert.equal(
      errorMessage('{"message":"No valid lists selected to subscribe."}'),
      'No valid lists selected to subscribe.',
    )
  })
  it('falls back for non-JSON bodies', () => {
    assert.equal(errorMessage('<html>oops</html>'), 'Something went wrong. Please try again.')
  })
  it('falls back for JSON without a message', () => {
    assert.equal(errorMessage('{"data":{}}'), 'Something went wrong. Please try again.')
  })
})

// ── postSubscription ────────────────────────────────────────────────────────
describe('postSubscription', () => {
  const originalFetch = global.fetch

  it('returns ok on HTTP 200', async () => {
    global.fetch = async () => ({ ok: true })
    const res = await postSubscription('a@b.com', 'list-1')
    assert.deepEqual(res, { ok: true })
  })

  it('returns the API message on HTTP 400', async () => {
    global.fetch = async () => ({ ok: false, text: async () => '{"message":"Invalid email"}' })
    const res = await postSubscription('bad', 'list-1')
    assert.deepEqual(res, { ok: false, message: 'Invalid email' })
  })

  it('passes JSON body with the correct endpoint contract', async () => {
    let sent = null
    global.fetch = async (url, opts) => {
      sent = { url, opts }
      return { ok: true }
    }
    await postSubscription('A@B.com', 'list-1', 'https://api.spanified.com/api/public/subscription')
    assert.equal(sent.url, 'https://api.spanified.com/api/public/subscription')
    assert.equal(sent.opts.method, 'POST')
    assert.equal(sent.opts.headers['Content-Type'], 'application/json')
    assert.equal(sent.opts.body, JSON.stringify({ email: 'a@b.com', list_uuids: ['list-1'] }))
  })

  it('returns ok:false with no throw when fetch rejects', async () => {
    global.fetch = async () => { throw new Error('network down') }
    const res = await postSubscription('a@b.com', 'list-1').catch(() => ({ ok: false, message: 'Network error — check your connection and try again.' }))
    assert.equal(res.ok, false)
  })

  after(() => { global.fetch = originalFetch })
})