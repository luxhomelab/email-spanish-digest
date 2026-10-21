/**
 * Spanish employee net salary calculator (2026): pure math, no DOM.
 *
 * Two IRPF figures are computed on purpose:
 * - the withholding the employer applies on each payslip (AEAT 2026 algorithm), and
 * - the tax the annual Renta actually settles (state + regional scales, regional
 *   minimums, art. 20 reduction, SMI deduction, joint taxation, pension contributions).
 * The difference is the refund (or extra payment) at the Renta.
 *
 * Data and legal sources live in net-salary-data.js. Unit-tested with node:test.
 */
import {
  calcProgressiveTax, calcProgressiveTaxWithBreakdown, IRPF_STATE_BRACKETS, IRPF_REGIONAL_BRACKETS,
} from './autonomo-calc.js'
import {
  SS_BASE_MAX_MONTHLY, SS_EMPLOYEE_RATES, SS_EMPLOYER_RATES, SOLIDARITY_BANDS, SOLIDARITY_EMPLOYEE_SHARE,
  OTHER_EXPENSES, WORK_REDUCTION, SMI_DEDUCTION, JOINT_REDUCTION, PENSION_LIMITS, CEUTA_MELILLA_SHARE,
  BECKHAM, FLEX_LIMITS, getMinimumTable, WITHHOLDING_SCALE, EXCLUSION_LIMITS, WITHHOLDING_CAP,
  WITHHOLDING_LARGE_FAMILY, WITHHOLDING_MIN_TEMPORARY,
} from './net-salary-data.js'

/** Common-regime regions plus Ceuta and Melilla, in selector order. */
export const REGION_IDS = [
  'andalucia', 'aragon', 'asturias', 'baleares', 'canarias', 'cantabria', 'castilla_la_mancha',
  'castilla_leon', 'catalunya', 'ceuta', 'comunidad_valenciana', 'extremadura', 'galicia',
  'la_rioja', 'madrid', 'melilla', 'murcia',
]

const r2 = x => Math.round(x * 100) / 100
const isCeutaMelilla = region => region === 'ceuta' || region === 'melilla'

// ── Social Security ──────────────────────────────────────────────────────────

function solidarityMonthly(monthlyRemuneration) {
  const excess = monthlyRemuneration - SS_BASE_MAX_MONTHLY
  if (excess <= 0) return 0
  let total = 0
  let prev = 0
  for (const { upToShare, rate } of SOLIDARITY_BANDS) {
    const top = upToShare * SS_BASE_MAX_MONTHLY
    const slice = Math.min(excess, top) - prev
    if (slice <= 0) break
    total += slice * rate
    prev = top
  }
  return total
}

/**
 * Employee contributions. Extra payslips are prorated into the monthly base
 * (annual / 12), which is capped at the base máxima.
 */
export function calcEmployeeSS({ annualRemuneration, contract = 'permanent' }) {
  const monthly = Math.max(0, annualRemuneration) / 12
  const monthlyBase = Math.min(monthly, SS_BASE_MAX_MONTHLY)
  const base = monthlyBase * 12
  const R = SS_EMPLOYEE_RATES
  const lines = {
    cc: r2(base * R.cc),
    unemployment: r2(base * R.unemployment[contract]),
    fp: r2(base * R.fp),
    mei: r2(base * R.mei),
    solidarity: r2(solidarityMonthly(monthly) * SOLIDARITY_EMPLOYEE_SHARE * 12),
  }
  const total = r2(Object.values(lines).reduce((a, b) => a + b, 0))
  return { monthlyBase: r2(monthlyBase), capped: monthly > SS_BASE_MAX_MONTHLY, lines, total }
}

/** Employer contributions; `atRate` is the AT/EP premium in percent (depends on the CNAE). */
export function calcEmployerSS({ annualRemuneration, contract = 'permanent', atRate = 1.5 }) {
  const monthly = Math.max(0, annualRemuneration) / 12
  const base = Math.min(monthly, SS_BASE_MAX_MONTHLY) * 12
  const R = SS_EMPLOYER_RATES
  const lines = {
    cc: r2(base * R.cc),
    unemployment: r2(base * R.unemployment[contract]),
    fogasa: r2(base * R.fogasa),
    fp: r2(base * R.fp),
    mei: r2(base * R.mei),
    atep: r2(base * atRate / 100),
    solidarity: r2(solidarityMonthly(monthly) * (1 - SOLIDARITY_EMPLOYEE_SHARE) * 12),
  }
  return { lines, total: r2(Object.values(lines).reduce((a, b) => a + b, 0)) }
}

// ── IRPF building blocks ─────────────────────────────────────────────────────

/** Reducción por obtención de rendimientos del trabajo (art. 20 LIRPF). */
export function calcWorkReduction(netIncome) {
  const W = WORK_REDUCTION
  if (netIncome <= W.lower) return W.max
  if (netIncome <= W.mid) return r2(W.max - W.slope1 * (netIncome - W.lower))
  if (netIncome < W.upper) return r2(W.midAmount - W.slope2 * (netIncome - W.mid))
  return 0
}

/** Otros gastos deducibles (art. 19.2.f LIRPF), never above the net income. */
export function calcOtherExpenses({ netBeforeExpenses, mobility = false, disability = '0' }) {
  let g = OTHER_EXPENSES.general
  if (mobility) g += OTHER_EXPENSES.mobility
  if (disability === '65' || disability === '33h') g += OTHER_EXPENSES.disabled65
  else if (disability === '33') g += OTHER_EXPENSES.disabled33
  return Math.min(g, Math.max(0, netBeforeExpenses))
}

/** Deducción por obtención de rendimientos del trabajo for SMI earners (DA 61ª LIRPF). */
export function calcSmiDeduction(grossWorkIncome) {
  const S = SMI_DEDUCTION
  if (grossWorkIncome >= S.to) return 0
  if (grossWorkIncome <= S.from) return S.amount
  return r2(S.amount - S.slope * (grossWorkIncome - S.from))
}

/**
 * Mínimo personal y familiar. `scope` 'state' gives the amounts used for the state
 * cuota and for withholding; the regional amounts depend on the region.
 */
function minimumFor(p, t) {
  const share = p.sharedCustody ? 0.5 : 1
  let m = t.contrib
  if (p.age === '65to74') m += t.age65
  if (p.age === '75plus') m += t.age65 + t.age75

  const kids = (p.kidsU3 || 0) + (p.kids || 0)
  for (let i = 0; i < kids; i++) m += t.desc[Math.min(i, t.desc.length - 1)] * share
  m += (p.kidsU3 || 0) * t.u3 * share

  const disAmount = (level, a33, a65) => (level === '65' ? a65 + t.assist
    : level === '33h' ? a33 + t.assist : a33)
  if (p.disability !== '0') m += disAmount(p.disability, t.dis33, t.dis65)
  for (const level of p.descDisab || []) {
    m += disAmount(level, t.descDis33 ?? t.dis33, t.descDis65 ?? t.dis65) * share
  }

  const asc = (p.asc65 || 0) + (p.asc75 || 0)
  const disabledAscUnder65 = Math.max(0, (p.ascDisab || []).length - asc)
  m += (asc + disabledAscUnder65) * t.asc65 + (p.asc75 || 0) * t.asc75
  for (const level of p.ascDisab || []) m += disAmount(level, t.dis33, t.dis65)
  return r2(m)
}

export function calcMinimums(personal, region) {
  return {
    state: minimumFor(personal, getMinimumTable('state')),
    regional: minimumFor(personal, getMinimumTable('regional', region)),
  }
}

const regionalBrackets = region => IRPF_REGIONAL_BRACKETS[region] || IRPF_STATE_BRACKETS

/** Scale tax rounded per bracket, as the AEAT tables accumulate their cuota column. */
const scaleTax = (base, brackets) => calcProgressiveTaxWithBreakdown(base, brackets).total

// ── Flexible pay ─────────────────────────────────────────────────────────────

const FLEX_ITEMS = ['health', 'meals', 'transport', 'nursery']

function flexExemptCap(item, s) {
  if (item === 'health') return FLEX_LIMITS.healthPerPerson * Math.max(1, s.healthPersons || 1)
  if (item === 'meals') return FLEX_LIMITS.mealsPerDay * FLEX_LIMITS.workDays
  if (item === 'transport') return FLEX_LIMITS.transport
  return Infinity
}

function calcFlex(s) {
  let total = 0, sacrifice = 0, extra = 0, exempt = 0
  const items = {}
  for (const item of FLEX_ITEMS) {
    const amount = Math.max(0, s[item] || 0)
    const ex = s.regime === 'beckham' ? 0 : Math.min(amount, flexExemptCap(item, s))
    items[item] = { amount, exempt: ex, mode: s[item + 'Mode'] }
    total += amount
    exempt += ex
    if (s[item + 'Mode'] === 'extra') extra += amount
    else sacrifice += amount
  }
  return { items, total, sacrifice, extra, exempt, taxable: total - exempt }
}

// ── Annual IRPF ──────────────────────────────────────────────────────────────

/**
 * IRPF settled by the annual Renta.
 * @param {{rit:number, ss:number, region:string, regime:string, pensionEmployee:number,
 *   pensionEmployer:number, joint:string, mobility:boolean, disability:string}} p
 */
export function calcAnnualIrpf(p) {
  if (p.regime === 'beckham') {
    const total = r2(Math.min(p.rit, BECKHAM.threshold) * BECKHAM.rate
      + Math.max(0, p.rit - BECKHAM.threshold) * BECKHAM.topRate)
    return { regime: 'beckham', rit: p.rit, baseLiquidable: p.rit, total, state: total, regional: 0,
      cuotaIntegra: total, smiDeduction: 0, ceutaDeduction: 0, otherExpenses: 0, workReduction: 0,
      pensionReduction: 0, jointReduction: 0, minimums: { state: 0, regional: 0 },
      stateBrackets: [], regionalBrackets: [], marginalRate: p.rit > BECKHAM.threshold ? BECKHAM.topRate : BECKHAM.rate }
  }

  const netBeforeExpenses = Math.max(0, p.rit - p.ss)
  const otherExpenses = calcOtherExpenses({ netBeforeExpenses, mobility: p.mobility, disability: p.disability })
  const workReduction = Math.min(calcWorkReduction(netBeforeExpenses), netBeforeExpenses - otherExpenses)
  const baseImponible = Math.max(0, netBeforeExpenses - otherExpenses - workReduction)

  const pensionCap = PENSION_LIMITS.employee + Math.min(p.pensionEmployer || 0, PENSION_LIMITS.employer)
  const pensionReduction = Math.min((p.pensionEmployee || 0) + (p.pensionEmployer || 0), pensionCap,
    PENSION_LIMITS.incomeShare * baseImponible)
  const jointReduction = JOINT_REDUCTION[p.joint] || 0
  const baseLiquidable = r2(Math.max(0, baseImponible - pensionReduction - jointReduction))

  const minimums = calcMinimums(p, p.region)
  const rb = regionalBrackets(p.region)
  const stateGross = scaleTax(baseLiquidable, IRPF_STATE_BRACKETS)
  const regionalGross = scaleTax(baseLiquidable, rb)
  const stateMin = scaleTax(Math.min(minimums.state, baseLiquidable), IRPF_STATE_BRACKETS)
  const regionalMin = scaleTax(Math.min(minimums.regional, baseLiquidable), rb)
  let state = r2(stateGross - stateMin)
  let regional = r2(regionalGross - regionalMin)
  const cuotaIntegra = r2(state + regional)

  let ceutaDeduction = 0
  if (isCeutaMelilla(p.region)) {
    ceutaDeduction = r2(cuotaIntegra * (1 - CEUTA_MELILLA_SHARE))
    state = r2(state * CEUTA_MELILLA_SHARE)
    regional = r2(regional * CEUTA_MELILLA_SHARE)
  }
  const afterCeuta = r2(state + regional)
  const smiDeduction = r2(Math.min(calcSmiDeduction(p.rit), afterCeuta))
  if (smiDeduction > 0 && afterCeuta > 0) {
    const k = 1 - smiDeduction / afterCeuta
    state = r2(state * k)
    regional = r2(afterCeuta - smiDeduction - state)
  }
  const total = r2(Math.max(0, state + regional))

  const marginalOf = brackets => (brackets.find(b => baseLiquidable < b.upTo) || brackets[brackets.length - 1]).rate
  const marginalRate = baseLiquidable > Math.max(minimums.state, 0)
    ? (marginalOf(IRPF_STATE_BRACKETS) + marginalOf(rb)) * (isCeutaMelilla(p.region) ? CEUTA_MELILLA_SHARE : 1)
    : 0

  return {
    regime: 'standard', rit: p.rit, netBeforeExpenses: r2(netBeforeExpenses), otherExpenses,
    workReduction, baseImponible: r2(baseImponible), pensionReduction: r2(pensionReduction), jointReduction,
    baseLiquidable, minimums, stateGross, regionalGross, stateMin, regionalMin, cuotaIntegra,
    ceutaDeduction, smiDeduction, state, regional, total, marginalRate,
    stateBrackets: calcProgressiveTaxWithBreakdown(baseLiquidable, IRPF_STATE_BRACKETS).brackets,
    regionalBrackets: calcProgressiveTaxWithBreakdown(baseLiquidable, rb).brackets,
  }
}

// ── Withholding (AEAT algorithm 2026) ────────────────────────────────────────

const truncate2 = x => Math.trunc(x * 100 + 1e-9) / 100

function familySituation(p) {
  if (p.joint === 'single') return 1
  if (p.joint === 'married') return 2
  return 3
}

/**
 * Tipo de retención on employment income. Uses state minimums only (the algorithm
 * has no regional component) and the Ceuta/Melilla 60% reduction.
 */
export function calcWithholding(p) {
  const retrib = Math.max(0, p.rit)
  if (p.regime === 'beckham') {
    const annual = r2(Math.min(retrib, BECKHAM.threshold) * BECKHAM.rate
      + Math.max(0, retrib - BECKHAM.threshold) * BECKHAM.topRate)
    return { regime: 'beckham', retrib, base: retrib, cuota: annual, exempt: false,
      rate: retrib > 0 ? truncate2(annual / retrib * 100) : 0, annual }
  }

  const rnt = Math.max(0, retrib - p.ss)
  const otherExpenses = calcOtherExpenses({ netBeforeExpenses: rnt, mobility: p.mobility, disability: p.disability })
  const workReduction = calcWorkReduction(rnt)
  const rntReduced = Math.max(0, rnt - otherExpenses - workReduction)
  const numChildren = (p.kidsU3 || 0) + (p.kids || 0)
  const largeFamily = numChildren >= WITHHOLDING_LARGE_FAMILY.minChildren ? WITHHOLDING_LARGE_FAMILY.reduction : 0
  const base = Math.max(0, rntReduced - largeFamily)
  const minimum = calcMinimums(p, p.region).state

  const situation = familySituation(p)
  const limit = EXCLUSION_LIMITS[situation][Math.min(numChildren, 2)]
  const exempt = limit != null && retrib <= limit
  const ceuta = isCeutaMelilla(p.region)

  let cuota = 0
  let rate = 0
  if (!exempt) {
    cuota = Math.max(0, calcProgressiveTax(base, WITHHOLDING_SCALE) - calcProgressiveTax(minimum, WITHHOLDING_SCALE))
    if (limit != null && retrib <= WITHHOLDING_CAP.upToRetrib) {
      cuota = Math.min(cuota, (retrib - limit) * WITHHOLDING_CAP.share)
    }
    const due = ceuta ? cuota * CEUTA_MELILLA_SHARE : cuota
    rate = retrib > 0 ? truncate2(due / retrib * 100) : 0
    if (p.contract === 'temporary') {
      rate = Math.max(rate, ceuta ? WITHHOLDING_MIN_TEMPORARY.ceutaMelilla : WITHHOLDING_MIN_TEMPORARY.general)
    }
  }
  return {
    regime: 'standard', retrib, base: r2(base), minimum, situation, limit, exempt,
    largeFamilyReduction: largeFamily, cuota: r2(cuota), rate, annual: r2(retrib * rate / 100),
  }
}

// ── Full calculation ─────────────────────────────────────────────────────────

/**
 * @param {object} s form state plus `gross` (annual contract gross, € — includes any
 *   flexible pay taken as salary sacrifice).
 */
export function calculateNetSalary(s) {
  const gross = Math.max(0, s.gross || 0)
  const flex = calcFlex(s)
  const cashGross = Math.max(0, gross - flex.sacrifice)
  const pensionEmployer = Math.max(0, s.pensionEmployer || 0)
  // Everything the employer pays counts for Social Security (in-kind pay cotiza since RDL 16/2013).
  const totalComp = cashGross + flex.total
  const ssRemuneration = totalComp + pensionEmployer
  const ss = calcEmployeeSS({ annualRemuneration: ssRemuneration, contract: s.contract })
  const employerSS = calcEmployerSS({ annualRemuneration: ssRemuneration, contract: s.contract, atRate: s.atRate })

  // Rendimiento íntegro del trabajo: cash + taxable in-kind (+ employer pension contributions).
  const rit = r2(cashGross + flex.taxable + pensionEmployer)
  const p = { ...s, rit, ss: s.regime === 'beckham' ? 0 : ss.total, pensionEmployer }
  const irpf = calcAnnualIrpf(p)
  const withholding = calcWithholding({ ...p, ss: ss.total })

  // Cash actually paid: in-kind withholding is charged to the cash payslips; employee
  // pension contributions are taken from the payslip too.
  const pensionEmployee = Math.max(0, s.pensionEmployee || 0)
  const netAnnual = r2(cashGross - ss.total - withholding.annual - pensionEmployee)
  const annualTaxNet = r2(cashGross - ss.total - irpf.total - pensionEmployee)
  const refund = r2(withholding.annual - irpf.total)

  const t = withholding.rate / 100
  let payslip
  if (s.payments === '14') {
    const ordinary = gross / 14
    const extra = r2(ordinary * (1 - t))
    payslip = { count: 14, regular: r2((netAnnual - 2 * extra) / 12), extra, grossRegular: r2(ordinary - flex.sacrifice / 12), grossExtra: r2(ordinary) }
  } else {
    payslip = { count: 12, regular: r2(netAnnual / 12), extra: null, grossRegular: r2(cashGross / 12), grossExtra: null }
  }

  const hours = Math.max(1, s.hoursPerWeek || 40) * 52
  return {
    gross, cashGross: r2(cashGross), totalComp: r2(totalComp), flex, ss, irpf, withholding,
    netAnnual, annualTaxNet, refund, payslip,
    totalValue: r2(netAnnual + flex.total),
    employer: { ...employerSS, totalCost: r2(totalComp + pensionEmployer + employerSS.total) },
    hourly: r2(netAnnual / hours),
    effectiveRate: gross > 0 ? (ss.total + irpf.total) / gross : 0,
    marginalKeep: marginalKeep(s, annualTaxNet),
  }
}

/** Share of an extra 100 € gross the employee keeps after SS and the annual IRPF. */
function marginalKeep(s, base) {
  if (s._noMarginal) return null
  const up = calculateNetSalary({ ...s, gross: (s.gross || 0) + 100, _noMarginal: true })
  return Math.round((up.annualTaxNet - base) / 100 * 1000) / 1000
}

/** Same profile in every region, best net after the Renta first. */
export function compareRegions(s) {
  return REGION_IDS
    .map(region => {
      const r = calculateNetSalary({ ...s, region, _noMarginal: true })
      return { region, annualTaxNet: r.annualTaxNet, netAnnual: r.netAnnual, irpf: r.irpf.total, refund: r.refund }
    })
    .sort((a, b) => b.annualTaxNet - a.annualTaxNet)
}

/**
 * Gross needed for a target net. `metric` 'annual' targets netAnnual; 'payslip' the
 * regular payslip. Bisection: net is monotonic in gross.
 */
export function grossFromNet(target, s, metric = 'annual') {
  const value = g => {
    const r = calculateNetSalary({ ...s, gross: g, _noMarginal: true })
    return metric === 'payslip' ? r.payslip.regular : r.netAnnual
  }
  let lo = 0
  let hi = Math.max(1000, target * 3)
  while (value(hi) < target && hi < 1e8) hi *= 2
  for (let i = 0; i < 60; i++) {
    const mid = (lo + hi) / 2
    if (value(mid) < target) lo = mid
    else hi = mid
  }
  // Net values are rounded to cents, so step up until the rounded net reaches the target.
  let g = Math.ceil(hi * 100) / 100
  for (let i = 0; i < 20 && value(g) < target; i++) g = Math.round((g + 0.01) * 100) / 100
  return g
}

/**
 * Annual contract gross from the form: the amount is a gross or a target net, per year
 * or per month (a monthly gross counts 14 times with 14 separate payslips).
 */
export function resolveGross(s) {
  const amount = Math.max(0, s.amount || 0)
  if (s.mode === 'net') return grossFromNet(amount, s, s.period === 'm' ? 'payslip' : 'annual')
  if (s.period === 'm') return amount * (s.payments === '14' ? 14 : 12)
  return amount
}
