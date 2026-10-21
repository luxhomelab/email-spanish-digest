/**
 * Foral IRPF for employees in Navarra and the Basque Country (2026): pure math, no DOM.
 *
 * Both regions run their own IRPF instead of the state + regional split, and their own
 * withholding tables. Social Security is the same as in the rest of Spain.
 *
 * Sources:
 * - Basque Country: NF 13/2013 (Bizkaia) scale, work bonus (art. 23), general deduction
 *   1,615 € and family deductions as updated for 2026; withholding table DF 134/2025
 *   (bizkaia.eus). Gipuzkoa and Álava use the same table; Álava's family deductions are
 *   slightly higher and are not modelled.
 * - Navarra: DFL 4/2008 scale, LF 17/2025 (work deduction and low-income personal
 *   minimum, art. 62), withholding table DF 148/2025 as corrected in BON 14/2026.
 * Joint returns: Basque base reduction (art. 71 NF 13/2013); Navarra sums the members'
 * individual cuotas (art. 73.3 DFL 4/2008), so a spouse without income only adds their
 * own personal minimum, plus 668 € for single parents (art. 75.4).
 * Not modelled: regional deductions (housing, rent), the Navarra art. 17.2 reduction
 * for other income, the Basque extra for children aged 3 to 5 (the form asks for under 3).
 */
import { calcProgressiveTaxWithBreakdown } from './autonomo-calc.js'

export const FORAL_REGIONS = ['navarra', 'pais_vasco']
export const isForal = region => FORAL_REGIONS.includes(region)

const r2 = x => Math.round(x * 100) / 100
const scaleTax = (base, brackets) => calcProgressiveTaxWithBreakdown(base, brackets)

// ── Basque Country ───────────────────────────────────────────────────────────

export const BASQUE_BRACKETS = [
  { upTo: 18080, rate: 0.23 },
  { upTo: 36160, rate: 0.28 },
  { upTo: 54240, rate: 0.35 },
  { upTo: 77450, rate: 0.40 },
  { upTo: 107260, rate: 0.45 },
  { upTo: 142960, rate: 0.46 },
  { upTo: 208390, rate: 0.47 },
  { upTo: Infinity, rate: 0.49 },
]
const BASQUE = {
  bonus: { max: 8000, lower: 14800, upper: 23000, min: 3000, slope: 0.6098 },
  generalDeduction: 1615,
  kids: [682, 844, 1421, 1680, 2195],
  under6: 394,
  ascendant: 328,
  age: { age65: 393, age75: 714, fullUpTo: 20000, zeroFrom: 30000 },
  disability: { '33': 906, '33h': 1294, '65': 1294 },
  pension: { employee: 5000, total: 10000 },
  // 4,800 € since 2025 for every family unit, deflated 2% for 2026.
  joint: 4896,
}

/** Bonificación de rendimientos del trabajo (art. 23 NF 13/2013), on pay minus SS. */
export function calcBasqueWorkBonus(net, disability = '0') {
  const B = BASQUE.bonus
  let bonus = net <= B.lower ? B.max
    : net < B.upper ? B.max - B.slope * (net - B.lower)
      : B.min
  if (disability === '33') bonus *= 2
  else if (disability === '65' || disability === '33h') bonus *= 3.5
  return r2(Math.min(Math.max(0, bonus), Math.max(0, net)))
}

function basqueIrpf(p) {
  const net = Math.max(0, p.rit - p.ss)
  const workBonus = calcBasqueWorkBonus(net, p.disability)
  const baseImponible = r2(net - workBonus)
  const ownPension = Math.min(p.pensionEmployee || 0, BASQUE.pension.employee)
  const pensionReduction = r2(Math.min(ownPension + (p.pensionEmployer || 0), BASQUE.pension.total, baseImponible))
  const jointReduction = p.joint === 'married' || p.joint === 'single'
    ? Math.min(BASQUE.joint, Math.max(0, baseImponible - pensionReduction)) : 0
  const baseLiquidable = r2(Math.max(0, baseImponible - pensionReduction - jointReduction))
  const scale = scaleTax(baseLiquidable, BASQUE_BRACKETS)

  const share = p.sharedCustody ? 0.5 : 1
  const numKids = (p.kidsU3 || 0) + (p.kids || 0)
  let family = 0
  for (let i = 0; i < numKids; i++) family += BASQUE.kids[Math.min(i, BASQUE.kids.length - 1)] * share
  family += (p.kidsU3 || 0) * BASQUE.under6 * share
  family += ((p.asc65 || 0) + (p.asc75 || 0)) * BASQUE.ascendant
  const A = BASQUE.age
  const ageAmount = p.age === '75plus' ? A.age75 : p.age === '65to74' ? A.age65 : 0
  const ageFactor = baseLiquidable <= A.fullUpTo ? 1
    : baseLiquidable >= A.zeroFrom ? 0 : (A.zeroFrom - baseLiquidable) / (A.zeroFrom - A.fullUpTo)
  family += ageAmount * ageFactor
  family += BASQUE.disability[p.disability] || 0
  for (const level of [...(p.descDisab || []), ...(p.ascDisab || [])]) family += BASQUE.disability[level] || 0

  const deductions = r2(BASQUE.generalDeduction + family)
  const total = r2(Math.max(0, scale.total - deductions))
  return {
    netBeforeExpenses: r2(net), baseImponible, pensionReduction, jointReduction, baseLiquidable, cuotaIntegra: scale.total, total,
    brackets: scale.brackets, marginal: BASQUE_BRACKETS,
    lines: [
      ['− Work income bonus', -workBonus, 'Bonificación: 8,000 € on low pay, 3,000 € from 23,000 €'],
      ['Taxable base', baseImponible, '', 'b'],
      pensionReduction > 0 ? ['− Pension contributions', -pensionReduction, 'Own contributions up to 5,000 €'] : null,
      jointReduction > 0 ? ['− Joint return', -jointReduction, '4,896 € for any family unit, single parents included'] : null,
      ['Base for the tax scale', baseLiquidable, 'Base liquidable general', 'b'],
      ['Tax on the base', scale.total, 'Basque scale 23–49%'],
      ['− General deduction', -BASQUE.generalDeduction, 'Minoración de cuota, every taxpayer'],
      family > 0 ? ['− Family, age and disability deductions', -r2(family), 'Children, ascendants, age, disability'] : null,
    ],
  }
}

// ── Navarra ──────────────────────────────────────────────────────────────────

export const NAVARRA_BRACKETS = [
  { upTo: 4458, rate: 0.13 },
  { upTo: 10030, rate: 0.22 },
  { upTo: 21175, rate: 0.25 },
  { upTo: 35663, rate: 0.28 },
  { upTo: 51266, rate: 0.365 },
  { upTo: 66869, rate: 0.415 },
  { upTo: 89159, rate: 0.44 },
  { upTo: 139310, rate: 0.47 },
  { upTo: 195034, rate: 0.49 },
  { upTo: 334344, rate: 0.505 },
  { upTo: Infinity, rate: 0.52 },
]
const NAVARRA = {
  personal: 1084,
  lowIncome: { amount: 1280, from: 17500, slope: 0.0904, mid: 30000, midAmount: 150, midSlope: 0.075, to: 32000 },
  age65: 264,
  age75: 585,
  disability: { '33': 766, '33h': 2757, '65': 2757 },
  familyDisability: { '33': 674, '33h': 2360, '65': 2360 },
  kids: [483, 512, 732, 981, 1111, 1286],
  under3: 644,
  // Descendant amounts +40% on rentas up to 20,000 €, tapering to nothing at 30,000 €.
  kidsBoost: { share: 0.4, fullUpTo: 20000, zeroFrom: 30000 },
  singleParent: 668,
  pension: { employee: 1500, employer: 8500, incomeShare: 0.30, incomeShareOver50: 0.50 },
}

/** Deducción por trabajo (art. 62.5 DFL 4/2008, as amended by LF 17/2025), on pay minus SS. */
export function calcNavarraWorkDeduction(net, disability = '0') {
  let d = net <= 12500 ? 1400
    : net <= 17500 ? 1400 - 0.14 * (net - 12500)
      : net <= 35000 ? 700
        : net <= 50000 ? 700 - 0.02 * (net - 35000)
          : 400
  if (disability === '33') d *= 1.5
  else if (disability === '65' || disability === '33h') d *= 2
  return r2(d)
}

function navarraPersonalMinimum(rentas, age) {
  const L = NAVARRA.lowIncome
  let m = NAVARRA.personal
  if (rentas <= L.from) m += L.amount
  else if (rentas <= L.mid) m += L.amount - L.slope * (rentas - L.from)
  else if (rentas <= L.to) m += L.midAmount - L.midSlope * (rentas - L.mid)
  if (age === '65to74') m += NAVARRA.age65
  if (age === '75plus') m += NAVARRA.age65 + NAVARRA.age75
  return r2(m)
}

function navarraIrpf(p) {
  const net = Math.max(0, p.rit - p.ss)
  const P = NAVARRA.pension
  // The form's age bands can't tell 50+ apart; 65+ gets the over-50 share.
  const incomeShare = p.age === 'u65' || !p.age ? P.incomeShare : P.incomeShareOver50
  const pensionCap = Math.min(P.employee + Math.min(p.pensionEmployer || 0, P.employer), incomeShare * net)
  const pensionReduction = r2(Math.min((p.pensionEmployee || 0) + (p.pensionEmployer || 0), pensionCap))
  const baseLiquidable = r2(Math.max(0, net - pensionReduction))
  const scale = scaleTax(baseLiquidable, NAVARRA_BRACKETS)

  const workDeduction = calcNavarraWorkDeduction(net, p.disability)
  let minimum = navarraPersonalMinimum(net, p.age) + (NAVARRA.disability[p.disability] || 0)
  const share = p.sharedCustody ? 0.5 : 1
  const numKids = (p.kidsU3 || 0) + (p.kids || 0)
  const B = NAVARRA.kidsBoost
  const boost = 1 + (net <= B.fullUpTo ? B.share : net >= B.zeroFrom ? 0 : B.share * (B.zeroFrom - net) / (B.zeroFrom - B.fullUpTo))
  for (let i = 0; i < numKids; i++) minimum += NAVARRA.kids[Math.min(i, NAVARRA.kids.length - 1)] * share * boost
  minimum += (p.kidsU3 || 0) * NAVARRA.under3 * share
  minimum += ((p.asc65 || 0) + (p.asc75 || 0)) * NAVARRA.age65 + (p.asc75 || 0) * NAVARRA.age75
  for (const level of [...(p.descDisab || []), ...(p.ascDisab || [])]) minimum += NAVARRA.familyDisability[level] || 0
  // Joint return: the spouse without income adds their own personal minimum (art. 73.3-73.4).
  if (p.joint === 'married') minimum += navarraPersonalMinimum(0, 'u65')
  if (p.joint === 'single') minimum += NAVARRA.singleParent
  minimum = r2(minimum)

  const total = r2(Math.max(0, scale.total - workDeduction - minimum))
  return {
    netBeforeExpenses: r2(net), baseImponible: r2(net), pensionReduction, baseLiquidable, cuotaIntegra: scale.total, total,
    brackets: scale.brackets, marginal: NAVARRA_BRACKETS,
    lines: [
      ['Taxable base', r2(net), 'Rendimiento neto del trabajo', 'b'],
      pensionReduction > 0 ? ['− Pension contributions', -pensionReduction, 'Up to 1,500 €, more through a company plan'] : null,
      ['Base for the tax scale', baseLiquidable, 'Base liquidable general', 'b'],
      ['Tax on the base', scale.total, 'Navarra scale 13–52%'],
      ['− Work income deduction', -workDeduction, 'Art. 62.5: 1,400 € on low pay, 700 € on middle incomes'],
      ['− Personal and family minimum', -minimum, p.joint === 'married'
        ? 'Yours plus your spouse’s, deducted from the tax'
        : p.joint === 'single' ? 'Includes 668 € for single parents' : 'Deducted from the tax in Navarra; higher on low incomes'],
    ],
  }
}

/** Annual IRPF for a foral region; same result shape as calcAnnualIrpf. */
export function calcForalIrpf(p) {
  const f = p.region === 'navarra' ? navarraIrpf(p) : basqueIrpf(p)
  const marginalRate = f.total > 0
    ? (f.marginal.find(b => f.baseLiquidable < b.upTo) || f.marginal[f.marginal.length - 1]).rate : 0
  return {
    regime: 'foral', rit: p.rit,
    jointReduction: 0, ...f, lines: f.lines.filter(Boolean),
    otherExpenses: 0, workReduction: 0, smiDeduction: 0, ceutaDeduction: 0,
    minimums: { state: 0, regional: 0 }, state: 0, regional: f.total, marginalRate,
    stateBrackets: [], regionalBrackets: f.brackets,
  }
}

// ── Withholding tables 2026 ──────────────────────────────────────────────────

// Bizkaia DF 134/2025: [up to annual pay, % for 0,1,2,3,4,5,6+ children]; 0% up to 20,000 €.
const BASQUE_WITHHOLDING = [
  [20000, 0, 0, 0, 0, 0, 0, 0],
  [20510, 7, 5, 3, 0, 0, 0, 0],
  [21300, 8, 6, 4, 1, 0, 0, 0],
  [22150, 9, 7, 5, 2, 0, 0, 0],
  [23220, 10, 9, 7, 4, 0, 0, 0],
  [24050, 11, 10, 8, 5, 1, 0, 0],
  [25410, 12, 11, 9, 6, 3, 0, 0],
  [27440, 13, 12, 10, 7, 4, 0, 0],
  [29790, 14, 13, 11, 9, 6, 2, 0],
  [32610, 15, 14, 13, 10, 8, 4, 0],
  [36350, 16, 15, 14, 12, 9, 6, 0],
  [40670, 17, 16, 15, 13, 11, 8, 0],
  [44560, 18, 17, 16, 15, 13, 10, 2],
  [48060, 19, 18, 17, 16, 14, 12, 4],
  [52020, 20, 19, 18, 17, 15, 13, 7],
  [56780, 21, 20, 20, 18, 17, 15, 9],
  [61820, 22, 21, 21, 20, 18, 16, 11],
  [65710, 23, 22, 22, 21, 19, 18, 12],
  [70080, 24, 23, 23, 22, 21, 19, 14],
  [75020, 25, 25, 24, 23, 22, 20, 16],
  [80730, 26, 26, 25, 24, 23, 22, 17],
  [86770, 27, 27, 26, 25, 24, 23, 19],
  [92190, 28, 28, 27, 26, 25, 24, 21],
  [98350, 29, 29, 28, 27, 27, 25, 22],
  [105380, 30, 30, 29, 29, 28, 27, 23],
  [113180, 31, 31, 30, 30, 29, 28, 25],
  [122030, 32, 32, 31, 31, 30, 29, 26],
  [132200, 33, 33, 32, 32, 31, 30, 28],
  [144140, 34, 34, 33, 33, 32, 32, 29],
  [157300, 35, 35, 34, 34, 33, 33, 31],
  [172280, 36, 36, 36, 35, 35, 34, 32],
  [190410, 37, 37, 37, 36, 36, 35, 33],
  [212820, 38, 38, 38, 37, 37, 36, 35],
  [236060, 39, 39, 39, 38, 38, 37, 36],
  [Infinity, 40, 40, 40, 39, 39, 39, 37],
]
// Points off the rate for disability (33–64%, 65%+ or reduced mobility), by pay up to.
const BASQUE_WH_DISABILITY = [
  [25410, 9, 12], [32610, 7, 12], [48060, 6, 10], [56780, 5, 10],
  [80730, 4, 8], [122030, 3, 6], [190410, 2, 5], [Infinity, 1, 3],
]

// Navarra DF 148/2025 (BON 14/2026): [more than annual pay, % for 0..10+ children]; 0% up to 17,000 €.
const NAVARRA_WITHHOLDING = [
  [17000, 2, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0],
  [18500, 4, 3, 2, 0, 0, 0, 0, 0, 0, 0, 0],
  [19750, 6, 5, 4, 2, 0, 0, 0, 0, 0, 0, 0],
  [21250, 8.5, 7.5, 6.5, 4.5, 2.5, 0, 0, 0, 0, 0, 0],
  [23250, 11, 10, 9, 7, 5, 2.5, 0, 0, 0, 0, 0],
  [25250, 13.3, 12, 11.3, 8.5, 7.5, 5.5, 3.4, 0.5, 0, 0, 0],
  [27500, 14.6, 13.3, 12.6, 9.9, 9.2, 7.8, 5.8, 3.8, 0.8, 0, 0],
  [30250, 15.8, 14.5, 13.7, 12.4, 10.7, 8.9, 7.9, 5.9, 3.9, 0.9, 0],
  [32250, 17, 16, 15, 13.6, 12.5, 10.8, 10, 8, 7, 5, 2],
  [35750, 18.1, 17.1, 16.5, 14.7, 14, 13.3, 12.2, 10.2, 9.1, 7.1, 6.1],
  [41250, 20, 19, 18.3, 16.9, 16.2, 15.5, 13.7, 12.4, 11.3, 10.2, 9.2],
  [48000, 22.1, 21.5, 20.9, 18.9, 18.3, 17.7, 16.6, 15.6, 14.5, 13.4, 12.3],
  [55000, 24.1, 23.5, 23, 22, 21.5, 20.9, 19.8, 18.7, 17.7, 16.6, 15],
  [62000, 26.1, 25.5, 24.5, 24, 23.5, 22.9, 21.9, 21.4, 19.8, 18.7, 17.2],
  [69250, 28.3, 27.7, 27, 26.6, 25.5, 25, 24.4, 22.9, 21.8, 20.3, 19.3],
  [75250, 29.6, 29.2, 28.3, 27.3, 27.2, 26.2, 26.1, 24.5, 23.4, 22.3, 21.3],
  [82250, 30.8, 30.5, 30, 29.4, 29, 28.3, 27.7, 26.6, 25.6, 24.5, 23.9],
  [94750, 32.2, 31.7, 31.2, 30.8, 30.4, 30, 29.5, 28.9, 27.8, 26.8, 25.7],
  [107250, 33.5, 33, 32.6, 32.3, 32, 31.5, 31, 30, 29.5, 28.5, 28],
  [120000, 35.1, 34.8, 34.6, 34, 33.5, 32.9, 32.4, 31.3, 30.7, 29.7, 29.1],
  [132750, 36.2, 36, 35.8, 35, 34.5, 33.9, 33.4, 32.8, 32, 31, 30],
  [146000, 38, 37.5, 37, 36.5, 35.5, 34.9, 34.4, 34, 33.5, 32, 31.5],
  [200000, 40, 39.8, 39.4, 39, 38.5, 38, 37.5, 35.5, 34.5, 33.7, 33],
  [280000, 42, 41.5, 41.2, 40.8, 40, 39.5, 39, 37, 36, 35.2, 34.5],
  [350000, 43, 42.9, 42.8, 42.5, 41.5, 41, 40.5, 38.5, 37.5, 36.7, 36],
]
// Points off the rate for disability (33–64%, 65%+), by pay up to.
const NAVARRA_WH_DISABILITY = [[23250, 5, 15], [41250, 3, 15], [94750, 2, 8], [Infinity, 2, 5]]

const MIN_TEMPORARY = 2

/** Withholding from the foral percentage tables; same result shape as calcWithholding. */
export function calcForalWithholding(p) {
  const retrib = Math.max(0, p.rit)
  const kids = (p.kidsU3 || 0) + (p.kids || 0)
  const navarra = p.region === 'navarra'
  let rate = 0
  let limit
  if (navarra) {
    limit = NAVARRA_WITHHOLDING[0][0]
    const row = [...NAVARRA_WITHHOLDING].reverse().find(r => retrib > r[0])
    if (row) rate = row[1 + Math.min(kids, 10)]
  } else {
    limit = BASQUE_WITHHOLDING[0][0]
    const row = BASQUE_WITHHOLDING.find(r => retrib <= r[0])
    rate = row[1 + Math.min(kids, 6)]
  }
  if (rate > 0 && p.disability !== '0') {
    const table = navarra ? NAVARRA_WH_DISABILITY : BASQUE_WH_DISABILITY
    const row = table.find(r => retrib <= r[0])
    rate = Math.max(0, rate - (p.disability === '33' ? row[1] : row[2]))
  }
  if (p.contract === 'temporary') rate = Math.max(rate, MIN_TEMPORARY)
  rate = r2(rate)
  return {
    regime: 'foral', retrib, base: retrib, minimum: 0, limit, exempt: rate === 0 && retrib <= limit,
    largeFamilyReduction: 0, cuota: 0, rate, annual: r2(retrib * rate / 100),
  }
}
