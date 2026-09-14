import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import { sanitizeState, parseStateFromParams, DEFAULTS, YEARS, VALID_TYPES, VALID_TIMES } from '../static/js/autonomo-form.js'

// ── sanitizeState: numeric clamping ──────────────────────────────────────────
describe('sanitizeState numbers', () => {
  it('clamps negative revenue to 0', () => {
    assert.equal(sanitizeState({ annualNetRevenue: -5000 }).annualNetRevenue, 0)
  })
  it('drops NaN revenue to default', () => {
    assert.equal(sanitizeState({ annualNetRevenue: Number.NaN }).annualNetRevenue, DEFAULTS.annualNetRevenue)
  })
  it('drops garbage string revenue to default', () => {
    assert.equal(sanitizeState({ annualNetRevenue: 'abc' }).annualNetRevenue, DEFAULTS.annualNetRevenue)
  })
  it('truncates fractional revenue', () => {
    assert.equal(sanitizeState({ annualNetRevenue: 30000.9 }).annualNetRevenue, 30000)
  })
  it('clamps age below 18 up to 18', () => {
    assert.equal(sanitizeState({ age: 5 }).age, 18)
  })
  it('clamps age above 100 down to 100', () => {
    assert.equal(sanitizeState({ age: 150 }).age, 100)
  })
  it('clamps children to 0..10', () => {
    assert.equal(sanitizeState({ numChildren: -2 }).numChildren, 0)
    assert.equal(sanitizeState({ numChildren: 99 }).numChildren, 10)
  })
  it('forces childrenUnder3 <= numChildren', () => {
    const s = sanitizeState({ numChildren: 1, childrenUnder3: 5 })
    assert.equal(s.childrenUnder3, 1)
  })
  it('rejects unknown disability level', () => {
    assert.equal(sanitizeState({ disabilityLevel: 50 }).disabilityLevel, 0)
  })
  it('accepts valid disability levels 0/33/65', () => {
    for (const v of [0, 33, 65]) assert.equal(sanitizeState({ disabilityLevel: v }).disabilityLevel, v)
  })
})

// ── sanitizeState: enums ─────────────────────────────────────────────────────
describe('sanitizeState enums', () => {
  it('rejects unknown autonomoType', () => {
    assert.equal(sanitizeState({ autonomoType: 'hacker' }).autonomoType, DEFAULTS.autonomoType)
  })
  it('rejects unknown timeAsAutonomo', () => {
    assert.equal(sanitizeState({ timeAsAutonomo: 'forever' }).timeAsAutonomo, DEFAULTS.timeAsAutonomo)
  })
  it('rejects year outside 2026..2031', () => {
    assert.equal(sanitizeState({ year: 1999 }).year, DEFAULTS.year)
    assert.equal(sanitizeState({ year: 2035 }).year, DEFAULTS.year)
  })
  it('rejects unknown region', () => {
    const regions = ['madrid', 'catalunya', 'ceuta', 'melilla', 'andalucia']
    assert.equal(sanitizeState({ region: 'atlantis' }, regions).region, DEFAULTS.region)
  })
  it('accepts every known region', () => {
    const regions = ['madrid', 'catalunya', 'ceuta', 'melilla', 'andalucia']
    for (const r of regions) {
      assert.equal(sanitizeState({ region: r }, regions).region, r)
    }
  })
})

// ── parseStateFromParams: URL sharing ────────────────────────────────────────
describe('parseStateFromParams', () => {
  it('returns null when no known params present', () => {
    assert.equal(parseStateFromParams('?foo=1'), null)
  })
  it('parses a full valid query string', () => {
    const s = parseStateFromParams('?aut_r=45000&aut_y=2027&aut_t=director&aut_d=new&aut_reg=catalunya&aut_age=40&aut_ch=2&aut_chu3=1&aut_dis=33')
    assert.equal(s.annualNetRevenue, 45000)
    assert.equal(s.year, 2027)
    assert.equal(s.autonomoType, 'director')
    assert.equal(s.region, 'catalunya')
    assert.equal(s.disabilityLevel, 33)
  })
  it('sanitizes hostile query values', () => {
    const regions = ['madrid', 'catalunya']
    const s = parseStateFromParams('?aut_r=-999&aut_reg=<script>&aut_age=200&aut_dis=99', regions)
    assert.equal(s.annualNetRevenue, 0)
    assert.equal(s.region, DEFAULTS.region)
    assert.equal(s.age, 100)
    assert.equal(s.disabilityLevel, 0)
  })
  it('clamps childrenUnder3 from URL to numChildren', () => {
    const s = parseStateFromParams('?aut_ch=1&aut_chu3=3')
    assert.equal(s.childrenUnder3, 1)
  })
})

// ── constants ────────────────────────────────────────────────────────────────
describe('constants', () => {
  it('years cover 2026..2031', () => {
    assert.deepEqual(YEARS, [2026, 2027, 2028, 2029, 2030, 2031])
  })
  it('types and times match the original', () => {
    assert.deepEqual(VALID_TYPES, ['individual', 'director'])
    assert.deepEqual(VALID_TIMES, ['new', 'mid', 'established'])
  })
})
