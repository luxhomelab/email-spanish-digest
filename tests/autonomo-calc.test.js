import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import {
  findSSBracket,
  findSSQuota,
  findSSQuotaForCollaborator,
  calcProgressiveTax,
  calcProgressiveTaxWithBreakdown,
  calcIrpfState,
  calcIrpfRegional,
  calcGeneralExpenses,
  calcPersonalMinimum,
  calculateAutonomo,
} from '../static/js/autonomo-calc.js'

// ── findSSBracket ─────────────────────────────────────────────────────────────
describe('findSSBracket', () => {
  it('returns bracket 1 for zero income', () => {
    assert.equal(findSSBracket(0).id, 1)
  })
  it('returns bracket 1 for exactly €670', () => {
    assert.equal(findSSBracket(670).id, 1)
  })
  it('returns bracket 2 for €670.01', () => {
    assert.equal(findSSBracket(670.01).id, 2)
  })
  it('returns bracket 2 for €900', () => {
    assert.equal(findSSBracket(900).id, 2)
  })
  it('returns bracket 3 for €901', () => {
    assert.equal(findSSBracket(901).id, 3)
  })
  it('returns bracket 9 for €2,100', () => {
    assert.equal(findSSBracket(2100).id, 9)
  })
  it('returns bracket 3 for exactly €1,166.70', () => {
    assert.equal(findSSBracket(1166.70).id, 3)
  })
  it('returns bracket 4 for €1,166.71', () => {
    assert.equal(findSSBracket(1166.71).id, 4)
  })
  it('returns bracket 14 for €5,000', () => {
    assert.equal(findSSBracket(5000).id, 14)
  })
  it('returns bracket 15 for €7,000', () => {
    assert.equal(findSSBracket(7000).id, 15)
  })
})

// ── findSSQuota ───────────────────────────────────────────────────────────────
describe('findSSQuota', () => {
  it('returns tarifa plana (€80) for new autonomo', () => {
    const result = findSSQuota(2000, 2026, 'new')
    assert.equal(result.isTarifaPlana, true)
    assert.equal(result.monthlyQuota, 80)
  })

  it('returns tarifa plana for new autonomo regardless of year', () => {
    assert.equal(findSSQuota(2000, 2028, 'new').monthlyQuota, 80)
  })

  it('returns 2026 quota for bracket 1 (established)', () => {
    const result = findSSQuota(500, 2026, 'established')
    assert.equal(result.isTarifaPlana, false)
    assert.equal(result.bracketId, 1)
    assert.equal(result.monthlyQuota, 205.88)
  })

  it('returns 2026 quota for bracket 15 (established)', () => {
    const result = findSSQuota(10000, 2026, 'established')
    assert.equal(result.bracketId, 15)
    assert.equal(result.monthlyQuota, 607.35)
  })

  it('returns same quota for all years (no increases approved beyond 2026)', () => {
    const result2026 = findSSQuota(2500, 2026, 'established')
    const result2028 = findSSQuota(2500, 2028, 'established')
    assert.equal(result2028.monthlyQuota, result2026.monthlyQuota)
  })

  it('returns regular quota (not tarifa plana) for mid autonomo', () => {
    // €1,000/mo > €900 (bracket 2 max) and <= €1,166.70 (bracket 3 max) → bracket 3; quota = 266.80
    const result = findSSQuota(1000, 2026, 'mid')
    assert.equal(result.isTarifaPlana, false)
    assert.equal(result.bracketId, 3)
    assert.equal(result.monthlyQuota, 267.65)
  })
})

// ── calcProgressiveTax ────────────────────────────────────────────────────────
describe('calcProgressiveTax', () => {
  const brackets = [
    { upTo: 10000, rate: 0.10 },
    { upTo: 20000, rate: 0.20 },
    { upTo: Infinity, rate: 0.30 },
  ]

  it('returns 0 for zero base', () => {
    assert.equal(calcProgressiveTax(0, brackets), 0)
  })

  it('returns 0 for negative base', () => {
    assert.equal(calcProgressiveTax(-100, brackets), 0)
  })

  it('calculates single bracket correctly', () => {
    assert.equal(calcProgressiveTax(5000, brackets), 500)
  })

  it('calculates two brackets correctly', () => {
    // 10000 × 0.10 + 5000 × 0.20 = 1000 + 1000 = 2000
    assert.equal(calcProgressiveTax(15000, brackets), 2000)
  })

  it('calculates three brackets correctly', () => {
    // 10000 × 0.10 + 10000 × 0.20 + 5000 × 0.30 = 1000 + 2000 + 1500 = 4500
    assert.equal(calcProgressiveTax(25000, brackets), 4500)
  })
})

// ── calcIrpfState ─────────────────────────────────────────────────────────────
describe('calcIrpfState', () => {
  it('returns 0 for zero income', () => {
    assert.equal(calcIrpfState(0), 0)
  })

  it('returns correct tax for income within first bracket (€10,000)', () => {
    // 10000 × 9.5% = 950
    assert.equal(calcIrpfState(10000), 950)
  })

  it('returns correct tax at exact first bracket boundary (€12,450)', () => {
    // 12450 × 0.095 = 1182.75
    assert.equal(calcIrpfState(12450), 1182.75)
  })

  it('returns correct tax for income spanning two brackets (€15,000)', () => {
    // 12450 × 0.095 + 2550 × 0.12 = 1182.75 + 306 = 1488.75
    assert.equal(calcIrpfState(15000), 1488.75)
  })

  it('returns correct tax at exact second bracket boundary (€20,200)', () => {
    // 12450 × 0.095 + 7750 × 0.12 = 1182.75 + 930 = 2112.75
    assert.equal(calcIrpfState(20200), 2112.75)
  })

  it('returns correct tax at exact third bracket boundary (€35,200)', () => {
    // 12450 × 0.095 + 7750 × 0.12 + 15000 × 0.15 = 1182.75 + 930 + 2250 = 4362.75
    assert.equal(calcIrpfState(35200), 4362.75)
  })

  it('returns correct tax for €30,000', () => {
    // 12450 × 0.095 + 7750 × 0.12 + 9800 × 0.15 = 1182.75 + 930 + 1470 = 3582.75
    assert.equal(calcIrpfState(30000), 3582.75)
  })
})

// ── calcIrpfRegional ──────────────────────────────────────────────────────────
describe('calcIrpfRegional', () => {
  it('returns 0 for zero income', () => {
    assert.equal(calcIrpfRegional(0, 'madrid'), 0)
  })

  it('Madrid has lower regional tax than Catalunya for same income', () => {
    const base = 40000
    assert.ok(calcIrpfRegional(base, 'madrid') < calcIrpfRegional(base, 'catalunya'))
  })

  it('falls back to default rates for unknown region', () => {
    // DEFAULT_REGIONAL_BRACKETS mirrors state bracket structure
    // Tax(30000) = 12450×0.095 + 7750×0.12 + 9800×0.15 = 1182.75 + 930 + 1470 = 3582.75
    const result = calcIrpfRegional(30000, 'unknown_region')
    assert.equal(result, 3582.75)
  })
})

// ── calcGeneralExpenses ───────────────────────────────────────────────────────
describe('calcGeneralExpenses', () => {
  it('returns 7% for individual autonomo', () => {
    assert.equal(calcGeneralExpenses(20000, 'individual'), 1400)
  })

  it('caps at €2,000 for individual autonomo with high revenue', () => {
    assert.equal(calcGeneralExpenses(40000, 'individual'), 2000)
  })

  it('returns 3% for company director', () => {
    assert.equal(calcGeneralExpenses(20000, 'director'), 600)
  })

  it('caps at €2,000 for director with high revenue', () => {
    // 3% of 70000 = 2100 → capped at 2000
    assert.equal(calcGeneralExpenses(70000, 'director'), 2000)
  })

  it('returns 0 for zero revenue', () => {
    assert.equal(calcGeneralExpenses(0, 'individual'), 0)
  })

  it('falls back to 7% rate for unknown autonomoType', () => {
    // falls back to 0.07: 10000 × 0.07 = 700
    assert.equal(calcGeneralExpenses(10000, 'unknown'), 700)
  })
})

// ── calcPersonalMinimum ───────────────────────────────────────────────────────
describe('calcPersonalMinimum', () => {
  it('returns base personal minimum for no special circumstances', () => {
    assert.equal(calcPersonalMinimum({ age: 35, numChildren: 0, childrenUnder3: 0, disabilityLevel: 0 }), 5550)
  })

  it('adds age 65+ allowance at exactly age 65', () => {
    assert.equal(calcPersonalMinimum({ age: 65, numChildren: 0, childrenUnder3: 0, disabilityLevel: 0 }), 5550 + 1150)
  })

  it('adds age 65+ allowance', () => {
    assert.equal(calcPersonalMinimum({ age: 66, numChildren: 0, childrenUnder3: 0, disabilityLevel: 0 }), 5550 + 1150)
  })

  it('adds age 75+ allowance at exactly age 75', () => {
    assert.equal(calcPersonalMinimum({ age: 75, numChildren: 0, childrenUnder3: 0, disabilityLevel: 0 }), 5550 + 1150 + 1400)
  })

  it('adds age 75+ allowance (65 extra + 75 extra)', () => {
    assert.equal(calcPersonalMinimum({ age: 76, numChildren: 0, childrenUnder3: 0, disabilityLevel: 0 }), 5550 + 1150 + 1400)
  })

  it('adds child allowances correctly (2 children)', () => {
    // 5550 + 2400 + 2700 = 10650
    assert.equal(calcPersonalMinimum({ age: 35, numChildren: 2, childrenUnder3: 0, disabilityLevel: 0 }), 10650)
  })

  it('adds child allowances correctly (3 children)', () => {
    // 5550 + 2400 + 2700 + 4000 = 14650
    assert.equal(calcPersonalMinimum({ age: 35, numChildren: 3, childrenUnder3: 0, disabilityLevel: 0 }), 14650)
  })

  it('adds child allowances correctly (4+ children use capped allowance)', () => {
    // 5550 + 2400 + 2700 + 4000 + 4500 = 19150
    assert.equal(calcPersonalMinimum({ age: 35, numChildren: 4, childrenUnder3: 0, disabilityLevel: 0 }), 19150)
  })

  it('adds child-under-3 extra allowance', () => {
    // 5550 + 2400 + 2800 = 10750
    assert.equal(calcPersonalMinimum({ age: 35, numChildren: 1, childrenUnder3: 1, disabilityLevel: 0 }), 10750)
  })

  it('clamps childrenUnder3 to numChildren when over-supplied', () => {
    // childrenUnder3: 3 with numChildren: 1 → clamps to 1 under-3 child
    // 5550 + 2400 + 2800 = 10750 (same as 1 child + 1 under-3)
    assert.equal(calcPersonalMinimum({ age: 35, numChildren: 1, childrenUnder3: 3, disabilityLevel: 0 }), 10750)
  })

  it('no disability allowance below threshold (level 32)', () => {
    assert.equal(calcPersonalMinimum({ age: 35, numChildren: 0, childrenUnder3: 0, disabilityLevel: 32 }), 5550)
  })

  it('adds disability allowance at 33%', () => {
    assert.equal(calcPersonalMinimum({ age: 35, numChildren: 0, childrenUnder3: 0, disabilityLevel: 33 }), 5550 + 3000)
  })

  it('adds 33% (not 65%) disability allowance at level 64', () => {
    assert.equal(calcPersonalMinimum({ age: 35, numChildren: 0, childrenUnder3: 0, disabilityLevel: 64 }), 5550 + 3000)
  })

  it('adds disability allowance at 65%', () => {
    assert.equal(calcPersonalMinimum({ age: 35, numChildren: 0, childrenUnder3: 0, disabilityLevel: 65 }), 5550 + 9000)
  })

  it('combines age + children + disability', () => {
    // 5550 + 1150 + 2400 + 3000 = 12100
    assert.equal(calcPersonalMinimum({ age: 67, numChildren: 1, childrenUnder3: 0, disabilityLevel: 33 }), 12100)
  })
})

// ── calculateAutonomo (integration) ──────────────────────────────────────────
describe('calculateAutonomo', () => {
  const base = {
    annualNetRevenue: 30000, autonomoType: 'individual', timeAsAutonomo: 'established',
    region: 'madrid', year: 2026, age: 35, numChildren: 0, childrenUnder3: 0, disabilityLevel: 0,
  }

  it('returns all expected keys', () => {
    const result = calculateAutonomo(base)
    const expectedKeys = [
      'monthlyNetIncome', 'ssBracketId', 'isTarifaPlana', 'monthlySSQuota',
      'annualSSTotal', 'generalExpensesDeduction', 'reducedNetIncome',
      'personalMinimum', 'irpfBase', 'irpfState', 'irpfRegional', 'irpfTotal',
      'effectiveIrpfRate', 'totalBurden', 'effectiveTotalRate',
      'netTakeHome', 'netTakeHomeMonthly',
    ]
    expectedKeys.forEach(key => assert.ok(result !== undefined && result !== null && (key) in Object(result) ? true : JSON.stringify(result).includes(key)))
  })

  it('irpfBase equals reducedNetIncome (personal minimum reduces tax, not base)', () => {
    const result = calculateAutonomo(base)
    assert.equal(result.irpfBase, result.reducedNetIncome)
  })

  it('net take-home + total burden = annual revenue', () => {
    const result = calculateAutonomo({ ...base, annualNetRevenue: 40000, region: 'andalucia', age: 40, numChildren: 1 })
    assert.ok(Math.abs(result.netTakeHome + result.totalBurden - 40000) < 0.02)
  })

  it('tarifa plana (€80/mo) reduces SS for new autonomo vs established', () => {
    const newResult = calculateAutonomo({ ...base, timeAsAutonomo: 'new' })
    const estResult = calculateAutonomo(base)
    assert.ok(newResult.annualSSTotal < estResult.annualSSTotal)
    assert.equal(newResult.isTarifaPlana, true)
    assert.equal(newResult.monthlySSQuota, 80)
  })

  it('director has lower general expenses deduction than individual', () => {
    const individual = calculateAutonomo(base)
    const director = calculateAutonomo({ ...base, autonomoType: 'director' })
    assert.ok(individual.generalExpensesDeduction > director.generalExpensesDeduction)
  })

  it('more children → lower IRPF (personal minimum reduces tax)', () => {
    const noChildren = calculateAutonomo(base)
    const twoChildren = calculateAutonomo({ ...base, numChildren: 2 })
    assert.ok(twoChildren.irpfTotal < noChildren.irpfTotal)
  })

  it('zero income returns zero IRPF, zero take-home, and zero effective rates', () => {
    const result = calculateAutonomo({ ...base, annualNetRevenue: 0 })
    assert.equal(result.irpfTotal, 0)
    assert.equal(result.netTakeHome, 0)
    assert.equal(result.effectiveIrpfRate, 0)
    assert.equal(result.effectiveTotalRate, 0)
  })

  it('negative annualNetRevenue is clamped to zero', () => {
    const result = calculateAutonomo({ ...base, annualNetRevenue: -5000 })
    assert.equal(result.netTakeHome, 0)
    assert.equal(result.irpfTotal, 0)
    // SS still charges minimum bracket quota even when revenue is treated as 0
    assert.ok(result.annualSSTotal > 0)
  })

  it('very high income (€200k) has positive IRPF and effective rate > 30%', () => {
    const result = calculateAutonomo({ ...base, annualNetRevenue: 200000 })
    assert.ok(result.irpfTotal > 0)
    assert.ok(result.netTakeHome > 0)
    assert.ok(result.effectiveTotalRate > 0.3)
  })

  it('monthly net take-home is annual / 12', () => {
    const result = calculateAutonomo({ ...base, annualNetRevenue: 50000 })
    assert.ok(Math.abs(result.netTakeHomeMonthly - result.netTakeHome / 12) < 0.01)
  })

  it('Madrid has lower total burden than Catalunya for same income', () => {
    const madrid = calculateAutonomo({ ...base, annualNetRevenue: 50000 })
    const cat = calculateAutonomo({ ...base, annualNetRevenue: 50000, region: 'catalunya' })
    assert.ok(madrid.totalBurden < cat.totalBurden)
  })

  it('SS bracket uses income after general expenses deduction', () => {
    // €80k individual: (80000-2000)/12 = 6500 → bracket 15; quota = 607.35
    const result = calculateAutonomo({ ...base, annualNetRevenue: 80000 })
    assert.equal(result.ssBracketId, 15)
    assert.equal(result.monthlySSQuota, 607.35)
  })

  it('IRPF uses Tax(base) - Tax(personalMin) method: state component verified', () => {
    // €80k individual, established, 2026 (madrid for simplicity)
    // generalExpenses = 2000, SS bracket 15 → 607.35/mo → 7288.20/yr
    // irpfBase = 80000 - 7288.20 - 2000 = 70711.80
    // state IRPF = Tax(70711.80) - Tax(5550)
    // Tax(70711.80) = 12450×0.095 + 7750×0.12 + 15000×0.15 + 24800×0.185 + 10711.80×0.225
    //              = 1182.75 + 930 + 2250 + 4588 + 2410.155 = 11360.905
    // Tax(5550) = 5550×0.095 = 527.25 → irpfState = 10833.66
    const result = calculateAutonomo({ ...base, annualNetRevenue: 80000 })
    assert.equal(result.irpfState, 10833.66)
  })

  it('SS cost exceeds revenue, reducedNetIncome clamps to 0', () => {
    // €200/mo = €2400/yr; established → bracket 1 → SS quota 205.23/mo = 2462.76/yr
    // SS cost (2462.76) exceeds revenue (2400)
    // generalExpenses = 168 (7% of 2400)
    // reducedNetIncome = max(0, 2400 - 2462.76 - 168) = max(0, -230.76) = 0 (clamps to zero)
    // This validates that negative income floors at 0 and IRPF follows correctly
    const revenue = 2400
    const result = calculateAutonomo({ ...base, annualNetRevenue: revenue, timeAsAutonomo: 'established' })
    assert.equal(result.ssBracketId, 1)
    assert.equal(result.monthlySSQuota, 205.88)
    assert.ok(result.annualSSTotal > revenue)
    assert.equal(result.reducedNetIncome, 0) // Clamped to zero
    assert.equal(result.irpfTotal, 0) // No IRPF on zero income
    // netTakeHome is clamped to 0 (never negative); effectiveTotalRate can exceed 1.0
    assert.equal(result.netTakeHome, 0)
    assert.ok(result.effectiveTotalRate > 1)
    // Total burden can exceed revenue in this edge case (SS+expenses > revenue)
    assert.ok(result.totalBurden > revenue)
  })

  it('IRPF floored at zero when personal minimum exceeds reduced income (Art. 56 LIRPF)', () => {
    // €6000 low income with 4 children (high personal minimum)
    // personalMinimum = 5550 + 2400 + 2700 + 4000 + 4500 = 19150
    // generalExpenses ≈ 420, SS cost ≈ 280 (using tarifa plana for 'new')
    // reducedNetIncome = 6000 - 280 - 420 ≈ 5300
    // Tax(5300) ≈ 503.50; Tax(19150) ≈ 1818.25 → negative IRPF, floored to 0
    const result = calculateAutonomo({ ...base, annualNetRevenue: 6000, numChildren: 4, timeAsAutonomo: 'new' })
    assert.ok(result.personalMinimum > 15000)
    assert.equal(result.irpfTotal, 0) // Floored at zero
    assert.ok(result.effectiveTotalRate >= 0) // Never negative
  })

  it('timeAsAutonomo "new" uses tarifa plana (€80/mo), while "mid" and "established" use bracket-based quotas', () => {
    // €12000/yr = €1000/mo after general expenses (7% deduction): (12000-840)/12 = €930/mo
    // €930/mo → bracket 3 → quota 266.80/mo (applies to both 'mid' and 'established')
    // €1000/mo is the gross input, but SS bracket lookup uses net monthly income after deductions
    const newAutonomo = calculateAutonomo({ ...base, annualNetRevenue: 12000, timeAsAutonomo: 'new' })
    const midAutonomo = calculateAutonomo({ ...base, annualNetRevenue: 12000, timeAsAutonomo: 'mid' })
    const establishedAutonomo = calculateAutonomo({ ...base, annualNetRevenue: 12000, timeAsAutonomo: 'established' })
    assert.equal(newAutonomo.monthlySSQuota, 80) // Tarifa plana (€80/mo flat for first 12 months)
    assert.equal(midAutonomo.monthlySSQuota, 267.65) // Bracket 3 (after 12 months, months 13–24)
    assert.equal(establishedAutonomo.monthlySSQuota, 267.65) // Same bracket as 'mid' for this income
  })

  it('out-of-range year parameter silently uses 2026 SS quotas — contract for future implementation', () => {
    // getSSQuotasForYear() only knows 2026; a future 2027+ year should still use 2026 until quotas are published
    const result = calculateAutonomo({ ...base, annualNetRevenue: 50000, year: 2030 })
    // If 2030 quotas are not implemented, result must match 2026 quotas
    const expected = calculateAutonomo({ ...base, annualNetRevenue: 50000, year: 2026 })
    assert.equal(result.monthlySSQuota, expected.monthlySSQuota)
    assert.equal(result.ssBracketId, expected.ssBracketId)
  })
})

// ── findSSQuotaForCollaborator ─────────────────────────────────────────────────
describe('findSSQuotaForCollaborator', () => {
  it('returns zero for zero income', () => {
    const result = findSSQuotaForCollaborator(0)
    assert.equal(result.bracketId, 0)
    assert.equal(result.monthlyQuota, 0)
  })

  it('returns zero for negative income', () => {
    const result = findSSQuotaForCollaborator(-100)
    assert.equal(result.bracketId, 0)
    assert.equal(result.monthlyQuota, 0)
  })

  it('uses bracket 1 minimum quota for income ≤ €670/mo', () => {
    const result = findSSQuotaForCollaborator(500)
    assert.equal(result.bracketId, 1)
    assert.equal(result.monthlyQuota, 205.88)
  })

  it('uses correct quota for bracket 4 (€1166.71–€1300)', () => {
    const result = findSSQuotaForCollaborator(1250)
    assert.equal(result.bracketId, 4)
    assert.equal(result.monthlyQuota, 299.56)
  })

  it('uses last bracket for very high income', () => {
    const result = findSSQuotaForCollaborator(100000)
    assert.ok(result.bracketId > 0)
    assert.ok(result.monthlyQuota > 0)
  })

  it('defaults to 2026 year', () => {
    const result = findSSQuotaForCollaborator(1000)
    const explicit = findSSQuotaForCollaborator(1000, 2026)
    assert.equal(result.monthlyQuota, explicit.monthlyQuota)
  })
})

// ── calcProgressiveTaxWithBreakdown ───────────────────────────────────────────
describe('calcProgressiveTaxWithBreakdown', () => {
  const brackets = [
    { upTo: 12450, rate: 0.095 },
    { upTo: 20200, rate: 0.12 },
    { upTo: Infinity, rate: 0.15 },
  ]

  it('returns zero for zero base', () => {
    const result = calcProgressiveTaxWithBreakdown(0, brackets)
    assert.equal(result.total, 0)
    assert.deepEqual(result.brackets, [])
  })

  it('returns zero for negative base', () => {
    const result = calcProgressiveTaxWithBreakdown(-100, brackets)
    assert.equal(result.total, 0)
    assert.deepEqual(result.brackets, [])
  })

  it('total matches calcProgressiveTax', () => {
    const bases = [0, 5000, 12450, 15000, 20200, 35000, 60000, 100000]
    for (const base of bases) {
      const expected = calcProgressiveTax(base, brackets)
      const actual = calcProgressiveTaxWithBreakdown(base, brackets).total
      assert.equal(actual, expected)
    }
  })

  it('sum of breakdown taxAmount entries equals total', () => {
    const bases = [15000, 35000, 100000]
    for (const base of bases) {
      const { total, brackets: breakdown } = calcProgressiveTaxWithBreakdown(base, brackets)
      const sumFromBreakdown = breakdown.reduce((s, b) => s + b.taxAmount, 0)
      assert.ok(Math.abs(sumFromBreakdown - total) < 0.01)
    }
  })

  it('breakdown entries have correct shape', () => {
    const { brackets: breakdown } = calcProgressiveTaxWithBreakdown(35000, brackets)
    for (const entry of breakdown) {
      assert.ok(entry !== undefined && entry !== null && ('from') in Object(entry) ? true : JSON.stringify(entry).includes('from'))
      assert.ok(entry !== undefined && entry !== null && ('to') in Object(entry) ? true : JSON.stringify(entry).includes('to'))
      assert.ok(entry !== undefined && entry !== null && ('rate') in Object(entry) ? true : JSON.stringify(entry).includes('rate'))
      assert.ok(entry !== undefined && entry !== null && ('taxableAmount') in Object(entry) ? true : JSON.stringify(entry).includes('taxableAmount'))
      assert.ok(entry !== undefined && entry !== null && ('taxAmount') in Object(entry) ? true : JSON.stringify(entry).includes('taxAmount'))
      assert.ok(entry.taxableAmount > 0)
      assert.ok(entry.taxAmount >= 0)
    }
  })

  it('income within first bracket has one breakdown entry', () => {
    const { brackets: breakdown } = calcProgressiveTaxWithBreakdown(10000, brackets)
    assert.equal(breakdown.length, 1)
    assert.equal(breakdown[0].rate, 0.095)
    assert.equal(breakdown[0].to, 12450)
  })

  it('income spanning two brackets has two breakdown entries', () => {
    const { brackets: breakdown } = calcProgressiveTaxWithBreakdown(15000, brackets)
    assert.equal(breakdown.length, 2)
  })

  it('last bracket with Infinity has to = null', () => {
    const { brackets: breakdown } = calcProgressiveTaxWithBreakdown(100000, brackets)
    const last = breakdown[breakdown.length - 1]
    assert.equal(last.to, null)
  })
})
