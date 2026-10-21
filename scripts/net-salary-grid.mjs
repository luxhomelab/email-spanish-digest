// Build-time figures for the programmatic net-salary pages (/calculators/net-salary-30000-euros ...).
// Reuses the browser calculator modules so the tax engine stays a single source of truth.
// Usage: node scripts/net-salary-grid.mjs [path/to/net-salary-pages.json]  -> JSON on stdout.
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import { calculateNetSalary, compareRegions } from '../static/js/net-salary-calc.js'
import { DEFAULTS, QUERY_KEYS } from '../static/js/net-salary-form.js'

const r2 = x => Math.round(x * 100) / 100

/** Figures for one gross-per-year at the reference profile (DEFAULTS: Madrid, under 65, permanent, no dependants). */
export function figuresFor(gross, payments) {
  const s = { ...DEFAULTS, gross, payments }
  const r = calculateNetSalary(s)
  return {
    gross,
    payments,
    netAnnual: r.netAnnual,
    annualTaxNet: r.annualTaxNet,
    refund: r.refund,
    payslipRegular: r.payslip.regular,
    payslipExtra: r.payslip.extra,
    ssTotal: r.ss.total,
    irpfTotal: r.irpf.total,
    marginalRate: r.irpf.marginalRate ?? null,
    withholdingRate: r.withholding.rate,
    effectiveRate: r.effectiveRate,
    employerCost: r.employer.totalCost,
  }
}

/** Both payment views plus the all-region comparison for a gross per year. */
export function gridEntry(gross) {
  const regions = compareRegions({ ...DEFAULTS, gross, payments: '12' }).map(x => ({
    region: x.region,
    annualTaxNet: x.annualTaxNet,
    monthlyNet: r2(x.annualTaxNet / 12),
    irpf: x.irpf,
  }))
  return { gross, p12: figuresFor(gross, '12'), p14: figuresFor(gross, '14'), regions }
}

/** Whole grid: annual pages keyed by gross; monthly pages keyed by monthly wage (x12 and x14 readings). */
export function buildGrid(config) {
  return {
    annual: config.annual.map(a => ({ amount: a, query: `${QUERY_KEYS.amount}=${a}`, ...gridEntry(a) })),
    monthly: config.monthly.map(m => ({
      amount: m,
      query: `${QUERY_KEYS.amount}=${m}&${QUERY_KEYS.period}=m`,
      x12: gridEntry(m * 12),
      x14: { gross: m * 14, p14: figuresFor(m * 14, '14') },
    })),
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const here = dirname(fileURLToPath(import.meta.url))
  const path = process.argv[2] || resolve(here, '../data/net-salary-pages.json')
  process.stdout.write(JSON.stringify(buildGrid(JSON.parse(readFileSync(path, 'utf8')))))
}
