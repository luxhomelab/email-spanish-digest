import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import {
  buildMortgageSchedule,
  buildVerdict,
  calculateExitTax,
  calculateIrrFromCashflows,
  calculatePurchaseTax,
  simulateProjection,
} from '../static/js/rental-yield-calc.js'
import { REGIONS } from '../static/js/property-buying-cost-calc.js'
import { DEFAULTS } from '../static/js/rental-yield-form.js'

const near = (a, b, eps = 0.01) => assert.ok(Math.abs(a - b) <= eps, `${a} != ${b}`)
const region = id => REGIONS.find(r => r.id === id)
const sim = over => simulateProjection({ ...DEFAULTS, ...over })

// ── mortgage ────────────────────────────────────────────────────────────────
describe('buildMortgageSchedule', () => {
  it('annuity payment for 200k @3% over 30y', () => {
    const s = buildMortgageSchedule(200000, 3, 30, 50)
    near(s.monthlyPayment, 843.21, 0.01)
    near(s.principalRemainingByYear[30], 0, 0.01)
    near(s.totalPaidByYear[0], 843.21 * 12, 0.2)
  })
  it('zero interest is linear', () => {
    const s = buildMortgageSchedule(120000, 0, 10, 50)
    near(s.monthlyPayment, 1000)
    near(s.principalRemainingByYear[5], 60000, 0.01)
  })
  it('no loan -> zeros', () => {
    assert.equal(buildMortgageSchedule(0, 3, 30, 50).monthlyPayment, 0)
  })
})

// ── purchase taxes ──────────────────────────────────────────────────────────
describe('purchase tax', () => {
  it('default scenario: Madrid resale 250k -> ITP 15000', () => {
    assert.equal(sim({}).purchaseTax, 15000)
  })
  it('marginal brackets: Catalunya 700k = 71000', () => {
    near(calculatePurchaseTax(700000, region('catalunya'), 'resale').purchaseTax, 71000)
  })
  it('Cantabria 400k = 300k@7% + 100k@9% = 30000', () => {
    near(calculatePurchaseTax(400000, region('cantabria'), 'resale').purchaseTax, 30000)
  })
  it('new build Madrid = IVA 10% + AJD 0.75%', () => {
    const t = calculatePurchaseTax(200000, region('madrid'), 'new')
    assert.equal(t.taxType, 'IVA+AJD')
    near(t.purchaseTax, 20000 + 1500)
  })
  it('new build Canarias = IGIC 7% + AJD 0.75%', () => {
    const t = calculatePurchaseTax(200000, region('canarias'), 'new')
    assert.equal(t.taxType, 'IGIC+AJD')
    near(t.purchaseTax, 14000 + 1500)
  })
  it('new build Pais Vasco = IVA only (AJD 0)', () => {
    near(calculatePurchaseTax(200000, region('pais_vasco'), 'new').purchaseTax, 20000)
  })
  it('simulation uses the new-build tax', () => {
    near(sim({ purchasePrice: 200000, propertyType: 'new' }).purchaseTax, 21500)
  })
})

// ── gross yield ─────────────────────────────────────────────────────────────
describe('gross yield', () => {
  it('1200/month on 250k = 5.76%', () => {
    near(sim({}).grossYield, 5.76, 1e-9)
  })
})

// ── rental tax by status ────────────────────────────────────────────────────
// Year-1 figures for the default scenario (no loan):
//   EGI 13680; opex 2544; amortization (250000+15000+5000)*0.7*0.03 = 5670
//   net base = 5466
describe('rental income tax', () => {
  it('resident default: reduction 50%, marginal 30% -> 820.9', () => {
    near(sim({}).firstYearTax, 5466 * 0.5 * 0.3, 0.01)
  })
  it('resident reduction selectable: 0% and 90%', () => {
    near(sim({ rentalReductionPct: 0 }).firstYearTax, 5466 * 0.3, 0.01)
    near(sim({ rentalReductionPct: 90 }).firstYearTax, 5466 * 0.1 * 0.3, 0.01)
    assert.equal(sim({ rentalReductionPct: 100 }).firstYearTax, 0)
  })
  it('EU non-resident: 19% of net base, no reduction', () => {
    near(sim({ taxStatus: 'non_resident_eu' }).firstYearTax, 5466 * 0.19, 0.01)
  })
  it('EU non-resident deducts mortgage interest', () => {
    const noLoan = sim({ taxStatus: 'non_resident_eu' })
    const loan = sim({ taxStatus: 'non_resident_eu', useLoan: true })
    const interest = loan.schedule.interestByYear[0]
    assert.ok(interest > 5000)
    // base is reduced by interest (floored at zero)
    const expected = Math.max(5466 - interest, 0) * 0.19
    near(loan.firstYearTax, expected, 0.01)
    assert.ok(loan.firstYearTax < noLoan.firstYearTax)
  })
  it('non-EU default: 24% of gross EGI', () => {
    near(sim({ taxStatus: 'non_resident_non_eu' }).firstYearTax, 13680 * 0.24, 0.01)
  })
  it('non-EU with AN 2025 ruling: 24% of net base', () => {
    near(sim({ taxStatus: 'non_resident_non_eu', useNonEuDeductions: true }).firstYearTax, 5466 * 0.24, 0.01)
  })
  it('tax base never negative', () => {
    assert.equal(sim({ monthlyRent: 100 }).firstYearTax, 0)
  })
})

// ── capital gains on sale ───────────────────────────────────────────────────
describe('calculateExitTax', () => {
  it('resident scale at bracket edges', () => {
    near(calculateExitTax(6000), 1140)
    near(calculateExitTax(50000), 1140 + 44000 * 0.21)
    near(calculateExitTax(200000), 1140 + 9240 + 150000 * 0.23)
    near(calculateExitTax(300000), 1140 + 9240 + 34500 + 100000 * 0.27)
    near(calculateExitTax(400000), 1140 + 9240 + 34500 + 27000 + 100000 * 0.30)
  })
  it('non-residents pay flat 19%', () => {
    near(calculateExitTax(400000, 'non_resident_eu'), 76000)
    near(calculateExitTax(400000, 'non_resident_non_eu'), 76000)
  })
  it('zero or negative gain -> 0', () => {
    assert.equal(calculateExitTax(0), 0)
    assert.equal(calculateExitTax(-100), 0)
  })
  it('simulation: non-resident exit tax is 19% of gain, resident higher at large gain', () => {
    const res = sim({})
    const non = sim({ taxStatus: 'non_resident_eu' })
    near(non.exitTax, non.capitalGainForTax * 0.19, 0.01)
    assert.ok(res.exitTax > res.capitalGainForTax * 0.19)
  })
})

// ── amortization ────────────────────────────────────────────────────────────
describe('amortization', () => {
  it('base = (price+tax+closing) x construction share, 3% per year', () => {
    const r = sim({})
    near(r.amortizationBase, 270000 * 0.7)
    near(r.amortizationByYear[0], 270000 * 0.7 * 0.03)
  })
  it('construction share is configurable', () => {
    near(sim({ constructionSharePct: 50 }).amortizationByYear[0], 270000 * 0.5 * 0.03)
  })
  it('renovation cost is added to the base', () => {
    const r = sim({ useRenovation: true, renovationCost: 20000 })
    near(r.amortizationBase, 270000 * 0.7 + 20000)
  })
  it('cumulative cap = base (3% for ~33.3 years)', () => {
    const r = sim({ holdYears: 50 })
    const total = r.amortizationByYear.reduce((s, v) => s + v, 0)
    near(total, r.amortizationBase, 0.001)
    assert.equal(r.amortizationByYear[49], 0)
    assert.ok(r.amortizationByYear[33] > 0 && r.amortizationByYear[33] < r.amortizationByYear[0])
  })
  it('accumulated amortization reduces the tax acquisition cost', () => {
    const r = sim({ holdYears: 10 })
    const used = r.amortizationByYear.slice(0, 10).reduce((s, v) => s + v, 0)
    near(r.taxAcquisitionCost, 250000 + 15000 + 5000 - used)
  })
})

// ── plusvalia ───────────────────────────────────────────────────────────────
describe('municipal plusvalia', () => {
  it('is added to selling costs', () => {
    const a = sim({ plusvalia: 0 })
    const b = sim({ plusvalia: 3000 })
    near(b.sellingCostsAmount - a.sellingCostsAmount, 3000, 1e-6)
    assert.ok(b.totalNetProfit < a.totalNetProfit)
  })
})

// ── IRR ─────────────────────────────────────────────────────────────────────
describe('calculateIrrFromCashflows', () => {
  it('known example: -100, +110 -> 10%', () => {
    near(calculateIrrFromCashflows([-100, 110]), 10, 1e-4)
  })
  it('-1000, 300, 400, 500 -> ~8.9%', () => {
    near(calculateIrrFromCashflows([-1000, 300, 400, 500]), 8.8963, 0.01)
  })
  it('degenerate inputs -> 0', () => {
    assert.equal(calculateIrrFromCashflows([]), 0)
    assert.equal(calculateIrrFromCashflows([0, 0, 0]), 0)
    assert.equal(calculateIrrFromCashflows([100, 100]), 0)
  })
})

// ── default scenario KPIs ───────────────────────────────────────────────────
describe('default scenario', () => {
  it('yields are plausible and consistent', () => {
    const r = sim({})
    near(r.grossYield, 5.76)
    near(r.netYield, 3.8208, 0.001)
    near(r.cashOnCashReturn, r.netYield, 1e-9) // no loan
    near(r.monthlyCashFlow, r.firstYearCashFlow / 12, 1e-9)
    assert.ok(r.irr > 0 && r.irr < 20)
    assert.equal(r.equityByYear.length, 51)
  })
  it('throws on unknown region', () => {
    assert.throws(() => simulateProjection({ ...DEFAULTS, regionId: 'nope' }))
  })
})

describe('growth and outputs', () => {
  it('rent and expense growth start in year 2 and move IRR and profit, not year-1 yields', () => {
  const base = simulateProjection({ ...DEFAULTS })
  const rent = simulateProjection({ ...DEFAULTS, rentGrowthPct: 10 })
  const exp = simulateProjection({ ...DEFAULTS, expenseGrowthRatePct: 10 })
  assert.equal(rent.netYield, base.netYield)
  assert.equal(rent.effectiveGrossIncomes[0], base.effectiveGrossIncomes[0])
  assert.ok(rent.effectiveGrossIncomes[1] > base.effectiveGrossIncomes[1])
  assert.ok(rent.irr > base.irr)
  assert.ok(rent.totalNetProfit > base.totalNetProfit)
  assert.ok(exp.operatingExpensesByYear[1] > base.operatingExpensesByYear[1])
  assert.ok(exp.irr < base.irr)
})

  it('year-1 tax breakdown: reduction applies to the net base; amortization used sums the hold', () => {
  const r = simulateProjection({ ...DEFAULTS, rentalReductionPct: 60 })
  assert.ok(Math.abs(r.taxBaseByYear[0] - r.netBaseByYear[0] * 0.4) < 1e-9)
  const sum = r.amortizationByYear.slice(0, r.holdYears).reduce((s, v) => s + v, 0)
  assert.ok(Math.abs(r.amortizationUsed - sum) < 1e-9)
  assert.ok(Math.abs(r.totalCashReceivedAfterTax - r.initialCashOutlay - r.totalNetProfit) < 1e-6)
})
})

describe('buildVerdict', () => {
  const verdict = (over, bench = 3) => {
    const r = sim(over)
    return buildVerdict(r, sim({ ...over, appreciationRatePct: 0 }), bench)
  }
  it('default scenario splits the profit between growth and rent', () => {
    const r = sim({})
    const v = verdict({})
    assert.equal(v.kind, 'mixed')
    near(v.growthProfit + v.rentProfit, r.totalNetProfit, 1e-6)
    assert.ok(v.growthSharePct > 0 && v.growthSharePct < 100)
    near(v.irrGap, r.irr - 3, 1e-9)
  })
  it('no price growth -> all from rent', () => {
    const v = verdict({ appreciationRatePct: 0 })
    assert.equal(v.kind, 'rent_only')
    assert.equal(v.growthSharePct, 0)
  })
  it('rent that loses money -> all from growth', () => {
    const v = verdict({ monthlyRent: 200, rentGrowthPct: 0, appreciationRatePct: 6 })
    assert.equal(v.kind, 'growth_only')
    assert.ok(v.rentProfit <= 0)
    assert.equal(v.growthSharePct, 100)
  })
  it('loss and benchmark comparison', () => {
    const v = verdict({ monthlyRent: 150, rentGrowthPct: 0, appreciationRatePct: 0 }, 50)
    assert.equal(v.kind, 'loss')
    assert.equal(v.beatsBenchmark, false)
  })
})
