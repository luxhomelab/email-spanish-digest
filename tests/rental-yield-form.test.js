import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import {
  sanitizeState, parseStateFromParams, stateToParams, clampField,
  DEFAULTS, QUERY_KEYS, FIELD_LIMITS,
} from '../static/js/rental-yield-form.js'

const REGIONS = ['madrid', 'catalunya', 'canarias']

describe('sanitizeState', () => {
  it('empty input yields DEFAULTS', () => {
    assert.deepEqual(sanitizeState({}, REGIONS), DEFAULTS)
  })
  it('defaults match the plan', () => {
    assert.equal(DEFAULTS.purchasePrice, 250000)
    assert.equal(DEFAULTS.monthlyRent, 1200)
    assert.equal(DEFAULTS.regionId, 'madrid')
    assert.equal(DEFAULTS.constructionSharePct, 70)
    assert.equal(DEFAULTS.rentalReductionPct, 50)
    assert.equal(DEFAULTS.useNonEuDeductions, false)
    assert.equal(DEFAULTS.plusvalia, 0)
  })
  it('garbage numbers fall back to default', () => {
    assert.equal(sanitizeState({ purchasePrice: 'abc' }, REGIONS).purchasePrice, DEFAULTS.purchasePrice)
    assert.equal(sanitizeState({ monthlyRent: NaN }, REGIONS).monthlyRent, DEFAULTS.monthlyRent)
    assert.equal(sanitizeState({ monthlyRent: Infinity }, REGIONS).monthlyRent, DEFAULTS.monthlyRent)
  })
  it('clamps negative money to 0 and percent to 0..100', () => {
    const s = sanitizeState({ purchasePrice: -5, vacancyRatePct: 250, costToSellPct: -1 }, REGIONS)
    assert.equal(s.purchasePrice, 0)
    assert.equal(s.vacancyRatePct, 100)
    assert.equal(s.costToSellPct, 0)
  })
  it('int fields truncate and clamp', () => {
    const s = sanitizeState({ holdYears: 99.7, loanTermYears: 0, renovationDurationMonths: 40 }, REGIONS)
    assert.equal(s.holdYears, 50)
    assert.equal(s.loanTermYears, 1)
    assert.equal(s.renovationDurationMonths, 24)
    assert.equal(clampField('holdYears', 7.9), 7)
  })
  it('enums fall back on unknown values', () => {
    const s = sanitizeState({ propertyType: 'x', taxStatus: 'y', rentalReductionPct: 55, regionId: 'atlantis' }, REGIONS)
    assert.equal(s.propertyType, 'resale')
    assert.equal(s.taxStatus, 'resident')
    assert.equal(s.rentalReductionPct, 50)
    assert.equal(s.regionId, 'madrid')
  })
  it('accepts valid enums', () => {
    const s = sanitizeState({ propertyType: 'new', taxStatus: 'non_resident_non_eu', rentalReductionPct: 90, regionId: 'canarias' }, REGIONS)
    assert.equal(s.propertyType, 'new')
    assert.equal(s.taxStatus, 'non_resident_non_eu')
    assert.equal(s.rentalReductionPct, 90)
    assert.equal(s.regionId, 'canarias')
  })
  it('reduction 0 and 100 are valid (not treated as missing)', () => {
    assert.equal(sanitizeState({ rentalReductionPct: '0' }, REGIONS).rentalReductionPct, 0)
    assert.equal(sanitizeState({ rentalReductionPct: 100 }, REGIONS).rentalReductionPct, 100)
  })
  it('booleans parse from 1/true', () => {
    const s = sanitizeState({ useLoan: '1', useRenovation: 'true', useNonEuDeductions: '0' }, REGIONS)
    assert.equal(s.useLoan, true)
    assert.equal(s.useRenovation, true)
    assert.equal(s.useNonEuDeductions, false)
  })
  it('every field limit has a default and a query key', () => {
    for (const k of Object.keys(FIELD_LIMITS)) {
      assert.ok(k in DEFAULTS, k)
      assert.ok(k in QUERY_KEYS, k)
    }
  })
  it('query keys are unique', () => {
    const v = Object.values(QUERY_KEYS)
    assert.equal(new Set(v).size, v.length)
  })
})

describe('parseStateFromParams', () => {
  it('returns null when no known params', () => {
    assert.equal(parseStateFromParams('?utm_source=x', REGIONS), null)
    assert.equal(parseStateFromParams('', REGIONS), null)
  })
  it('parses and sanitizes', () => {
    const s = parseStateFromParams('?ry_pp=300000&ry_r=catalunya&ry_ts=non_resident_eu&ry_loan=1&ry_hy=500', REGIONS)
    assert.equal(s.purchasePrice, 300000)
    assert.equal(s.regionId, 'catalunya')
    assert.equal(s.taxStatus, 'non_resident_eu')
    assert.equal(s.useLoan, true)
    assert.equal(s.holdYears, 50)
    assert.equal(s.monthlyRent, DEFAULTS.monthlyRent)
  })
  it('round-trips through stateToParams', () => {
    const state = { ...DEFAULTS, purchasePrice: 410000, useLoan: true, taxStatus: 'non_resident_non_eu', useNonEuDeductions: true, rentalReductionPct: 70 }
    const back = parseStateFromParams('?' + stateToParams(state).toString(), REGIONS)
    assert.deepEqual(back, state)
  })
})
