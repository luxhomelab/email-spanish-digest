/**
 * Autónomo (Spanish self-employed) tax calculator.
 *
 * Covers:
 * - Social Security quotas under the 2023 income-based reform (15 brackets)
 * - Tarifa plana for new autonomos (first 12 months)
 * - IRPF: state + regional components
 * - Personal minimum allowances (age, children, disability)
 * - General expenses deduction (7% individual, 3% director) — for SS bracket only
 * - IRPF deduction (5% flat, estimación directa simplificada)
 *
 * Data sources:
 * - SS quotas 2026: Orden PJC/297/2026 (BOE-A-2026-7296, art. 18: bases × 31.50% tipo total)
 * - SS quotas 2027+: 2026 values applied (no approved increases yet)
 * - IRPF brackets: AEAT state brackets + approximate regional rates
 * - Results are approximate; not financial or legal advice.
 */

// ── Social Security brackets ──────────────────────────────────────────────────
// Monthly net income thresholds (rendimiento neto mensual) defining each tramo.
// The autonomo pays the minimum quota for the tramo that matches their net income.

/** @type {Array<{id:number, maxMonthly:number}>} */
const SS_BRACKET_THRESHOLDS = [
  { id: 1,  maxMonthly: 670     },
  { id: 2,  maxMonthly: 900     },
  { id: 3,  maxMonthly: 1166.70 },
  { id: 4,  maxMonthly: 1300    },
  { id: 5,  maxMonthly: 1500    },
  { id: 6,  maxMonthly: 1700    },
  { id: 7,  maxMonthly: 1850    },
  { id: 8,  maxMonthly: 2030    },
  { id: 9,  maxMonthly: 2330    },
  { id: 10, maxMonthly: 2760    },
  { id: 11, maxMonthly: 3190    },
  { id: 12, maxMonthly: 3620    },
  { id: 13, maxMonthly: 4050    },
  { id: 14, maxMonthly: 6000    },
  { id: 15, maxMonthly: Infinity },
]

/**
 * Official 2026 minimum monthly SS quotas (cuota mínima) per bracket.
 * Source: Orden PJC/297/2026 (BOE-A-2026-7296, art. 18) — minimum bases × 31.50%
 * (28.30% comunes + 1.30% profesionales + 0.90% MEI + 0.90% cese + 0.10% FP).
 * Index 0 = bracket 1, index 14 = bracket 15.
 * For 2027+: no increases approved yet; 2026 values are used.
 */
const SS_MIN_QUOTAS_2026 = [
  205.88, 226.47, 267.65, 299.56, 302.65, 302.65,
  360.29, 380.88, 401.47, 427.21, 452.94, 478.68,
  504.41, 545.59, 607.35,
]

// Tarifa plana: €80/month flat quota for new autonomos in their first 12 months.
// NOTE (C3): €80 was fixed by DT5 RDL 13/2022 for 2023–2025 only; from 2026 the amount
// is set by each year's Ley de Presupuestos, and neither RDL 3/2026 nor Orden
// PJC/297/2026 establishes a 2026 amount (see radarfiscal.es/en/guias/tarifa-plana-autonomos/).
// The calculator keeps €80 as the working estimate and shows an on-page disclaimer
// (r-tarifa-2026) whenever tarifa plana applies. Revisit when the BOE publishes the 2026 rate.
const TARIFA_PLANA = 80

// ── C4: societario (director) minimum quota floor ─────────────────────────────
// Directors/shareholders (autónomo societario) have a higher minimum contribution base.
// Source: Orden PJC/297/2026 (BOE-A-2026-7296) + Seguridad Social Importass guide,
// via infoautonomos.com/seguridad-social/cuota-autonomos-societarios/ (verified 2026-09-15):
// minimum base for annual regularization = €1,424.40 (provisional €1,000 allowed during
// the year if registered ≥90 days in 2026). Monthly floor quota = base × 31.50% tipo total
// (28.30% comunes + 1.30% profesionales + 0.90% MEI + 0.90% cese + 0.10% FP).
// VERIFY: re-check against BOE/Importass if Orden PJC/297/2026 is amended for 2027+.
const SOCIETARIO_MIN_BASE = 1424.40
const SOCIETARIO_MIN_QUOTA = Math.round(SOCIETARIO_MIN_BASE * 0.315 * 100) / 100 // = 448.69

/**
 * Returns the minimum monthly SS quotas array for the given year.
 * Only 2026 is officially published; all other years use the same values.
 *
 * @returns {number[]} 15-element array (index 0 = bracket 1)
 */
// NOTE: year parameter reserved for future use when 2027+ quotas are published.
function getSSQuotasForYear(_year) {
  return SS_MIN_QUOTAS_2026
}

/**
 * Find the SS bracket for a given monthly net income.
 *
 * @param {number} monthlyNetIncome
 * @returns {{id:number, maxMonthly:number}}
 */
export function findSSBracket(monthlyNetIncome) {
  for (const bracket of SS_BRACKET_THRESHOLDS) {
    if (monthlyNetIncome <= bracket.maxMonthly) return bracket
  }
  return SS_BRACKET_THRESHOLDS[SS_BRACKET_THRESHOLDS.length - 1]
}

/**
 * Returns the monthly SS quota for a given net income, year, and autonomo status.
 *
 * Directors (autónomo societario) get a floor: max(bracket quota, SOCIETARIO_MIN_QUOTA).
 * Tarifa plana (new) takes precedence over the floor.
 *
 * @param {number} monthlyNetIncome
 * @param {number} year
 * @param {'new'|'mid'|'established'} timeAsAutonomo
 * @param {'individual'|'director'} [autonomoType='individual']
 * @returns {{ bracketId: number, monthlyQuota: number, isTarifaPlana: boolean }}
 */
export function findSSQuota(monthlyNetIncome, year, timeAsAutonomo, autonomoType = 'individual') {
  const bracket = findSSBracket(monthlyNetIncome)
  if (timeAsAutonomo === 'new') {
    return { bracketId: bracket.id, monthlyQuota: TARIFA_PLANA, isTarifaPlana: true }
  }
  if (!['new', 'mid', 'established'].includes(timeAsAutonomo)) {
    console.warn(`[autonomo] findSSQuota: unrecognized timeAsAutonomo "${timeAsAutonomo}", using bracket-based quota`)
  }
  const quotas = getSSQuotasForYear(year)
  const bracketQuota = quotas[bracket.id - 1]
  const monthlyQuota = autonomoType === 'director'
    ? Math.max(bracketQuota, SOCIETARIO_MIN_QUOTA)
    : bracketQuota
  return { bracketId: bracket.id, monthlyQuota, isTarifaPlana: false }
}

/**
 * Returns the minimum monthly RETA SS quota for an autonomo colaborador.
 * No tarifa plana — collaborators are not new autonomos.
 *
 * @param {number} monthlyIncome - monthly gross income (€)
 * @param {number} [year=2026]
 * @returns {{ bracketId: number, monthlyQuota: number }}
 */
export function findSSQuotaForCollaborator(monthlyIncome, year = 2026) {
  if (monthlyIncome <= 0) return { bracketId: 0, monthlyQuota: 0 }
  const bracket = findSSBracket(monthlyIncome)
  const quotas = getSSQuotasForYear(year)
  return { bracketId: bracket.id, monthlyQuota: quotas[bracket.id - 1] }
}

// ── IRPF ──────────────────────────────────────────────────────────────────────

/**
 * IRPF state brackets (tramo estatal) — unchanged since 2024; valid for 2026.
 * Applied to "base liquidable general" (taxable income after personal minimums).
 */
const IRPF_STATE_BRACKETS = [
  { upTo: 12450,    rate: 0.095  },
  { upTo: 20200,    rate: 0.12   },
  { upTo: 35200,    rate: 0.15   },
  { upTo: 60000,    rate: 0.185  },
  { upTo: 300000,   rate: 0.225  },
  { upTo: Infinity, rate: 0.245  },
]

/**
 * IRPF regional brackets (tramo autonómico) by region — 2026 values.
 * Each region has its own income thresholds and rates, independent of state brackets.
 * Source: taxdown.es/irpf/tabla-tramos
 * Navarra and País Vasco have foral regimes; values here are educational estimates.
 *
 * @type {Record<string, Array<{upTo:number, rate:number}>>}
 */
const IRPF_REGIONAL_BRACKETS = {
  andalucia: [
    { upTo: 13000,    rate: 0.095  },
    { upTo: 21000,    rate: 0.12   },
    { upTo: 35200,    rate: 0.15   },
    { upTo: 50000,    rate: 0.185  },
    { upTo: Infinity, rate: 0.225  },
  ],
  aragon: [
    { upTo: 13972.50, rate: 0.095  },
    { upTo: 21210,    rate: 0.12   },
    { upTo: 36960,    rate: 0.15   },
    { upTo: 52500,    rate: 0.185  },
    { upTo: 60000,    rate: 0.205  },
    { upTo: 80000,    rate: 0.23   },
    { upTo: 90000,    rate: 0.24   },
    { upTo: 130000,   rate: 0.25   },
    { upTo: Infinity, rate: 0.255  },
  ],
  asturias: [
    { upTo: 12450,    rate: 0.10   },
    { upTo: 17707,    rate: 0.12   },
    { upTo: 33007,    rate: 0.14   },
    { upTo: 53407,    rate: 0.185  },
    { upTo: 70000,    rate: 0.215  },
    { upTo: 90000,    rate: 0.225  },
    { upTo: 175000,   rate: 0.25   },
    { upTo: Infinity, rate: 0.255  },
  ],
  baleares: [
    { upTo: 10000,    rate: 0.09   },
    { upTo: 18000,    rate: 0.1125 },
    { upTo: 30000,    rate: 0.1425 },
    { upTo: 48000,    rate: 0.175  },
    { upTo: 70000,    rate: 0.19   },
    { upTo: 90000,    rate: 0.2175 },
    { upTo: 120000,   rate: 0.2275 },
    { upTo: 175000,   rate: 0.2375 },
    { upTo: Infinity, rate: 0.2475 },
  ],
  canarias: [
    { upTo: 12450,    rate: 0.09   },
    { upTo: 17707,    rate: 0.115  },
    { upTo: 33007,    rate: 0.14   },
    { upTo: 53407,    rate: 0.185  },
    { upTo: 90000,    rate: 0.235  },
    { upTo: 120000,   rate: 0.25   },
    { upTo: Infinity, rate: 0.26   },
  ],
  cantabria: [
    { upTo: 13000,    rate: 0.085  },
    { upTo: 21000,    rate: 0.11   },
    { upTo: 35200,    rate: 0.145  },
    { upTo: 60000,    rate: 0.18   },
    { upTo: 90000,    rate: 0.225  },
    { upTo: Infinity, rate: 0.245  },
  ],
  castilla_la_mancha: [
    { upTo: 12450,    rate: 0.095  },
    { upTo: 20200,    rate: 0.12   },
    { upTo: 35200,    rate: 0.15   },
    { upTo: 60000,    rate: 0.185  },
    { upTo: Infinity, rate: 0.225  },
  ],
  castilla_leon: [
    { upTo: 12450,    rate: 0.09   },
    { upTo: 20200,    rate: 0.12   },
    { upTo: 35200,    rate: 0.14   },
    { upTo: 53407,    rate: 0.185  },
    { upTo: Infinity, rate: 0.215  },
  ],
  catalunya: [
    // 2026 scale: AEAT Manual Renta 2025 Cap.15 Catalunya; DL 1/2024 art. 611-1.
    { upTo: 12500,    rate: 0.095  },
    { upTo: 22000,    rate: 0.125  },
    { upTo: 33000,    rate: 0.16   },
    { upTo: 53000,    rate: 0.19   },
    { upTo: 90000,    rate: 0.215  },
    { upTo: 120000,   rate: 0.235  },
    { upTo: 175000,   rate: 0.245  },
    { upTo: Infinity, rate: 0.255  },
  ],
  comunidad_valenciana: [
    // 2026 deflated scale (Ley 13/1997; DOGV Ley 5/2026; cross-checked via
    // guiafiscal.es/irpf/valencia, verified 2026-07-29). Matches AEAT Manual
    // Renta 2025 minus ~0.2-0.4pp deflation applied for 2026.
    { upTo: 12000,    rate: 0.088  },
    { upTo: 22000,    rate: 0.117  },
    { upTo: 32000,    rate: 0.146  },
    { upTo: 42000,    rate: 0.17   },
    { upTo: 52000,    rate: 0.194  },
    { upTo: 62000,    rate: 0.219  },
    { upTo: 72000,    rate: 0.244  },
    { upTo: 100000,   rate: 0.261  },
    { upTo: 150000,   rate: 0.2735 },
    { upTo: 200000,   rate: 0.2835 },
    { upTo: Infinity, rate: 0.2935 },
  ],
  extremadura: [
    { upTo: 12450,    rate: 0.08   },
    { upTo: 20200,    rate: 0.10   },
    { upTo: 24200,    rate: 0.16   },
    { upTo: 35200,    rate: 0.175  },
    { upTo: 60000,    rate: 0.21   },
    { upTo: 80200,    rate: 0.235  },
    { upTo: 99200,    rate: 0.24   },
    { upTo: 120200,   rate: 0.245  },
    { upTo: Infinity, rate: 0.25   },
  ],
  galicia: [
    { upTo: 12985,    rate: 0.09   },
    { upTo: 21068,    rate: 0.1165 },
    { upTo: 35200,    rate: 0.149  },
    { upTo: 47600,    rate: 0.184  },
    { upTo: Infinity, rate: 0.225  },
  ],
  madrid: [
    { upTo: 13362,    rate: 0.085  },
    { upTo: 18004,    rate: 0.107  },
    { upTo: 35425,    rate: 0.128  },
    { upTo: 57320,    rate: 0.174  },
    { upTo: Infinity, rate: 0.205  },
  ],
  murcia: [
    { upTo: 12450,    rate: 0.095  },
    { upTo: 20200,    rate: 0.112  },
    { upTo: 34000,    rate: 0.133  },
    { upTo: 60000,    rate: 0.179  },
    { upTo: Infinity, rate: 0.225  },
  ],
  la_rioja: [
    { upTo: 12450,    rate: 0.08   },
    { upTo: 20200,    rate: 0.106  },
    { upTo: 35200,    rate: 0.136  },
    { upTo: 40000,    rate: 0.178  },
    { upTo: 50000,    rate: 0.185  },
    { upTo: 60000,    rate: 0.19   },
    { upTo: 120000,   rate: 0.245  },
    { upTo: Infinity, rate: 0.27   },
  ],
  // Foral regimes — UNUSED (regions removed from selector, see M3).
  // Reserved for future foral support: state=0 + real foral scales + foral minimums.
  navarra: [
    { upTo: 12450,    rate: 0.085  },
    { upTo: 20200,    rate: 0.105  },
    { upTo: 35200,    rate: 0.145  },
    { upTo: 60000,    rate: 0.175  },
    { upTo: 300000,   rate: 0.22   },
    { upTo: Infinity, rate: 0.235  },
  ],
  pais_vasco: [
    { upTo: 12450,    rate: 0.07   },
    { upTo: 20200,    rate: 0.10   },
    { upTo: 35200,    rate: 0.135  },
    { upTo: 60000,    rate: 0.165  },
    { upTo: 300000,   rate: 0.20   },
    { upTo: Infinity, rate: 0.22   },
  ],
  // Ceuta and Melilla — regional component uses standard bracket estimates only.
  // Art. 68.4 LIRPF 60% reduction for residents is applied in calculateAutonomo
  // (irpfTotal x 0.4 for these regions).
  ceuta:   [
    { upTo: 12450,    rate: 0.095  },
    { upTo: 20200,    rate: 0.12   },
    { upTo: 35200,    rate: 0.15   },
    { upTo: 60000,    rate: 0.185  },
    { upTo: 300000,   rate: 0.225  },
    { upTo: Infinity, rate: 0.245  },
  ],
  melilla: [
    { upTo: 12450,    rate: 0.095  },
    { upTo: 20200,    rate: 0.12   },
    { upTo: 35200,    rate: 0.15   },
    { upTo: 60000,    rate: 0.185  },
    { upTo: 300000,   rate: 0.225  },
    { upTo: Infinity, rate: 0.245  },
  ],
}

/** Fallback for unknown regions — mirrors state bracket structure. */
const DEFAULT_REGIONAL_BRACKETS = [
  { upTo: 12450,    rate: 0.095  },
  { upTo: 20200,    rate: 0.12   },
  { upTo: 35200,    rate: 0.15   },
  { upTo: 60000,    rate: 0.185  },
  { upTo: 300000,   rate: 0.225  },
  { upTo: Infinity, rate: 0.245  },
]

/**
 * Compute progressive IRPF using a bracket table.
 *
 * @param {number} base - taxable income (€)
 * @param {Array<{upTo:number, rate:number}>} brackets
 * @returns {number} tax owed (€)
 */
export function calcProgressiveTax(base, brackets) {
  if (base <= 0) return 0
  let tax = 0
  let prev = 0
  for (const { upTo, rate } of brackets) {
    if (base <= prev) break
    const slice = Math.min(base, upTo) - prev
    tax += slice * rate
    prev = upTo
    if (upTo === Infinity || base <= upTo) break
  }
  return Math.round(tax * 100) / 100
}

/**
 * Compute progressive IRPF with per-bracket breakdown.
 *
 * @param {number} base - taxable income (€)
 * @param {Array<{upTo:number, rate:number}>} brackets
 * @returns {{
 *   total: number,
 *   brackets: Array<{from:number, to:number|null, rate:number, taxableAmount:number, taxAmount:number}>
 * }}
 */
export function calcProgressiveTaxWithBreakdown(base, brackets) {
  if (base <= 0) return { total: 0, brackets: [] }
  let tax = 0
  let prev = 0
  const result = []
  for (const { upTo, rate } of brackets) {
    if (base <= prev) break
    const slice = Math.min(base, upTo) - prev
    const taxAmount = Math.round(slice * rate * 100) / 100
    tax += taxAmount
    result.push({
      from: prev,
      to: upTo === Infinity ? null : upTo,
      rate,
      taxableAmount: Math.round(slice * 100) / 100,
      taxAmount,
    })
    prev = upTo
    if (upTo === Infinity || base <= upTo) break
  }
  return { total: Math.round(tax * 100) / 100, brackets: result }
}

/**
 * Compute state IRPF on the given base.
 *
 * @param {number} base
 * @returns {number}
 */
export function calcIrpfState(base) {
  return calcProgressiveTax(base, IRPF_STATE_BRACKETS)
}

/**
 * Compute state IRPF with per-bracket breakdown.
 *
 * @param {number} base
 * @returns {{ total: number, brackets: Array }}
 */
export function calcIrpfStateWithBreakdown(base) {
  return calcProgressiveTaxWithBreakdown(base, IRPF_STATE_BRACKETS)
}

/**
 * Compute regional IRPF for the given region and base.
 *
 * @param {number} base
 * @param {string} region
 * @returns {number}
 */
export function calcIrpfRegional(base, region) {
  const brackets = IRPF_REGIONAL_BRACKETS[region]
  if (!brackets) {
    console.warn(`[autonomo] calcIrpfRegional: unrecognized region "${region}", using default brackets.`)
  }
  return calcProgressiveTax(base, brackets ?? DEFAULT_REGIONAL_BRACKETS)
}

/**
 * Compute regional IRPF with per-bracket breakdown.
 *
 * @param {number} base
 * @param {string} region
 * @returns {{ total: number, brackets: Array }}
 */
export function calcIrpfRegionalWithBreakdown(base, region) {
  const brackets = IRPF_REGIONAL_BRACKETS[region]
  if (!brackets) {
    console.warn(`[autonomo] calcIrpfRegionalWithBreakdown: unrecognized region "${region}", using default brackets.`)
  }
  return calcProgressiveTaxWithBreakdown(base, brackets ?? DEFAULT_REGIONAL_BRACKETS)
}

// ── Deductions ────────────────────────────────────────────────────────────────

/** General expenses deduction for SS bracket — 7% for individuals (max €2,000), 3% for directors (max €2,000).
 *  Art. 308 LGSS: rendimiento neto for RETA includes this deduction. */
const GENERAL_EXPENSES_RATE = { individual: 0.07, director: 0.03 }
const GENERAL_EXPENSES_MAX = 2000

/**
 * @param {number} annualNetRevenue
 * @param {'individual'|'director'} autonomoType
 * @returns {number}
 */
export function calcGeneralExpenses(annualNetRevenue, autonomoType) {
  const rate = GENERAL_EXPENSES_RATE[autonomoType]
  if (rate === undefined) {
    console.warn(`[autonomo] calcGeneralExpenses: unrecognized autonomoType "${autonomoType}", using default 7% rate`)
  }
  return Math.round(Math.min(Math.max(0, annualNetRevenue) * (rate ?? 0.07), GENERAL_EXPENSES_MAX) * 100) / 100
}

/** IRPF deduction under estimación directa simplificada — 5% flat for everyone (max €2,000).
 *  Gastos de difícil justificación (Art. 30.2.5ª RIRPF). Unlike the SS deduction, the
 *  autonomo type (individual vs director) does NOT change this rate. */
const IRPF_DEDUCTION_RATE = 0.05
const IRPF_DEDUCTION_MAX = 2000

/**
 * @param {number} annualNetRevenue
 * @returns {number}
 */
export function calcIrpfDeduction(annualNetRevenue) {
  return Math.round(Math.min(Math.max(0, annualNetRevenue) * IRPF_DEDUCTION_RATE, IRPF_DEDUCTION_MAX) * 100) / 100
}

// ── Personal minimum ──────────────────────────────────────────────────────────

const PERSONAL_MIN_BASE = 5550
const AGE_65_EXTRA      = 1150
const AGE_75_EXTRA      = 1400  // additional on top of AGE_65_EXTRA
const CHILD_ALLOWANCES  = [2400, 2700, 4000, 4500]  // 1st, 2nd, 3rd, 4th+
const CHILD_U3_EXTRA    = 2800                       // per child under 3
const DISABILITY_ALLOWANCE = { 33: 3000, 65: 9000 } // 33%+ and 65%+ disability
// Art. 59-60 LIRPF (BOE-A-2006-20764): ascendientes convivientes >65 o discapacitados
// (cualquier edad) +1150 c/u; +1400 adicional si >75. Movilidad reducida (o ayuda de
// terceras personas) con 33-65% anade +3000 (total 6000); con >=65% los +3000 aplican
// siempre (9000 + 3000 = 12000). Requisitos de convivencia/renta (<=8000 EUR) se
// advierten en el tooltip del UI; no hay checkboxes de renta separados.
const ASCENDANT_65_EXTRA = 1150
const ASCENDANT_75_EXTRA = 1400  // additional on top of ASCENDANT_65_EXTRA
const MOBILITY_EXTRA = 3000

/**
 * Compute the total personal minimum allowance (mínimo personal y familiar).
 *
 * @param {{ age:number, numChildren:number, childrenUnder3:number, disabilityLevel:0|33|65, numParents65?:number, numParents75?:number, reducedMobility?:boolean }} params
 * @returns {number}
 */
export function calcPersonalMinimum({ age = 35, numChildren = 0, childrenUnder3 = 0, disabilityLevel = 0, numParents65 = 0, numParents75 = 0, reducedMobility = false }) {
  let min = PERSONAL_MIN_BASE

  if (age >= 75) min += AGE_65_EXTRA + AGE_75_EXTRA
  else if (age >= 65) min += AGE_65_EXTRA

  const safeChildren = Math.max(0, Math.round(numChildren))
  for (let i = 0; i < safeChildren; i++) {
    min += CHILD_ALLOWANCES[Math.min(i, CHILD_ALLOWANCES.length - 1)]
  }

  const safeU3 = Math.min(Math.max(0, Math.round(childrenUnder3)), safeChildren)
  min += safeU3 * CHILD_U3_EXTRA

  if (disabilityLevel >= 65) min += DISABILITY_ALLOWANCE[65] + MOBILITY_EXTRA
  else if (disabilityLevel >= 33) min += DISABILITY_ALLOWANCE[33] + (reducedMobility ? MOBILITY_EXTRA : 0)

  const safeParents65 = Math.min(Math.max(0, Math.round(numParents65)), 4)
  const safeParents75 = Math.min(Math.max(0, Math.round(numParents75)), safeParents65)
  min += safeParents65 * ASCENDANT_65_EXTRA + safeParents75 * ASCENDANT_75_EXTRA

  return min
}

// ── Main calculation ──────────────────────────────────────────────────────────

/**
 * Calculate full autónomo tax breakdown.
 *
 * @param {{
 *   annualNetRevenue: number,
 *   autonomoType: 'individual'|'director',
 *   timeAsAutonomo: 'new'|'mid'|'established',
 *   region: string,
 *   year: number,
 *   age: number,
 *   numChildren: number,
 *   childrenUnder3: number,
 *   disabilityLevel: 0|33|65,
 *   numParents65: number,
 *   numParents75: number,
 *   reducedMobility: boolean,
 * }} params
 * @returns {{
 *   monthlyNetIncome: number,
 *   ssBracketId: number,
 *   isTarifaPlana: boolean,
 *   monthlySSQuota: number,
 *   annualSSTotal: number,
 *   generalExpensesDeduction: number, // legacy alias of ssDeduction
 *   ssDeduction: number,
 *   irpfDeduction: number,
 *   reducedNetIncome: number,
 *   personalMinimum: number,
 *   irpfBase: number,
 *   irpfState: number,
 *   irpfRegional: number,
 *   irpfTotal: number,
 *   effectiveIrpfRate: number,
 *   totalBurden: number,
 *   effectiveTotalRate: number,
 *   netTakeHome: number,
 *   netTakeHomeMonthly: number,
 * }}
 */
export function calculateAutonomo({
  annualNetRevenue,
  autonomoType = 'individual',
  timeAsAutonomo = 'established',
  region = 'madrid',
  year = 2026,
  age = 35,
  numChildren = 0,
  childrenUnder3 = 0,
  disabilityLevel = 0,
  numParents65 = 0,
  numParents75 = 0,
  reducedMobility = false,
}) {
  const revenue = Math.max(0, annualNetRevenue)
  const monthlyNetIncome = revenue / 12

  // SS deduction (7% individual / 3% director, cap €2,000) — determines the SS bracket only.
  const ssDeduction = calcGeneralExpenses(revenue, autonomoType)
  const generalExpensesDeduction = ssDeduction // legacy alias, kept for compatibility

  // IRPF deduction (5% flat for everyone, cap €2,000) — goes into the IRPF base only.
  const irpfDeduction = calcIrpfDeduction(revenue)

  // Social Security bracket is determined on income after the SS deduction,
  // per Spanish law (rendimiento neto for estimación directa simplificada includes this deduction).
  const monthlyIncomeForSS = Math.max(0, revenue - ssDeduction) / 12
  const { bracketId: ssBracketId, monthlyQuota: monthlySSQuota, isTarifaPlana } =
    findSSQuota(monthlyIncomeForSS, year, timeAsAutonomo, autonomoType)
  const annualSSTotal = Math.round(monthlySSQuota * 12 * 100) / 100

  // IRPF base (base imponible) = revenue after SS contributions and the 5% IRPF deduction
  const reducedNetIncome = Math.max(0, revenue - annualSSTotal - irpfDeduction)

  // Personal minimum allowances
  const personalMinimum = calcPersonalMinimum({ age, numChildren, childrenUnder3, disabilityLevel, numParents65, numParents75, reducedMobility })

  // IRPF: Spanish law computes Tax(base) - Tax(personalMin), NOT Tax(base - personalMin).
  // The personal minimum reduces the tax owed, not the taxable base.
  // Math.max(0, ...) enforces that the personal minimum cannot reduce IRPF below zero (Art. 56 LIRPF).
  const irpfStateFull = Math.max(0, Math.round(
    (calcIrpfState(reducedNetIncome) - calcIrpfState(personalMinimum)) * 100
  ) / 100)
  const irpfRegionalFull = Math.max(0, Math.round(
    (calcIrpfRegional(reducedNetIncome, region) - calcIrpfRegional(personalMinimum, region)) * 100
  ) / 100)
  // Art. 68.4 LIRPF: Ceuta/Melilla residents deduct 60% of the cuotas integras
  // (state + regional), i.e. pay 40% of the full IRPF.
  const ceutaReduction = (region === 'ceuta' || region === 'melilla')
  const irpfState = ceutaReduction ? Math.round(irpfStateFull * 0.4 * 100) / 100 : irpfStateFull
  const irpfRegional = ceutaReduction ? Math.round(irpfRegionalFull * 0.4 * 100) / 100 : irpfRegionalFull
  const irpfTotal = Math.round((irpfState + irpfRegional) * 100) / 100

  const effectiveIrpfRate = revenue > 0 ? irpfTotal / revenue : 0
  const totalBurden = annualSSTotal + irpfTotal
  const effectiveTotalRate = revenue > 0 ? totalBurden / revenue : 0
  const netTakeHome = Math.max(0, revenue - totalBurden)
  const netTakeHomeMonthly = Math.round((netTakeHome / 12) * 100) / 100

  return {
    monthlyNetIncome: Math.round(monthlyNetIncome * 100) / 100,
    ssBracketId,
    isTarifaPlana,
    monthlySSQuota,
    annualSSTotal,
    generalExpensesDeduction: Math.round(generalExpensesDeduction * 100) / 100,
    ssDeduction: Math.round(ssDeduction * 100) / 100,
    irpfDeduction: Math.round(irpfDeduction * 100) / 100,
    reducedNetIncome: Math.round(reducedNetIncome * 100) / 100,
    personalMinimum,
    irpfBase: Math.round(reducedNetIncome * 100) / 100, // alias for reducedNetIncome, used by UI
    irpfState,
    irpfRegional,
    irpfTotal,
    effectiveIrpfRate: Math.round(effectiveIrpfRate * 10000) / 10000,
    totalBurden: Math.round(totalBurden * 100) / 100,
    effectiveTotalRate: Math.round(effectiveTotalRate * 10000) / 10000,
    netTakeHome: Math.round(netTakeHome * 100) / 100,
    netTakeHomeMonthly,
  }
}
