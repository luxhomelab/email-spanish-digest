import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import {
  calcEmployeeSS, calcEmployerSS, calcWorkReduction, calcOtherExpenses, calcSmiDeduction,
  calcMinimums, calcAnnualIrpf, calcWithholding, calculateNetSalary, compareRegions,
  grossFromNet, resolveGross, REGION_IDS,
} from '../static/js/net-salary-calc.js'
import { DEFAULTS } from '../static/js/net-salary-form.js'

const near = (a, b, eps = 0.01) => assert.ok(Math.abs(a - b) <= eps, `${a} != ${b}`)
const calc = over => calculateNetSalary({ ...DEFAULTS, ...over })

// ── Social Security (Orden PJC/297/2026) ─────────────────────────────────────

describe('employee Social Security', () => {
  it('permanent contract: 4.70 + 1.55 + 0.10 + 0.15 MEI = 6.50% (tecalculo 24k → 1.560)', () => {
    const ss = calcEmployeeSS({ annualRemuneration: 24000, contract: 'permanent' })
    near(ss.total, 1560)
    near(ss.lines.cc, 1128)
    near(ss.lines.unemployment, 372)
    near(ss.lines.fp, 24)
    near(ss.lines.mei, 36)
    near(ss.lines.solidarity, 0)
    near(ss.monthlyBase, 2000)
    assert.equal(ss.capped, false)
  })

  it('temporary contract: unemployment 1.60% → 6.55%', () => {
    near(calcEmployeeSS({ annualRemuneration: 24000, contract: 'temporary' }).total, 1572)
  })

  it('base is capped at 5.101,20 €/month and the solidarity fee applies above it', () => {
    const ss = calcEmployeeSS({ annualRemuneration: 80000, contract: 'permanent' })
    near(ss.monthlyBase, 5101.2)
    assert.equal(ss.capped, true)
    near(ss.lines.cc + ss.lines.unemployment + ss.lines.fp + ss.lines.mei, 61214.4 * 0.065)
    // Monthly excess 6.666,67 − 5.101,20 = 1.565,47: 510,12 @1,15% + 1.055,35 @1,25%,
    // employee share 4,70/28,30 of each rate.
    const excess = 80000 / 12 - 5101.2
    const monthly = (510.12 * 0.0115 + (excess - 510.12) * 0.0125) * (4.7 / 28.3)
    near(ss.lines.solidarity, monthly * 12, 0.02)
  })

  it('solidarity third band (> 50% above the cap) is 1,46%', () => {
    const ss = calcEmployeeSS({ annualRemuneration: 150000, contract: 'permanent' })
    const excess = 150000 / 12 - 5101.2
    const monthly = (510.12 * 0.0115 + 2040.48 * 0.0125 + (excess - 2550.6) * 0.0146) * (4.7 / 28.3)
    near(ss.lines.solidarity, monthly * 12, 0.02)
  })
})

describe('employer Social Security', () => {
  it('23.60 + 5.50 + 0.20 FOGASA + 0.60 FP + 0.75 MEI + 1.50 AT/EP = 32,15% (tecalculo 24k → 7.716)', () => {
    const er = calcEmployerSS({ annualRemuneration: 24000, contract: 'permanent', atRate: 1.5 })
    near(er.total, 7716)
    near(er.lines.atep, 360)
  })

  it('temporary contract: unemployment 6.70%', () => {
    const er = calcEmployerSS({ annualRemuneration: 24000, contract: 'temporary', atRate: 1.5 })
    near(er.lines.unemployment, 24000 * 0.067)
  })
})

// ── IRPF building blocks (LIRPF arts. 19, 20, 56-61; DA 61ª) ─────────────────

describe('reducción por obtención de rendimientos del trabajo (art. 20)', () => {
  it('7.302 up to 14.852', () => near(calcWorkReduction(14852), 7302))
  it('7.302 − 1,75 × excess up to 17.673,52', () => near(calcWorkReduction(17673.52), 2364.34))
  it('2.364,34 − 1,14 × excess below 19.747,50', () => near(calcWorkReduction(18000), 1992.15))
  it('zero from 19.747,50', () => near(calcWorkReduction(19747.5), 0))
})

describe('otros gastos deducibles (art. 19.2.f)', () => {
  it('2.000 general', () => near(calcOtherExpenses({ netBeforeExpenses: 30000 }), 2000))
  it('+2.000 for geographic mobility', () => near(calcOtherExpenses({ netBeforeExpenses: 30000, mobility: true }), 4000))
  it('+3.500 for a disabled worker 33-65%', () => near(calcOtherExpenses({ netBeforeExpenses: 30000, disability: '33' }), 5500))
  it('+7.750 for ≥65% or 33% with assistance', () => {
    near(calcOtherExpenses({ netBeforeExpenses: 30000, disability: '65' }), 9750)
    near(calcOtherExpenses({ netBeforeExpenses: 30000, disability: '33h' }), 9750)
  })
  it('never exceeds the net income', () => near(calcOtherExpenses({ netBeforeExpenses: 1500 }), 1500))
})

describe('deducción SMI 2026 (DA 61ª LIRPF, RDL 5/2026)', () => {
  it('590,89 up to 17.094', () => near(calcSmiDeduction(17094), 590.89))
  it('590,89 − 0,2 × excess', () => near(calcSmiDeduction(18000), 409.69))
  it('zero from 20.048,45', () => near(calcSmiDeduction(20048.45), 0))
})

describe('mínimo personal y familiar', () => {
  const none = { age: 'u65', disability: '0', kidsU3: 0, kids: 0, sharedCustody: false, descDisab: [], asc65: 0, asc75: 0, ascDisab: [] }

  it('state 5.550; Madrid 5.956,65 (AEAT cuadro comparativo)', () => {
    near(calcMinimums(none, 'madrid').state, 5550)
    near(calcMinimums(none, 'madrid').regional, 5956.65)
  })

  it('regions without their own minimums use the state amounts', () => {
    near(calcMinimums(none, 'catalunya').regional, 5550)
    near(calcMinimums(none, 'murcia').regional, 5550)
  })

  it('age increments 65+ and 75+', () => {
    near(calcMinimums({ ...none, age: '65to74' }, 'murcia').state, 6700)
    near(calcMinimums({ ...none, age: '75plus' }, 'murcia').state, 8100)
  })

  it('children: 2.400 / 2.700 / 4.000 / 4.500 plus 2.800 per child under 3', () => {
    // 1 under 3 + 3 older = 4 children
    near(calcMinimums({ ...none, kidsU3: 1, kids: 3 }, 'murcia').state, 5550 + 2400 + 2700 + 4000 + 4500 + 2800)
  })

  it('shared custody halves the descendant minimum', () => {
    near(calcMinimums({ ...none, kids: 1, sharedCustody: true }, 'murcia').state, 5550 + 1200)
  })

  it('Madrid regional descendant amounts', () => {
    near(calcMinimums({ ...none, kidsU3: 1, kids: 1 }, 'madrid').regional, 5956.65 + 2575.85 + 2897.83 + 3005.16)
  })

  it('ascendants: 1.150 each, +1.400 if 75+', () => {
    near(calcMinimums({ ...none, asc65: 1, asc75: 1 }, 'murcia').state, 5550 + 1150 + 1150 + 1400)
  })

  it('worker disability: 3.000 / 9.000, +3.000 assistance for ≥65% or 33% with help', () => {
    near(calcMinimums({ ...none, disability: '33' }, 'murcia').state, 8550)
    near(calcMinimums({ ...none, disability: '33h' }, 'murcia').state, 11550)
    near(calcMinimums({ ...none, disability: '65' }, 'murcia').state, 17550)
  })

  it('disabled descendants add their disability amounts (halved when shared)', () => {
    near(calcMinimums({ ...none, kids: 1, descDisab: ['65'] }, 'murcia').state, 5550 + 2400 + 12000)
    near(calcMinimums({ ...none, kids: 1, sharedCustody: true, descDisab: ['33'] }, 'murcia').state, 5550 + 1200 + 1500)
  })

  it('a disabled ascendant under 65 still counts as an ascendant (1.150)', () => {
    near(calcMinimums({ ...none, ascDisab: ['33'] }, 'murcia').state, 5550 + 1150 + 3000)
    // already counted in asc65: no second 1.150
    near(calcMinimums({ ...none, asc65: 1, ascDisab: ['33'] }, 'murcia').state, 5550 + 1150 + 3000)
  })
})

// ── Annual IRPF (what the Renta settles) ─────────────────────────────────────

describe('annual IRPF', () => {
  it('tecalculo oracle: 24.000 €, Madrid, single, 12 payslips', () => {
    const r = calc({ gross: 24000, region: 'madrid' })
    near(r.ss.total, 1560)
    near(r.irpf.baseLiquidable, 20440)
    near(r.irpf.state, 1621.5)
    near(r.irpf.regional, 1416.94)
    near(r.irpf.total, 3038.44)
    near(r.annualTaxNet, 19401.56)
  })

  it('tecalculo oracle: 40.000 € Madrid and Catalunya', () => {
    const mad = calc({ gross: 40000, region: 'madrid' })
    near(mad.irpf.baseLiquidable, 35400)
    near(mad.irpf.state, 3872.5)
    near(mad.irpf.regional, 3331.82)
    near(mad.annualTaxNet, 30195.68)
    near(mad.employer.totalCost, 52860)
    near(calc({ gross: 40000, region: 'catalunya' }).irpf.regional, 4063.75)
  })

  it('tecalculo oracle: 70.000 € Madrid, above the SS cap', () => {
    const r = calc({ gross: 70000, region: 'madrid' })
    near(r.ss.lines.solidarity, 17.22)
    near(r.ss.total - r.ss.lines.solidarity, 3978.94)
    near(r.irpf.total, 17839.25, 0.02)
    near(r.annualTaxNet, 48164.59)
    near(r.employer.totalCost, 89766.9, 0.05)
  })

  it('applies the art. 20 reduction near the SMI and the SMI deduction', () => {
    const r = calc({ gross: 18000, region: 'madrid' })
    // ss 1.170 → RN 16.830; red20 3.840,50; gastos 2.000 → BL 10.989,50
    near(r.irpf.workReduction, 3840.5)
    near(r.irpf.baseLiquidable, 10989.5)
    near(r.irpf.cuotaIntegra, (1044.0025 - 527.25) + (934.1075 - 506.31525), 0.02)
    near(r.irpf.smiDeduction, 409.69)
    near(r.irpf.total, r.irpf.cuotaIntegra - 409.69, 0.02)
  })

  it('joint taxation (married, spouse without income) reduces the base by 3.400', () => {
    const r = calc({ gross: 40000, region: 'murcia', joint: 'married' })
    const s = calc({ gross: 40000, region: 'murcia' })
    near(s.irpf.baseLiquidable - r.irpf.baseLiquidable, 3400)
  })

  it('single-parent joint taxation reduces the base by 2.150', () => {
    const r = calc({ gross: 40000, region: 'murcia', joint: 'single', kids: 1 })
    const s = calc({ gross: 40000, region: 'murcia', kids: 1 })
    near(s.irpf.baseLiquidable - r.irpf.baseLiquidable, 2150)
  })

  it('employee pension contributions reduce the base, capped at 1.500', () => {
    const r = calc({ gross: 40000, region: 'murcia', pensionEmployee: 3000 })
    const s = calc({ gross: 40000, region: 'murcia' })
    near(s.irpf.baseLiquidable - r.irpf.baseLiquidable, 1500)
  })

  it('employer pension contributions are taxable in kind, cotizan, and are deductible', () => {
    const r = calc({ gross: 40000, region: 'murcia', pensionEmployer: 2000 })
    const s = calc({ gross: 40000, region: 'murcia' })
    near(r.ss.total - s.ss.total, 2000 * 0.065)
    // income +2.000 in kind, base −2.000 reduction: the base only drops by the extra SS
    near(s.irpf.baseLiquidable - r.irpf.baseLiquidable, 130)
  })

  it('Ceuta and Melilla pay 40% of the cuota (art. 68.4)', () => {
    const r = calc({ gross: 24000, region: 'ceuta' })
    near(r.irpf.total, (1621.5 + 1621.5) * 0.4)
  })

  it('Beckham: 24% of gross up to 600.000, 47% above, no deductions', () => {
    near(calc({ gross: 100000, regime: 'beckham' }).irpf.total, 24000)
    near(calc({ gross: 700000, regime: 'beckham' }).irpf.total, 600000 * 0.24 + 100000 * 0.47)
  })

  it('never negative at very low income', () => {
    const r = calc({ gross: 8000 })
    assert.equal(r.irpf.total, 0)
  })
})

// ── Withholding (AEAT "Algoritmo de cálculo del tipo de retención 2026") ─────

describe('withholding', () => {
  it('24.000 single permanent: base 20.440, cuota 3.243 → 13,51%', () => {
    const w = calc({ gross: 24000 }).withholding
    near(w.base, 20440)
    near(w.cuota, 3243)
    assert.equal(w.rate, 13.51)
    near(w.annual, 3242.4)
  })

  it('exempt below the límite excluyente (situación 3, no children: 15.876)', () => {
    assert.equal(calc({ gross: 15000 }).withholding.rate, 0)
  })

  it('43% cap on the excess over the límite excluyente', () => {
    const w = calc({ gross: 17000 }).withholding
    assert.ok(w.cuota <= (17000 - 15876) * 0.43 + 0.001)
  })

  it('temporary contract minimum 2%', () => {
    assert.equal(calc({ gross: 16500, contract: 'temporary' }).withholding.rate, 2)
  })

  it('more than two descendants reduce the base by 600', () => {
    const a = calc({ gross: 40000, kids: 3 }).withholding
    const b = calc({ gross: 40000, kids: 2 }).withholding
    near(b.base - a.base, 600)
  })

  it('withholding uses state minimums whatever the region', () => {
    assert.equal(calc({ gross: 40000, region: 'madrid' }).withholding.rate,
      calc({ gross: 40000, region: 'catalunya' }).withholding.rate)
  })

  it('Ceuta: 40% of the cuota', () => {
    const w = calc({ gross: 24000, region: 'ceuta' }).withholding
    assert.equal(w.rate, 5.4)
  })

  it('Beckham: flat 24%', () => {
    assert.equal(calc({ gross: 100000, regime: 'beckham' }).withholding.rate, 24)
  })

  it('refund = withheld − annual tax', () => {
    const r = calc({ gross: 24000, region: 'madrid' })
    near(r.refund, r.withholding.annual - r.irpf.total)
  })
})

// ── Payslips ─────────────────────────────────────────────────────────────────

describe('payslips', () => {
  it('12 payslips', () => {
    const r = calc({ gross: 24000, payments: '12' })
    near(r.payslip.regular, (24000 - 1560 - r.withholding.annual) / 12)
    assert.equal(r.payslip.extra, null)
  })

  it('14 payslips: SS is spread over the 12 ordinary months, extras only withhold IRPF', () => {
    const r = calc({ gross: 28000, payments: '14' })
    const t = r.withholding.rate / 100
    near(r.payslip.extra, 2000 * (1 - t))
    near(r.payslip.regular * 12 + r.payslip.extra * 2, r.netAnnual, 0.05)
  })

  it('14 prorated payslips are 12 equal ones', () => {
    near(calc({ gross: 28000, payments: '14p' }).payslip.regular, calc({ gross: 28000, payments: '12' }).payslip.regular)
  })
})

// ── Flexible pay ─────────────────────────────────────────────────────────────

describe('flexible pay', () => {
  it('salary sacrifice: exempt part leaves IRPF, but still pays SS', () => {
    const r = calc({ gross: 30000, meals: 1500, mealsMode: 'sacrifice' })
    const s = calc({ gross: 30000 })
    near(r.ss.total, s.ss.total)
    near(s.irpf.rit - r.irpf.rit, 1500)
    near(r.cashGross, 28500)
    assert.ok(r.totalValue > s.totalValue)
  })

  it('exemption caps: health 500/person, transport 1.500, meals 11 €/day × 220', () => {
    const r = calc({ gross: 30000, health: 1500, healthPersons: 2, healthMode: 'sacrifice', transport: 2000, transportMode: 'sacrifice', meals: 3000, mealsMode: 'sacrifice' })
    near(r.flex.exempt, 1000 + 1500 + 2420)
    near(r.flex.taxable, 500 + 500 + 580)
  })

  it('extra benefit is paid on top of the gross', () => {
    const r = calc({ gross: 30000, nursery: 2400, nurseryMode: 'extra' })
    near(r.cashGross, 30000)
    near(r.flex.total, 2400)
    near(r.employer.totalCost - calc({ gross: 30000 }).employer.totalCost, 2400 * (1 + 0.3215), 0.05)
  })
})

// ── Outputs ──────────────────────────────────────────────────────────────────

describe('derived outputs', () => {
  it('employer cost (tecalculo 24k → 31.716)', () => near(calc({ gross: 24000 }).employer.totalCost, 31716))

  it('hourly net uses hours per week × 52', () => {
    const r = calc({ gross: 24000, hoursPerWeek: 40 })
    near(r.hourly, r.netAnnual / 2080)
  })

  it('marginal: share of an extra 100 € kept', () => {
    const r = calc({ gross: 40000 })
    assert.ok(r.marginalKeep > 0.5 && r.marginalKeep < 0.7)
  })

  it('compareRegions covers every region, sorted by net after the Renta', () => {
    const rows = compareRegions({ ...DEFAULTS, gross: 40000 })
    assert.equal(rows.length, REGION_IDS.length)
    for (let i = 1; i < rows.length; i++) assert.ok(rows[i - 1].annualTaxNet >= rows[i].annualTaxNet)
    near(rows.find(r => r.region === 'madrid').annualTaxNet, calc({ gross: 40000, region: 'madrid' }).annualTaxNet)
  })

  it('grossFromNet inverts the annual net and the payslip', () => {
    const g = grossFromNet(30000, { ...DEFAULTS }, 'annual')
    near(calc({ gross: g }).netAnnual, 30000, 1)
    const g2 = grossFromNet(2000, { ...DEFAULTS, payments: '14' }, 'payslip')
    near(calc({ gross: g2, payments: '14' }).payslip.regular, 2000, 1)
  })

  it('grossFromNet never lands a cent below the target', () => {
    for (const [target, over] of [[1800, { payments: '14', kidsU3: 1 }], [1800, { payments: '14' }], [25000, {}]]) {
      const metric = target < 5000 ? 'payslip' : 'annual'
      const g = grossFromNet(target, { ...DEFAULTS, ...over }, metric)
      const r = calc({ gross: g, ...over })
      assert.ok((metric === 'payslip' ? r.payslip.regular : r.netAnnual) >= target, `${target} ${JSON.stringify(over)}`)
    }
  })
})

describe('resolveGross (form amount → annual gross)', () => {
  const base = { ...DEFAULTS }
  it('annual gross as typed', () => near(resolveGross({ ...base, amount: 30000 }), 30000))
  it('monthly gross × 12, or × 14 with 14 payslips', () => {
    near(resolveGross({ ...base, amount: 2000, period: 'm' }), 24000)
    near(resolveGross({ ...base, amount: 2000, period: 'm', payments: '14' }), 28000)
    near(resolveGross({ ...base, amount: 2000, period: 'm', payments: '14p' }), 24000)
  })
  it('net mode solves for the gross', () => {
    const g = resolveGross({ ...base, amount: 25000, mode: 'net' })
    near(calculateNetSalary({ ...base, gross: g }).netAnnual, 25000, 1)
    const g2 = resolveGross({ ...base, amount: 1800, mode: 'net', period: 'm', payments: '14' })
    near(calculateNetSalary({ ...base, gross: g2, payments: '14' }).payslip.regular, 1800, 1)
  })
})
