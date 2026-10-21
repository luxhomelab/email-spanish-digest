// Build-time figures for the programmatic rental-yield pages (/calculators/rental-yield-200000-euros-property ...).
// Reuses the browser calculator modules so the yield engine stays a single source of truth.
// Usage: node scripts/rental-yield-grid.mjs [path/to/rental-yield-pages.json]  -> JSON on stdout.
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import { simulateProjection } from '../static/js/rental-yield-calc.js'
import { REGIONS } from '../static/js/property-buying-cost-calc.js'
import { DEFAULTS, QUERY_KEYS } from '../static/js/rental-yield-form.js'

const roundTo = (x, step) => Math.round(x / step) * step

/** Reference expenses scale with the price: DEFAULTS describe a €250,000 flat (IBI €600, community €80/month). */
export function referenceCosts(price) {
  const ratio = price / DEFAULTS.purchasePrice
  return {
    annualIBI: Math.max(roundTo(DEFAULTS.annualIBI * ratio, 10), 100),
    monthlyCommunity: Math.min(Math.max(roundTo(DEFAULTS.monthlyCommunity * ratio ** 0.5, 5), 30), 300),
  }
}

/** Monthly rent that gives a target gross yield on the price, rounded to €5. */
export function rentForYield(price, grossPct) {
  return roundTo(price * grossPct / 100 / 12, 5)
}

function simulate(price, rent, overrides = {}) {
  const state = {
    ...DEFAULTS, ...referenceCosts(price), purchasePrice: price, monthlyRent: rent, useRenovation: false, useLoan: false, ...overrides,
  }
  return { state, r: simulateProjection(state) }
}

function summary(price, rent, overrides) {
  const { r } = simulate(price, rent, overrides)
  return {
    rent,
    annualRent: rent * 12,
    grossYield: r.grossYield,
    netYield: r.netYield,
    monthlyCashFlow: r.monthlyCashFlow,
    firstYearNOI: r.firstYearNOI,
    firstYearTax: r.firstYearTax,
    purchaseTax: r.purchaseTax,
    closingCosts: r.closingCosts,
    totalInvestment: r.totalInvestment,
    irr: r.irr,
  }
}

const STATUSES = ['resident', 'non_resident_eu', 'non_resident_non_eu']

export function gridEntry(price, config) {
  const refRent = rentForYield(price, config.referenceGrossPct)
  const costs = referenceCosts(price)
  const byStatus = Object.fromEntries(STATUSES.map(t => [t, summary(price, refRent, { taxStatus: t })]))
  const targets = config.targetYields.map(y => {
    const rent = rentForYield(price, y)
    return { targetPct: y, ...Object.fromEntries(STATUSES.map(t => [t, summary(price, rent, { taxStatus: t })])) }
  })
  const regions = REGIONS.map(reg => ({ region: reg.id, ...summary(price, refRent, { regionId: reg.id }) }))
  const q = new URLSearchParams({
    [QUERY_KEYS.purchasePrice]: price, [QUERY_KEYS.monthlyRent]: refRent,
    [QUERY_KEYS.annualIBI]: costs.annualIBI, [QUERY_KEYS.monthlyCommunity]: costs.monthlyCommunity,
  })
  return { amount: price, query: q.toString(), refRent, costs, resident: byStatus.resident, byStatus, targets, regions }
}

export function buildGrid(config) {
  return { prices: config.prices.map(p => gridEntry(p, config)) }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const here = dirname(fileURLToPath(import.meta.url))
  const path = process.argv[2] || resolve(here, '../data/rental-yield-pages.json')
  process.stdout.write(JSON.stringify(buildGrid(JSON.parse(readFileSync(path, 'utf8')))))
}
