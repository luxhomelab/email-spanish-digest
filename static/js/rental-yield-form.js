// Pure state validation for the Spanified rental yield calculator.
// No DOM access here — unit-tested with node:test, reused by rental-yield.js.

export const TAX_STATUSES = ['resident', 'non_resident_eu', 'non_resident_non_eu']
export const PROPERTY_TYPES = ['resale', 'new']
export const REDUCTION_VALUES = [0, 50, 60, 70, 90, 100]
export const MAX_MONEY = 1e9

export const DEFAULTS = {
  purchasePrice: 250000,
  propertyType: 'resale',
  regionId: 'madrid',
  closingCostsPct: 2,
  renovationCost: 20000,
  renovationDurationMonths: 3,
  valueAfterRepairs: 270000,
  useRenovation: false,
  useLoan: false,
  downPaymentPct: 20,
  interestRateAnnual: 3.0,
  loanTermYears: 30,
  loanOpeningFee: 0,
  monthlyRent: 1200,
  vacancyRatePct: 5,
  rentGrowthPct: 2,
  annualIBI: 600,
  monthlyCommunity: 80,
  annualHomeInsurance: 300,
  annualRentalInsurance: 0,
  maintenanceRatePct: 5,
  managementFeePct: 0,
  expenseGrowthRatePct: 2,
  taxStatus: 'resident',
  personalTaxRatePct: 30,
  rentalReductionPct: 50,
  useNonEuDeductions: false,
  constructionSharePct: 70,
  costToSellPct: 3,
  plusvalia: 0,
  holdYears: 30,
  appreciationRatePct: 3,
}

export const QUERY_KEYS = {
  purchasePrice: 'ry_pp',
  propertyType: 'ry_pt',
  regionId: 'ry_r',
  closingCostsPct: 'ry_cc',
  renovationCost: 'ry_ren',
  renovationDurationMonths: 'ry_rdur',
  valueAfterRepairs: 'ry_var',
  useRenovation: 'ry_uren',
  useLoan: 'ry_loan',
  downPaymentPct: 'ry_dp',
  interestRateAnnual: 'ry_ir',
  loanTermYears: 'ry_lt',
  loanOpeningFee: 'ry_lof',
  monthlyRent: 'ry_rent',
  vacancyRatePct: 'ry_vac',
  rentGrowthPct: 'ry_rg',
  annualIBI: 'ry_ibi',
  monthlyCommunity: 'ry_com',
  annualHomeInsurance: 'ry_hi',
  annualRentalInsurance: 'ry_ri',
  maintenanceRatePct: 'ry_mnt',
  managementFeePct: 'ry_mgmt',
  expenseGrowthRatePct: 'ry_eg',
  taxStatus: 'ry_ts',
  personalTaxRatePct: 'ry_ptr',
  rentalReductionPct: 'ry_red',
  useNonEuDeductions: 'ry_neu',
  constructionSharePct: 'ry_cs',
  costToSellPct: 'ry_cts',
  plusvalia: 'ry_plus',
  holdYears: 'ry_hy',
  appreciationRatePct: 'ry_apr',
}

export const FIELD_LIMITS = {
  purchasePrice: { type: 'money', min: 0 },
  renovationCost: { type: 'money', min: 0 },
  valueAfterRepairs: { type: 'money', min: 0 },
  annualIBI: { type: 'money', min: 0 },
  monthlyCommunity: { type: 'money', min: 0 },
  annualHomeInsurance: { type: 'money', min: 0 },
  annualRentalInsurance: { type: 'money', min: 0 },
  loanOpeningFee: { type: 'money', min: 0 },
  monthlyRent: { type: 'money', min: 0 },
  plusvalia: { type: 'money', min: 0 },
  closingCostsPct: { type: 'percent', min: 0, max: 100 },
  downPaymentPct: { type: 'percent', min: 0, max: 100 },
  interestRateAnnual: { type: 'percent', min: 0, max: 100 },
  vacancyRatePct: { type: 'percent', min: 0, max: 100 },
  rentGrowthPct: { type: 'percent', min: 0, max: 100 },
  maintenanceRatePct: { type: 'percent', min: 0, max: 100 },
  managementFeePct: { type: 'percent', min: 0, max: 100 },
  expenseGrowthRatePct: { type: 'percent', min: 0, max: 100 },
  personalTaxRatePct: { type: 'percent', min: 0, max: 100 },
  constructionSharePct: { type: 'percent', min: 0, max: 100 },
  costToSellPct: { type: 'percent', min: 0, max: 100 },
  appreciationRatePct: { type: 'percent', min: 0, max: 100 },
  renovationDurationMonths: { type: 'int', min: 0, max: 24 },
  loanTermYears: { type: 'int', min: 1, max: 50 },
  holdYears: { type: 'int', min: 1, max: 50 },
}

const BOOL_KEYS = ['useRenovation', 'useLoan', 'useNonEuDeductions']

export function toBool(v) {
  return v === true || v === 1 || v === '1' || v === 'true'
}

/** Clamp a single numeric field to its limits; garbage falls back to the default. */
export function clampField(key, raw) {
  const lim = FIELD_LIMITS[key]
  if (raw === '' || raw === null || raw === undefined) return DEFAULTS[key]
  let n = Number(raw)
  if (!Number.isFinite(n)) return DEFAULTS[key]
  if (lim.type === 'int') n = Math.trunc(n)
  const max = lim.max ?? MAX_MONEY
  return Math.min(max, Math.max(lim.min, n))
}

/**
 * Totally ordered sanitizer: every field falls back to DEFAULTS on garbage.
 * regions: valid region ids (injected for testability); null accepts any non-empty id.
 */
export function sanitizeState(raw = {}, regions = null) {
  const valid = regions ? new Set(regions) : null
  const out = {}
  for (const key of Object.keys(FIELD_LIMITS)) out[key] = clampField(key, raw[key])
  for (const key of BOOL_KEYS) out[key] = toBool(raw[key])
  out.propertyType = PROPERTY_TYPES.includes(raw.propertyType) ? raw.propertyType : DEFAULTS.propertyType
  out.taxStatus = TAX_STATUSES.includes(raw.taxStatus) ? raw.taxStatus : DEFAULTS.taxStatus
  const red = Number(raw.rentalReductionPct)
  out.rentalReductionPct = raw.rentalReductionPct !== '' && raw.rentalReductionPct != null && REDUCTION_VALUES.includes(red)
    ? red : DEFAULTS.rentalReductionPct
  out.regionId = valid
    ? (valid.has(raw.regionId) ? raw.regionId : DEFAULTS.regionId)
    : (raw.regionId || DEFAULTS.regionId)
  return out
}

/**
 * Parse shareable-URL state. Returns null when no known params are present.
 */
export function parseStateFromParams(search, regions = null) {
  const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search)
  const hasAny = Object.values(QUERY_KEYS).some(k => params.has(k))
  if (!hasAny) return null
  const raw = {}
  for (const [key, param] of Object.entries(QUERY_KEYS)) {
    const v = params.get(param)
    if (v != null) raw[key] = v
  }
  return sanitizeState(raw, regions)
}

/** Serialize state to query params (booleans as 1/0). */
export function stateToParams(state) {
  const p = new URLSearchParams()
  for (const [key, param] of Object.entries(QUERY_KEYS)) {
    let v = state[key]
    if (typeof v === 'boolean') v = v ? '1' : '0'
    p.set(param, String(v))
  }
  return p
}
