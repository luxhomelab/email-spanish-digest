import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import {
  calculateItpAmount,
  estimateNotaryFee,
  estimateRegistryFee,
  calculateBuyingCost,
  MIN_PRICE,
} from '../static/js/property-buying-cost-calc.js'

// ── estimateNotaryFee boundaries ─────────────────────────────────────────────
describe('estimateNotaryFee', () => {
  it('returns 0 for null/negative', () => {
    assert.equal(estimateNotaryFee(null), 0)
    assert.equal(estimateNotaryFee(-5), 0)
  })
  it('boundary: 99999 → 700, 100000 → 850', () => {
    assert.equal(estimateNotaryFee(99999), 700)
    assert.equal(estimateNotaryFee(100000), 850)
  })
  it('boundary: 199999 → 850, 200000 → 1050', () => {
    assert.equal(estimateNotaryFee(199999), 850)
    assert.equal(estimateNotaryFee(200000), 1050)
  })
  it('boundary: 399999 → 1050, 400000 → 1150', () => {
    assert.equal(estimateNotaryFee(399999), 1050)
    assert.equal(estimateNotaryFee(400000), 1150)
  })
  it('boundary: 699999 → 1150, 700000 → 1200', () => {
    assert.equal(estimateNotaryFee(699999), 1150)
    assert.equal(estimateNotaryFee(700000), 1200)
  })
})

// ── estimateRegistryFee boundaries ───────────────────────────────────────────
describe('estimateRegistryFee', () => {
  it('returns 0 for null/negative', () => {
    assert.equal(estimateRegistryFee(null), 0)
    assert.equal(estimateRegistryFee(-5), 0)
  })
  it('boundary: 99999 → 450, 100000 → 550', () => {
    assert.equal(estimateRegistryFee(99999), 450)
    assert.equal(estimateRegistryFee(100000), 550)
  })
  it('boundary: 199999 → 550, 200000 → 700', () => {
    assert.equal(estimateRegistryFee(199999), 550)
    assert.equal(estimateRegistryFee(200000), 700)
  })
  it('boundary: 399999 → 700, 400000 → 850', () => {
    assert.equal(estimateRegistryFee(399999), 700)
    assert.equal(estimateRegistryFee(400000), 850)
  })
  it('boundary: 699999 → 850, 700000 → 1000', () => {
    assert.equal(estimateRegistryFee(699999), 850)
    assert.equal(estimateRegistryFee(700000), 1000)
  })
})

// ── calculateItpAmount ───────────────────────────────────────────────────────
describe('calculateItpAmount', () => {
  const flat = (rate) => ({ id: 'x', itp_standard: rate })
  it('returns 0 for null region or non-positive price', () => {
    assert.equal(calculateItpAmount(200000, null), 0)
    assert.equal(calculateItpAmount(0, flat(6)), 0)
    assert.equal(calculateItpAmount(-1, flat(6)), 0)
  })
  it('flat rate: Madrid 6% on €200k → €12,000', () => {
    assert.equal(calculateItpAmount(200000, flat(6)), 12000)
  })
  it('marginal: Catalunya €700k → 600000×10% + 100000×11% = €71,000', () => {
    const cat = { id: 'catalunya', itp_standard: 10, itp_brackets: [
      { upTo: 600000, rate: 10 }, { upTo: 900000, rate: 11 },
      { upTo: 1500000, rate: 12 }, { upTo: null, rate: 13 },
    ]}
    assert.equal(calculateItpAmount(700000, cat), 71000)
  })
  it('marginal: Aragón €500k → 32000 + 4250 + 4500 = €40,750', () => {
    const ar = { id: 'aragon', itp_standard: 8, itp_brackets: [
      { upTo: 400000, rate: 8 }, { upTo: 450000, rate: 8.5 },
      { upTo: 500000, rate: 9 }, { upTo: 750000, rate: 9.5 },
      { upTo: null, rate: 10 },
    ]}
    assert.equal(calculateItpAmount(500000, ar), 40750)
  })
  it('marginal: Baleares €700k → 32000 + 18000 + 10000 = €60,000', () => {
    const bal = { id: 'baleares', itp_standard: 8, itp_brackets: [
      { upTo: 400000, rate: 8 }, { upTo: 600000, rate: 9 },
      { upTo: 1000000, rate: 10 }, { upTo: 3000000, rate: 12 },
      { upTo: null, rate: 13 },
    ]}
    assert.equal(calculateItpAmount(700000, bal), 60000)
  })
})

// ── calculateBuyingCost ──────────────────────────────────────────────────────
describe('calculateBuyingCost', () => {
  it('returns null for price below MIN_PRICE (10000)', () => {
    assert.equal(MIN_PRICE, 10000)
    assert.equal(calculateBuyingCost({ price: 9999, isNewBuild: false, regionId: 'madrid' }), null)
    assert.equal(calculateBuyingCost({ price: null, isNewBuild: false, regionId: 'madrid' }), null)
  })
  it('returns null for unknown region', () => {
    assert.equal(calculateBuyingCost({ price: 200000, isNewBuild: false, regionId: 'atlantis' }), null)
  })
  it('Madrid resale €200k → ITP 6% = €12,000, total €13,750', () => {
    const r = calculateBuyingCost({ price: 200000, isNewBuild: false, regionId: 'madrid' })
    assert.equal(r.taxType, 'ITP')
    assert.equal(r.primaryTaxAmount, 12000)
    assert.equal(r.ajdAmount, null)
    assert.equal(r.totalTax, 12000)
    assert.equal(r.notaryFee, 1050)
    assert.equal(r.registryFee, 700)
    assert.equal(r.totalCosts, 13750)
    assert.deepEqual(r.breakdown.map(b => b.key), ['itp', 'notary', 'registry'])
  })
  it('Madrid new-build €200k → IVA 10% + AJD 0.75% = €21,500, total €23,250', () => {
    const r = calculateBuyingCost({ price: 200000, isNewBuild: true, regionId: 'madrid' })
    assert.equal(r.taxType, 'IVA+AJD')
    assert.equal(r.primaryTaxAmount, 20000)
    assert.equal(r.ajdRate, 0.75)
    assert.equal(r.ajdAmount, 1500)
    assert.equal(r.totalTax, 21500)
    assert.equal(r.totalCosts, 23250)
    assert.deepEqual(r.breakdown.map(b => b.key), ['iva', 'ajd', 'notary', 'registry'])
  })
  it('Canarias new-build €200k → IGIC 7% + AJD 0.75% = €15,500, total €17,250', () => {
    const r = calculateBuyingCost({ price: 200000, isNewBuild: true, regionId: 'canarias' })
    assert.equal(r.taxType, 'IGIC+AJD')
    assert.equal(r.primaryTaxRate, 7.0)
    assert.equal(r.primaryTaxAmount, 14000)
    assert.equal(r.ajdAmount, 1500)
    assert.equal(r.totalTax, 15500)
    assert.equal(r.totalCosts, 17250)
    assert.deepEqual(r.breakdown.map(b => b.key), ['igic', 'ajd', 'notary', 'registry'])
  })
  it('Catalunya resale €700k → marginal ITP €71,000', () => {
    const r = calculateBuyingCost({ price: 700000, isNewBuild: false, regionId: 'catalunya' })
    assert.equal(r.taxType, 'ITP')
    assert.equal(r.primaryTaxAmount, 71000)
  })
  it('Aragón resale €500k → marginal ITP €40,750', () => {
    const r = calculateBuyingCost({ price: 500000, isNewBuild: false, regionId: 'aragon' })
    assert.equal(r.primaryTaxAmount, 40750)
  })
  it('Valencia resale €500k post-transition (2026-07-01) → 9% = €45,000', () => {
    const r = calculateBuyingCost({ price: 500000, isNewBuild: false, regionId: 'comunidad_valenciana' })
    assert.equal(r.primaryTaxAmount, 45000)
  })
  it('Valencia resale €1.2M post-transition → 90000 + 22000 = €112,000', () => {
    const r = calculateBuyingCost({ price: 1200000, isNewBuild: false, regionId: 'comunidad_valenciana' })
    assert.equal(r.primaryTaxAmount, 112000)
  })
  it('País Vasco new-build omits AJD row (ajd 0%)', () => {
    const r = calculateBuyingCost({ price: 200000, isNewBuild: true, regionId: 'pais_vasco' })
    assert.equal(r.taxType, 'IVA+AJD')
    assert.equal(r.primaryTaxAmount, 20000)
    assert.deepEqual(r.breakdown.map(b => b.key), ['iva', 'notary', 'registry'])
  })
})
