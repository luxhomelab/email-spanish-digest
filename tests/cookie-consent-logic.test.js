import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  CONSENT_VERSION, CONSENT_MAX_AGE_MS, parseConsent, serializeConsent,
  allChoice, isWithdrawal, vendorCookieNames
} from '../static/js/cookie-consent-logic.js'

const NOW = 1_800_000_000_000

test('no or broken record means ask', () => {
  for (const raw of [null, undefined, '', 'nope', '[]', 'null', '{"v":1}']) {
    assert.equal(parseConsent(raw, NOW), null, String(raw))
  }
})

test('round trip keeps only known categories as booleans', () => {
  const raw = serializeConsent({ analytics: true, marketing: 'yes', extra: true }, NOW)
  assert.deepEqual(JSON.parse(raw), { v: CONSENT_VERSION, ts: NOW, analytics: true, marketing: false })
  assert.deepEqual(parseConsent(raw, NOW), { analytics: true, marketing: false })
})

test('a refusal is a valid stored choice', () => {
  assert.deepEqual(parseConsent(serializeConsent(allChoice(false), NOW), NOW), { analytics: false, marketing: false })
})

test('old version, expired or future record means ask again', () => {
  assert.equal(parseConsent(JSON.stringify({ v: CONSENT_VERSION - 1, ts: NOW, analytics: true }), NOW), null)
  assert.equal(parseConsent(serializeConsent(allChoice(true), NOW - CONSENT_MAX_AGE_MS - 1), NOW), null)
  assert.notEqual(parseConsent(serializeConsent(allChoice(true), NOW - CONSENT_MAX_AGE_MS + 1000), NOW), null)
  assert.equal(parseConsent(serializeConsent(allChoice(true), NOW + 3600_000), NOW), null)
})

test('withdrawal only when a granted category is turned off', () => {
  assert.equal(isWithdrawal(null, allChoice(false)), false)
  assert.equal(isWithdrawal(allChoice(false), allChoice(true)), false)
  assert.equal(isWithdrawal({ analytics: true, marketing: false }, { analytics: true, marketing: true }), false)
  assert.equal(isWithdrawal({ analytics: true, marketing: true }, { analytics: true, marketing: false }), true)
  assert.equal(isWithdrawal(allChoice(true), allChoice(false)), true)
})

test('vendor cookies picked per denied category', () => {
  const jar = '_ga=GA1.1.1; _ga_CBF70VDX1D=GS1; _gid=x; _gat_UA=1; _fbp=fb.1; _fbc=fb.2; other=1; _gax=keep'
  assert.deepEqual(vendorCookieNames(jar, allChoice(false)), ['_ga', '_ga_CBF70VDX1D', '_gid', '_gat_UA', '_fbp', '_fbc'])
  assert.deepEqual(vendorCookieNames(jar, { analytics: true, marketing: false }), ['_fbp', '_fbc'])
  assert.deepEqual(vendorCookieNames(jar, allChoice(true)), [])
  assert.deepEqual(vendorCookieNames('', allChoice(false)), [])
})
