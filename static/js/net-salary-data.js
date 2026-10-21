/**
 * Spanish employee payroll data for 2026 (net salary calculator).
 *
 * Sources (verified 2026-10-21):
 * - Social Security: Orden PJC/297/2026 (bases y tipos de cotización 2026) — base máxima
 *   5.101,20 €/mes; MEI 0,90% (0,75 empresa / 0,15 trabajador); cotización adicional de
 *   solidaridad 1,15 / 1,25 / 1,46%, split in the contingencias comunes proportion.
 * - IRPF: Ley 35/2006 arts. 19.2.f (otros gastos), 20 (reducción, RDL 4/2024),
 *   56-61 (mínimos), 84 (tributación conjunta), 51-52 (previsión social), 68.4 (Ceuta y
 *   Melilla), 93 (Beckham); DA 61ª (deducción SMI, raised to 590,89 € by RDL 5/2026).
 * - Regional minimums: AEAT Manual práctico Renta 2025, "Cuadro comparativo de los
 *   importes de los mínimos personales y familiares" (updated 17/03/2026).
 * - Withholding: AEAT "Algoritmo de cálculo del tipo de retención 2026" (09-09-2026).
 * Results are estimates; not tax advice.
 */

// ── Social Security ──────────────────────────────────────────────────────────

export const SS_BASE_MAX_MONTHLY = 5101.20

export const SS_EMPLOYEE_RATES = {
  cc: 0.047,
  unemployment: { permanent: 0.0155, temporary: 0.016 },
  fp: 0.001,
  mei: 0.0015,
}

export const SS_EMPLOYER_RATES = {
  cc: 0.236,
  unemployment: { permanent: 0.055, temporary: 0.067 },
  fogasa: 0.002,
  fp: 0.006,
  mei: 0.0075,
}

/** Cotización adicional de solidaridad: bands over the monthly excess above the max base,
 *  as a share of that base. Employee pays 4,70/28,30 of each rate. */
export const SOLIDARITY_BANDS = [
  { upToShare: 0.10, rate: 0.0115 },
  { upToShare: 0.50, rate: 0.0125 },
  { upToShare: Infinity, rate: 0.0146 },
]
export const SOLIDARITY_EMPLOYEE_SHARE = 4.70 / 28.30

// ── IRPF ─────────────────────────────────────────────────────────────────────

export const OTHER_EXPENSES = { general: 2000, mobility: 2000, disabled33: 3500, disabled65: 7750 }

export const WORK_REDUCTION = {
  max: 7302, lower: 14852, mid: 17673.52, midAmount: 2364.34, upper: 19747.5,
  slope1: 1.75, slope2: 1.14,
}

export const SMI_DEDUCTION = { amount: 590.89, from: 17094, to: 20048.45, slope: 0.2 }

export const JOINT_REDUCTION = { married: 3400, single: 2150 }

export const PENSION_LIMITS = { employee: 1500, employer: 8500, incomeShare: 0.30 }

export const CEUTA_MELILLA_SHARE = 0.4

export const BECKHAM = { rate: 0.24, threshold: 600000, topRate: 0.47 }

/** Flexible pay exemptions (art. 42.3 LIRPF, art. 45-46 RIRPF). */
export const FLEX_LIMITS = { healthPerPerson: 500, mealsPerDay: 11, workDays: 220, transport: 1500 }

/** Mínimo personal y familiar. `assist` is the extra for ≥65% or 33% with assistance. */
const STATE_MINIMUMS = {
  contrib: 5550, age65: 1150, age75: 1400,
  desc: [2400, 2700, 4000, 4500], u3: 2800,
  asc65: 1150, asc75: 1400,
  dis33: 3000, dis65: 9000, assist: 3000,
}

const regional = over => ({ ...STATE_MINIMUMS, ...over })

/** Regions not listed here apply the state amounts to the regional cuota too. */
const REGIONAL_MINIMUMS = {
  andalucia: regional({ contrib: 5790, age65: 1200, age75: 1460, desc: [2510, 2820, 4170, 4700], u3: 2920,
    asc65: 1200, asc75: 1460, dis33: 3130, dis65: 9390, assist: 3130 }),
  asturias: regional({ contrib: 6105, age65: 1265, age75: 1540, desc: [2640, 2970, 4400, 4950], u3: 3080,
    asc65: 1265, asc75: 1540, dis33: 3300, dis65: 9900, assist: 3300 }),
  baleares: regional({ age65: 1265, age75: 1540, desc: [2400, 2970, 4400, 4950],
    asc65: 1265, asc75: 1540, dis33: 3300, dis65: 9900, assist: 3300 }),
  canarias: regional({ contrib: 5606, age65: 1162, age75: 1414, desc: [2424, 2727, 4040, 4545], u3: 2828,
    asc65: 1162, asc75: 1414, dis33: 3030, dis65: 9090, assist: 3030 }),
  galicia: regional({ contrib: 5789, age65: 1199, age75: 1460, desc: [2503, 2816, 4172, 4694], u3: 2920,
    asc65: 1199, asc75: 1460, dis33: 3129, dis65: 9387, assist: 3129 }),
  madrid: regional({ contrib: 5956.65, age65: 1234.26, age75: 1502.58, desc: [2575.85, 2897.83, 4400, 4950], u3: 3005.16,
    asc65: 1234.26, asc75: 1502.58, dis33: 3219.81, dis65: 9659.44, assist: 3219.81 }),
  comunidad_valenciana: regional({ contrib: 6105, age65: 1265, age75: 1540, desc: [2640, 2970, 4400, 4950], u3: 3080,
    asc65: 1265, asc75: 1540, dis33: 3300, dis65: 9900, assist: 3300 }),
  // La Rioja raises only the descendant disability amounts.
  la_rioja: regional({ descDis33: 3300, descDis65: 9900 }),
}

export function getMinimumTable(scope, region) {
  if (scope === 'state') return STATE_MINIMUMS
  return REGIONAL_MINIMUMS[region] || STATE_MINIMUMS
}

// ── Withholding (algoritmo AEAT 2026) ────────────────────────────────────────

export const WITHHOLDING_SCALE = [
  { upTo: 12450, rate: 0.19 },
  { upTo: 20200, rate: 0.24 },
  { upTo: 35200, rate: 0.30 },
  { upTo: 60000, rate: 0.37 },
  { upTo: 300000, rate: 0.45 },
  { upTo: Infinity, rate: 0.47 },
]

/** Límites excluyentes (art. 81 RIRPF, RD 142/2024): [situación][0, 1, 2+ children]. */
export const EXCLUSION_LIMITS = {
  1: [null, 17644, 18694],
  2: [17197, 18130, 19262],
  3: [15876, 16342, 16867],
}
export const WITHHOLDING_CAP = { share: 0.43, upToRetrib: 35200 }
export const WITHHOLDING_LARGE_FAMILY = { minChildren: 3, reduction: 600 }
export const WITHHOLDING_MIN_TEMPORARY = { general: 2, ceutaMelilla: 0.8 }
