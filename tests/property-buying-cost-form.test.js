import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import { sanitizeState, parseStateFromParams, DEFAULTS } from '../static/js/property-buying-cost-form.js'

const REGIONS = ['madrid', 'catalunya', 'canarias', 'comunidad_valenciana']

// ── sanitizeState ────────────────────────────────────────────────────────────
describe('sanitizeState', () => {
  it('defaults: price 200000, resale, madrid', () => {
    assert.deepEqual(sanitizeState({}, REGIONS), {
      price: 200000, isNewBuild: false, regionId: 'madrid',
    })
    assert.equal(DEFAULTS.price, 200000)
    assert.equal(DEFAULTS.isNewBuild, false)
    assert.equal(DEFAULTS.regionId, 'madrid')
  })
  it('drops NaN/garbage price to default', () => {
    assert.equal(sanitizeState({ price: Number.NaN }, REGIONS).price, DEFAULTS.price)
    assert.equal(sanitizeState({ price: 'abc' }, REGIONS).price, DEFAULTS.price)
  })
  it('clamps negative price to 0', () => {
    assert.equal(sanitizeState({ price: -5000 }, REGIONS).price, 0)
  })
  it('truncates fractional price', () => {
    assert.equal(sanitizeState({ price: 200000.9 }, REGIONS).price, 200000)
  })
  it('accepts valid price', () => {
    assert.equal(sanitizeState({ price: 350000 }, REGIONS).price, 350000)
  })
  it('rejects unknown region → default', () => {
    assert.equal(sanitizeState({ regionId: 'atlantis' }, REGIONS).regionId, DEFAULTS.regionId)
  })
  it('accepts every known region', () => {
    for (const r of REGIONS) {
      assert.equal(sanitizeState({ regionId: r }, REGIONS).regionId, r)
    }
  })
  it('coerces isNewBuild to boolean (default false)', () => {
    assert.equal(sanitizeState({}, REGIONS).isNewBuild, false)
    assert.equal(sanitizeState({ isNewBuild: '1' }, REGIONS).isNewBuild, true)
    assert.equal(sanitizeState({ isNewBuild: 1 }, REGIONS).isNewBuild, true)
    assert.equal(sanitizeState({ isNewBuild: true }, REGIONS).isNewBuild, true)
    assert.equal(sanitizeState({ isNewBuild: 'yes' }, REGIONS).isNewBuild, false)
  })
})

// ── parseStateFromParams ─────────────────────────────────────────────────────
describe('parseStateFromParams', () => {
  it('returns null when no known params present', () => {
    assert.equal(parseStateFromParams('?foo=1', REGIONS), null)
  })
  it('parses a full valid query string', () => {
    const s = parseStateFromParams('?pbc_p=350000&pbc_nb=1&pbc_r=catalunya', REGIONS)
    assert.equal(s.price, 350000)
    assert.equal(s.isNewBuild, true)
    assert.equal(s.regionId, 'catalunya')
  })
  it('parses resale flag pbc_nb=0', () => {
    const s = parseStateFromParams('?pbc_nb=0', REGIONS)
    assert.equal(s.isNewBuild, false)
  })
  it('sanitizes hostile query values', () => {
    const s = parseStateFromParams('?pbc_p=-999&pbc_r=<script>', REGIONS)
    assert.equal(s.price, 0)
    assert.equal(s.regionId, DEFAULTS.regionId)
  })
})
