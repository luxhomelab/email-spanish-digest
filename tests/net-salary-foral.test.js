import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import {
  calcBasqueWorkBonus, calcNavarraWorkDeduction, calcForalIrpf, calcForalWithholding, FORAL_REGIONS,
} from '../static/js/net-salary-foral.js'
import { calculateNetSalary, compareRegions, REGION_IDS } from '../static/js/net-salary-calc.js'
import { DEFAULTS } from '../static/js/net-salary-form.js'

const near = (a, b, eps = 0.01) => assert.ok(Math.abs(a - b) <= eps, `${a} != ${b}`)
const calc = over => calculateNetSalary({ ...DEFAULTS, ...over })
const base = { age: 'u65', disability: '0', kids: 0, kidsU3: 0, descDisab: [], asc65: 0, asc75: 0, ascDisab: [], contract: 'permanent' }

describe('foral regions', () => {
  it('Navarra and the Basque Country are selectable regions', () => {
    for (const id of FORAL_REGIONS) assert.ok(REGION_IDS.includes(id), id)
  })
})

describe('Basque Country (NF 13/2013, DF 134/2025)', () => {
  it('work bonus: 8,000 up to 14,800 net, tapering to 3,000 at 23,000 (legatiq: 18,000 − 1,170 SS → 6,762.11)', () => {
    near(calcBasqueWorkBonus(14000), 8000)
    near(calcBasqueWorkBonus(16830), 6762.11, 0.02)
    near(calcBasqueWorkBonus(30000), 3000)
  })

  it('30,000 € single: base 25,050, scale 6,110, minus 1,615 general deduction → 4,495', () => {
    const r = calcForalIrpf({ ...base, region: 'pais_vasco', rit: 30000, ss: 1950 })
    near(r.baseLiquidable, 25050)
    near(r.cuotaIntegra, 6110)
    near(r.total, 4495)
  })

  it('child deductions come off the tax (682 first, 844 second)', () => {
    const r = calcForalIrpf({ ...base, region: 'pais_vasco', rit: 30000, ss: 1950, kids: 2 })
    near(r.total, 4495 - 682 - 844)
  })

  it('withholding uses the Bizkaia 2026 table: 15% at 30,000, 14% with one child, 0 up to 20,000', () => {
    assert.equal(calcForalWithholding({ ...base, region: 'pais_vasco', rit: 30000 }).rate, 15)
    assert.equal(calcForalWithholding({ ...base, region: 'pais_vasco', rit: 30000, kids: 1 }).rate, 14)
    assert.equal(calcForalWithholding({ ...base, region: 'pais_vasco', rit: 20000 }).rate, 0)
  })

  it('full calculation: 30,000 € → 4,500 withheld, 5 € back at the Renta', () => {
    const r = calc({ gross: 30000, region: 'pais_vasco' })
    near(r.withholding.annual, 4500)
    near(r.irpf.total, 4495)
    near(r.refund, 5)
  })
})

describe('Navarra (DFL 4/2008, LF 17/2025, DF 148/2025)', () => {
  it('work deduction: 1,400 to 12,500, 1,400 − 0.14 × excess to 17,500, 700 to 35,000, 400 above 50,000', () => {
    near(calcNavarraWorkDeduction(12000), 1400)
    near(calcNavarraWorkDeduction(15000), 1050)
    near(calcNavarraWorkDeduction(28050), 700)
    near(calcNavarraWorkDeduction(40000), 600)
    near(calcNavarraWorkDeduction(60000), 400)
  })

  it('30,000 € single (legatiq worked example): cuota íntegra 6,516.63, − 700 work, − 1,410.28 minimum → 4,406.35', () => {
    const r = calcForalIrpf({ ...base, region: 'navarra', rit: 30000, ss: 1950 })
    near(r.cuotaIntegra, 6516.63, 0.05)
    near(r.total, 4406.35, 0.05)
  })

  it('16,000 € pays no IRPF and has nothing withheld', () => {
    near(calcForalIrpf({ ...base, region: 'navarra', rit: 16000, ss: 1040 }).total, 0)
    assert.equal(calcForalWithholding({ ...base, region: 'navarra', rit: 16000 }).rate, 0)
  })

  it('withholding uses the Navarra 2026 table: 14.6% at 30,000, 13.3% with one child', () => {
    assert.equal(calcForalWithholding({ ...base, region: 'navarra', rit: 30000 }).rate, 14.6)
    assert.equal(calcForalWithholding({ ...base, region: 'navarra', rit: 30000, kids: 1 }).rate, 13.3)
  })

  it('temporary contracts withhold at least 2%', () => {
    assert.equal(calcForalWithholding({ ...base, region: 'navarra', rit: 16000, contract: 'temporary' }).rate, 2)
  })
})

describe('region comparison includes foral regions', () => {
  it('ranks Navarra and the Basque Country with the rest', () => {
    const ids = compareRegions({ ...DEFAULTS, gross: 30000 }).map(x => x.region)
    assert.ok(ids.includes('navarra') && ids.includes('pais_vasco'))
  })
})

describe('foral joint returns and family cases', () => {
  const pv = over => calcForalIrpf({ ...base, region: 'pais_vasco', rit: 30000, ss: 1950, ...over })
  const na = over => calcForalIrpf({ ...base, region: 'navarra', rit: 30000, ss: 1950, ...over })

  it('Basque joint return (married or single parent) takes 4,896 € off the base', () => {
    for (const joint of ['married', 'single']) {
      const r = pv({ joint, kids: joint === 'single' ? 1 : 0 })
      near(r.jointReduction, 4896)
      near(r.baseLiquidable, 25050 - 4896)
    }
  })

  it('Navarra joint with a spouse without income adds the spouse’s own personal minimum (1,084 + 1,280)', () => {
    near(na({ joint: 'married' }).total, 4406.35 - 2364, 0.05)
  })

  it('Navarra single-parent joint return raises the personal minimum by 668 €', () => {
    near(na({ joint: 'none', kids: 1 }).total - na({ joint: 'single', kids: 1 }).total, 668)
  })

  it('Navarra disabled descendants and ascendants: 674 € (33–64%), 2,360 € (65%+)', () => {
    near(na({}).total - na({ descDisab: ['33'] }).total, 674)
    near(na({}).total - na({ ascDisab: ['65'] }).total, 2360)
  })

  it('Navarra pension: 50% of net income limit at 65+ (30% otherwise)', () => {
    const young = na({ rit: 4000, ss: 0, pensionEmployee: 1500 })
    const old = na({ rit: 4000, ss: 0, pensionEmployee: 1500, age: '65to74' })
    near(young.pensionReduction, 1200)
    near(old.pensionReduction, 1500)
  })

  it('Navarra descendant minimum is 40% higher on rentas up to 20,000 €', () => {
    const low = { rit: 19000, ss: 1235 }
    near(na({ ...low }).total - na({ ...low, kids: 1 }).total, Math.min(483 * 1.4, na({ ...low }).total))
  })

  it('full calculation in the user’s scenario: married joint return is no longer ignored in the Basque Country', () => {
    const s = { gross: 37628.88, region: 'pais_vasco', age: '75plus', contract: 'temporary', disability: '65', meals: 11 }
    assert.ok(calc({ ...s, joint: 'married' }).irpf.total < calc({ ...s, joint: 'none' }).irpf.total)
  })
})
