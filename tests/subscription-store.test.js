import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import {
  SUBSCRIBED_KEY,
  markSubscribed,
  isSubscribed,
} from '../static/js/subscription-store.js'

function memStorage() {
  const map = new Map()
  return {
    getItem: k => (map.has(k) ? map.get(k) : null),
    setItem: (k, v) => { map.set(k, v) },
  }
}

describe('subscription store (site-wide opt-in record)', () => {
  it('is false on a fresh storage', () => {
    assert.equal(isSubscribed(memStorage()), false)
  })

  it('markSubscribed flips it and keeps the email', () => {
    const s = memStorage()
    assert.equal(markSubscribed(s, 'reader@site.com'), true)
    assert.equal(isSubscribed(s), true)
    const raw = JSON.parse(s.getItem(SUBSCRIBED_KEY))
    assert.equal(raw.subscribed, true)
    assert.equal(raw.email, 'reader@site.com')
    assert.ok(raw.at)
  })

  it('survives broken JSON and broken storage (private mode)', () => {
    const s = memStorage()
    s.setItem(SUBSCRIBED_KEY, '{broken')
    assert.equal(isSubscribed(s), false)
    const bad = { getItem: () => { throw new Error('deny') }, setItem: () => { throw new Error('deny') } }
    assert.equal(isSubscribed(bad), false)
    assert.equal(markSubscribed(bad, 'a@b.com'), false)
  })
})
