import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import {
  calculateBill,
  compareProviders,
  getTotalKwh,
  ELECTRICITY_TAX_RATE,
  VAT_RATE,
} from '../static/js/electricity-calc.js'

const TOL = 1e-6

// ── constants ────────────────────────────────────────────────────────────────
describe('rates', () => {
  it('electricity special tax is 5.112696%', () => {
    assert.equal(ELECTRICITY_TAX_RATE, 0.05112696)
  })
  it('VAT (IVA) is 21%', () => {
    assert.equal(VAT_RATE, 0.21)
  })
})

// ── calculateBill (flat tariff) ─────────────────────────────────────────────
describe('calculateBill — flat', () => {
  const provider = {
    id: 'p1', name: 'Test', potenciaP1: 1, potenciaP2: 0,
    energyType: 'flat', energiaFlat: 0.5,
    bonoSocialDaily: 0.1, alquilerContadorDaily: 0.2,
  }
  const inputs = { days: 10, contractedKw: 2, kwhFlat: 100 }

  it('computes power term as P1_rate × days × kW', () => {
    const r = calculateBill(provider, inputs)
    assert.ok(Math.abs(r.terminoPotenciaP1 - 20) < TOL)
    assert.equal(r.terminoPotenciaP2, 0)
    assert.ok(Math.abs(r.terminoPotencia - 20) < TOL)
  })

  it('computes energy term as kWh × price', () => {
    const r = calculateBill(provider, inputs)
    assert.ok(Math.abs(r.terminoEnergia - 50) < TOL)
  })

  it('bills bono social and meter rental per day', () => {
    const r = calculateBill(provider, inputs)
    assert.ok(Math.abs(r.bonoSocial - 1) < TOL)
    assert.ok(Math.abs(r.alquilerContador - 2) < TOL)
  })

  it('applies 5.112696% tax and 21% VAT in the documented order', () => {
    const r = calculateBill(provider, inputs)
    // subtotal = 20 (power) + 50 (energy) + 1 (bono) = 71
    assert.ok(Math.abs(r.subtotal - 71) < TOL)
    assert.ok(Math.abs(r.impuestoElectricidad - 71 * 0.05112696) < TOL)
    // totalElectricidad = 71 + tax + 2 (alquiler)
    assert.ok(Math.abs(r.totalElectricidad - (71 + 71 * 0.05112696 + 2)) < TOL)
    assert.ok(Math.abs(r.iva - (71 + 71 * 0.05112696 + 2) * 0.21) < TOL)
    assert.ok(Math.abs(r.total - (71 + 71 * 0.05112696 + 2) * 1.21) < TOL)
    // hardcoded: 92.722317…
    assert.ok(Math.abs(r.total - 92.7223171336) < TOL)
  })

  it('subtotal = power + energy + bono; total = electricity total + VAT', () => {
    const r = calculateBill(provider, inputs)
    assert.ok(Math.abs(r.subtotal - (r.terminoPotencia + r.terminoEnergia + r.bonoSocial)) < TOL)
    assert.ok(Math.abs(r.total - (r.totalElectricidad + r.iva)) < TOL)
  })

  it('ignores period kWh on a flat tariff', () => {
    const r = calculateBill(provider, { days: 10, contractedKw: 2, kwhFlat: 100, kwhPunta: 9999 })
    assert.ok(Math.abs(r.terminoEnergia - 50) < TOL)
  })

  it('zero consumption and zero rates → zero bill', () => {
    const r = calculateBill(
      { id: 'z', name: 'z', potenciaP1: 0, potenciaP2: 0, energyType: 'flat', energiaFlat: 0 },
      { days: 30, contractedKw: 5.7, kwhFlat: 0 }
    )
    assert.equal(r.total, 0)
    assert.equal(r.iva, 0)
    assert.equal(r.subtotal, 0)
  })

  it('missing optional fields are treated as zero', () => {
    const r = calculateBill({}, { days: 30, contractedKw: 5.7 })
    assert.equal(r.total, 0)
    assert.equal(r.bonoSocial, 0)
    assert.equal(r.alquilerContador, 0)
  })

  it('bills both P1 and P2 capacity periods', () => {
    const r = calculateBill(
      { id: 'p', name: 'p', potenciaP1: 0.1, potenciaP2: 0.05, energyType: 'flat', energiaFlat: 0 },
      { days: 30, contractedKw: 5.7, kwhFlat: 0 }
    )
    // 0.1 × 30 × 5.7 = 17.1 · 0.05 × 30 × 5.7 = 8.55
    assert.ok(Math.abs(r.terminoPotenciaP1 - 17.1) < TOL)
    assert.ok(Math.abs(r.terminoPotenciaP2 - 8.55) < TOL)
    assert.ok(Math.abs(r.terminoPotencia - 25.65) < TOL)
  })
})

// ── calculateBill (punta/llano/valle) ───────────────────────────────────────
describe('calculateBill — punta/llano/valle', () => {
  const provider = {
    id: 'p', name: 'P', potenciaP1: 0, potenciaP2: 0,
    energyType: 'punta_llano_valle',
    energiaPunta: 0.2, energiaLlano: 0.15, energiaValle: 0.1,
  }
  const inputs = { days: 30, contractedKw: 5.7, kwhPunta: 10, kwhLlano: 20, kwhValle: 30 }

  it('sums the three period energies', () => {
    const r = calculateBill(provider, inputs)
    // 10×0.2 + 20×0.15 + 30×0.1 = 2 + 3 + 3 = 8
    assert.ok(Math.abs(r.terminoEnergia - 8) < TOL)
    assert.ok(Math.abs(r.subtotal - 8) < TOL)
  })

  it('tax and VAT apply on top of period energy', () => {
    const r = calculateBill(provider, inputs)
    assert.ok(Math.abs(r.total - 8 * 1.05112696 * 1.21) < TOL)
  })

  it('ignores kwhFlat on a time-of-use tariff', () => {
    const r = calculateBill(provider, { ...inputs, kwhFlat: 5000 })
    assert.ok(Math.abs(r.terminoEnergia - 8) < TOL)
  })
})

// ── default market tariffs (integration with defaults data) ─────────────────
describe('default Naturgy tariff', () => {
  const naturgy = {
    id: 'naturgy', name: 'Naturgy',
    potenciaP1: 0.11362, potenciaP2: 0.040193,
    energyType: 'flat', energiaFlat: 0.108,
    bonoSocialDaily: 0, alquilerContadorDaily: 0,
  }
  const inputs = { days: 30, contractedKw: 5.7, kwhFlat: 300 }

  it('produces a realistic ~€75 monthly bill', () => {
    const r = calculateBill(naturgy, inputs)
    // P1 19.42902 + P2 6.873003 + energy 32.4 = 58.702023 subtotal
    assert.ok(Math.abs(r.subtotal - 58.702023) < TOL)
    assert.ok(Math.abs(r.total - 74.66) < 0.01, `got ${r.total}`)
  })
})

// ── compareProviders ────────────────────────────────────────────────────────
describe('compareProviders', () => {
  const cheap = { id: 'a', name: 'Cheap', potenciaP1: 0, potenciaP2: 0, energyType: 'flat', energiaFlat: 0.1 }
  const mid = { id: 'b', name: 'Mid', potenciaP1: 0, potenciaP2: 0, energyType: 'flat', energiaFlat: 0.2 }
  const pricey = { id: 'c', name: 'Pricey', potenciaP1: 0, potenciaP2: 0, energyType: 'flat', energiaFlat: 0.4 }
  const inputs = { days: 30, contractedKw: 0, kwhFlat: 1000 }

  it('ranks providers cheapest first', () => {
    const results = compareProviders([pricey, cheap, mid], inputs)
    assert.equal(results.length, 3)
    assert.deepEqual(results.map(r => r.provider.id), ['a', 'b', 'c'])
    assert.deepEqual(results.map(r => r.rank), [1, 2, 3])
  })

  it('each result carries provider, breakdown and rank', () => {
    const results = compareProviders([cheap, mid], inputs)
    for (const r of results) {
      assert.ok(r.provider)
      assert.ok(r.breakdown && typeof r.breakdown.total === 'number')
      assert.ok(Number.isInteger(r.rank))
    }
  })

  it('totals increase with rank', () => {
    const results = compareProviders([pricey, cheap, mid], inputs)
    assert.ok(results[0].breakdown.total < results[1].breakdown.total)
    assert.ok(results[1].breakdown.total < results[2].breakdown.total)
  })

  it('handles a single provider (rank 1)', () => {
    const results = compareProviders([cheap], inputs)
    assert.equal(results.length, 1)
    assert.equal(results[0].rank, 1)
  })

  it('comparison uses the same math as calculateBill', () => {
    const results = compareProviders([cheap, mid], inputs)
    assert.ok(Math.abs(results[0].breakdown.total - calculateBill(cheap, inputs).total) < TOL)
  })
})

// ── getTotalKwh ─────────────────────────────────────────────────────────────
describe('getTotalKwh', () => {
  it('returns kwhFlat when present (flat tariff)', () => {
    assert.equal(getTotalKwh({ kwhFlat: 300, kwhPunta: 99 }), 300)
  })

  it('returns 0 for zero/absent flat consumption', () => {
    assert.equal(getTotalKwh({ kwhFlat: 0 }), 0)
    assert.equal(getTotalKwh({ kwhFlat: null }), 0)
  })

  it('sums periods when kwhFlat is absent (time-of-use)', () => {
    assert.equal(getTotalKwh({ kwhPunta: 75, kwhLlano: 150, kwhValle: 75 }), 300)
  })

  it('treats missing period values as zero', () => {
    assert.equal(getTotalKwh({ kwhPunta: 10 }), 10)
    assert.equal(getTotalKwh({}), 0)
  })
})
