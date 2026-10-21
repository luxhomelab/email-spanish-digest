import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import {
  DEFAULTS, QUERY_KEYS, FIELD_LIMITS, sanitizeState, parseStateFromParams, stateToParams,
} from '../static/js/net-salary-form.js'

const REGIONS = ['madrid', 'catalunya', 'ceuta', 'andalucia']

describe('net salary form state', () => {
  it('defaults', () => {
    assert.equal(DEFAULTS.amount, 30000)
    assert.equal(DEFAULTS.period, 'y')
    assert.equal(DEFAULTS.mode, 'gross')
    assert.equal(DEFAULTS.payments, '12')
    assert.equal(DEFAULTS.region, 'madrid')
    assert.equal(DEFAULTS.regime, 'standard')
    assert.deepEqual(DEFAULTS.descDisab, [])
    assert.equal(DEFAULTS.hoursPerWeek, 40)
  })

  it('every key has a distinct ns_ query key', () => {
    const keys = Object.values(QUERY_KEYS)
    assert.equal(new Set(keys).size, keys.length)
    for (const k of keys) assert.ok(k.startsWith('ns_'), k)
    for (const field of Object.keys(DEFAULTS)) assert.ok(QUERY_KEYS[field], `no query key for ${field}`)
  })

  it('sanitize clamps numbers to FIELD_LIMITS', () => {
    const s = sanitizeState({ amount: -5, kids: 99, hoursPerWeek: 0, atRate: 50 }, REGIONS)
    assert.equal(s.amount, FIELD_LIMITS.amount.min)
    assert.equal(s.kids, FIELD_LIMITS.kids.max)
    assert.equal(s.hoursPerWeek, FIELD_LIMITS.hoursPerWeek.min)
    assert.equal(s.atRate, FIELD_LIMITS.atRate.max)
  })

  it('sanitize rejects unknown enum values and regions', () => {
    const s = sanitizeState({ payments: '13', region: 'atlantis', regime: 'x', age: 'old', disability: '50', joint: '?', mealsMode: 'free' }, REGIONS)
    assert.equal(s.payments, '12')
    assert.equal(s.region, 'madrid')
    assert.equal(s.regime, 'standard')
    assert.equal(s.age, 'u65')
    assert.equal(s.disability, '0')
    assert.equal(s.joint, 'none')
    assert.equal(s.mealsMode, 'sacrifice')
  })

  it('disability lists keep only valid levels, capped', () => {
    const s = sanitizeState({ descDisab: ['33', 'x', '65', '33h', '33', '33', '33', '33'], ascDisab: 'nope' }, REGIONS)
    assert.deepEqual(s.descDisab, ['33', '65', '33h', '33', '33', '33'])
    assert.deepEqual(s.ascDisab, [])
  })

  it('single-parent joint taxation needs a child', () => {
    assert.equal(sanitizeState({ joint: 'single', kids: 0, kidsU3: 0 }, REGIONS).joint, 'none')
    assert.equal(sanitizeState({ joint: 'single', kidsU3: 1 }, REGIONS).joint, 'single')
  })

  it('URL round-trip', () => {
    const state = sanitizeState({
      ...DEFAULTS, amount: 2100, period: 'm', payments: '14', region: 'catalunya', kids: 2,
      sharedCustody: true, descDisab: ['33h', '65'], ascDisab: ['33'], meals: 1200, mealsMode: 'extra', mobility: true,
    }, REGIONS)
    const qs = new URLSearchParams(stateToParams(state)).toString()
    assert.deepEqual(parseStateFromParams('?' + qs, REGIONS), state)
  })

  it('writes the amount plus only non-default values', () => {
    const params = new Map(stateToParams({ ...DEFAULTS, region: 'catalunya' }))
    assert.deepEqual([...params.keys()].sort(), [QUERY_KEYS.amount, QUERY_KEYS.region].sort())
  })

  it('no ns_ params → null (falls back to storage)', () => {
    assert.equal(parseStateFromParams('?utm_source=x', REGIONS), null)
  })

  it('missing params take defaults', () => {
    const s = parseStateFromParams(`?${QUERY_KEYS.amount}=45000`, REGIONS)
    assert.deepEqual(s, { ...DEFAULTS, amount: 45000 })
  })
})
