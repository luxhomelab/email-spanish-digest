// Build-time figures for the programmatic autónomo pages
// (/calculators/autonomo-tax-30000-euros, /calculators/autonomo-take-home-2000-euros-per-month ...).
// Reuses the browser calculator modules so the tax engine stays a single source of truth.
// Usage: node scripts/autonomo-grid.mjs [path/to/autonomo-pages.json]  -> JSON on stdout.
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import { calculateAutonomo, IRPF_REGIONAL_BRACKETS } from '../static/js/autonomo-calc.js'
import { DEFAULTS } from '../static/js/autonomo-form.js'

// The calculator UI does not offer the foral regions, so neither do the pages.
const FORAL = new Set(['navarra', 'pais_vasco'])
export const REGIONS = Object.keys(IRPF_REGIONAL_BRACKETS).filter(r => !FORAL.has(r))

// Net pay is searched in whole-euro steps of this size; the answer is rounded up to it.
export const STEP = 10
const SEARCH_MAX = 300000

/** Figures for one annual net revenue at the reference profile (DEFAULTS: Madrid, individual, 35, no dependants). */
export function figuresFor(annualNetRevenue, overrides = {}) {
  const r = calculateAutonomo({ ...DEFAULTS, annualNetRevenue, ...overrides })
  return {
    revenue: annualNetRevenue,
    bracketId: r.ssBracketId,
    isTarifaPlana: r.isTarifaPlana,
    monthlyQuota: r.monthlySSQuota,
    annualSS: r.annualSSTotal,
    ssDeduction: r.ssDeduction,
    irpfDeduction: r.irpfDeduction,
    irpfBase: r.irpfBase,
    personalMinimum: r.personalMinimum,
    irpfState: r.irpfState,
    irpfRegional: r.irpfRegional,
    irpfTotal: r.irpfTotal,
    totalBurden: r.totalBurden,
    effectiveTotalRate: r.effectiveTotalRate,
    effectiveIrpfRate: r.effectiveIrpfRate,
    netYear: r.netTakeHome,
    netMonth: r.netTakeHomeMonthly,
  }
}

/** Established autónomo, new autónomo (tarifa plana), and every region, for an annual net revenue. */
export function revenueEntry(revenue) {
  const regions = REGIONS.map(region => {
    const f = figuresFor(revenue, { region })
    return { region, netYear: f.netYear, netMonth: f.netMonth, irpf: f.irpfTotal }
  }).sort((a, b) => b.netYear - a.netYear)
  return { amount: revenue, established: figuresFor(revenue), tarifaPlana: figuresFor(revenue, { timeAsAutonomo: 'new' }), regions }
}

/**
 * Smallest annual net revenue (multiple of STEP) that keeps at least `monthlyNet` a month at every
 * higher revenue too. Quota brackets make net pay step down slightly at each boundary, so the first
 * revenue that reaches the target is not always safe; the one after the last miss is.
 */
export function requiredRevenue(monthlyNet, overrides = {}) {
  let lastMiss = -STEP
  for (let rev = 0; rev <= SEARCH_MAX; rev += STEP) {
    if (figuresFor(rev, overrides).netMonth < monthlyNet) lastMiss = rev
  }
  if (lastMiss + STEP > SEARCH_MAX) throw new Error(`monthly net ${monthlyNet} is out of the search range`)
  return lastMiss + STEP
}

export function monthlyEntry(monthlyNet) {
  const revenue = requiredRevenue(monthlyNet)
  return {
    ...revenueEntry(revenue),
    amount: monthlyNet,
    needed: revenue,
    neededTarifaPlana: requiredRevenue(monthlyNet, { timeAsAutonomo: 'new' }),
  }
}

export function buildGrid(config) {
  return {
    revenue: config.revenue.map(revenueEntry),
    monthly: config.monthly.map(monthlyEntry),
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const here = dirname(fileURLToPath(import.meta.url))
  const path = process.argv[2] || resolve(here, '../data/autonomo-pages.json')
  process.stdout.write(JSON.stringify(buildGrid(JSON.parse(readFileSync(path, 'utf8')))))
}
