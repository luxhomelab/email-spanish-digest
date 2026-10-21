// Pure state validation and shareable-URL encoding for the net salary calculator.
// No DOM access here — unit-tested with node:test, reused by net-salary.js.

export const PERIODS = ['y', 'm']
export const MODES = ['gross', 'net']
export const PAYMENTS = ['12', '14', '14p']
export const REGIMES = ['standard', 'beckham']
export const AGES = ['u65', '65to74', '75plus']
export const CONTRACTS = ['permanent', 'temporary']
export const DISABILITY = ['0', '33', '33h', '65']
export const DISABILITY_LIST = ['33', '33h', '65']
export const JOINT = ['none', 'married', 'single']
export const FLEX_MODES = ['sacrifice', 'extra']
export const MAX_DESC_DISAB = 6
export const MAX_ASC_DISAB = 4

export const DEFAULTS = {
  amount: 30000,
  period: 'y',
  mode: 'gross',
  payments: '12',
  region: 'madrid',
  regime: 'standard',
  age: 'u65',
  contract: 'permanent',
  disability: '0',
  mobility: false,
  joint: 'none',
  kidsU3: 0,
  kids: 0,
  sharedCustody: false,
  descDisab: [],
  asc65: 0,
  asc75: 0,
  ascDisab: [],
  health: 0,
  healthPersons: 1,
  healthMode: 'sacrifice',
  meals: 0,
  mealsMode: 'sacrifice',
  transport: 0,
  transportMode: 'sacrifice',
  nursery: 0,
  nurseryMode: 'sacrifice',
  pensionEmployee: 0,
  pensionEmployer: 0,
  hoursPerWeek: 40,
  atRate: 1.5,
}

export const QUERY_KEYS = {
  amount: 'ns_a',
  period: 'ns_p',
  mode: 'ns_md',
  payments: 'ns_n',
  region: 'ns_r',
  regime: 'ns_rg',
  age: 'ns_ag',
  contract: 'ns_ct',
  disability: 'ns_ds',
  mobility: 'ns_mob',
  joint: 'ns_j',
  kidsU3: 'ns_k3',
  kids: 'ns_k',
  sharedCustody: 'ns_ksh',
  descDisab: 'ns_dd',
  asc65: 'ns_a65',
  asc75: 'ns_a75',
  ascDisab: 'ns_ad',
  health: 'ns_hi',
  healthPersons: 'ns_hip',
  healthMode: 'ns_him',
  meals: 'ns_ml',
  mealsMode: 'ns_mlm',
  transport: 'ns_tr',
  transportMode: 'ns_trm',
  nursery: 'ns_nu',
  nurseryMode: 'ns_num',
  pensionEmployee: 'ns_pe',
  pensionEmployer: 'ns_pr',
  hoursPerWeek: 'ns_h',
  atRate: 'ns_at',
}

export const FIELD_LIMITS = {
  amount: { type: 'money', min: 0, max: 10000000 },
  kidsU3: { type: 'int', min: 0, max: 6 },
  kids: { type: 'int', min: 0, max: 10 },
  asc65: { type: 'int', min: 0, max: 4 },
  asc75: { type: 'int', min: 0, max: 4 },
  health: { type: 'money', min: 0, max: 100000 },
  healthPersons: { type: 'int', min: 1, max: 10 },
  meals: { type: 'money', min: 0, max: 100000 },
  transport: { type: 'money', min: 0, max: 100000 },
  nursery: { type: 'money', min: 0, max: 100000 },
  pensionEmployee: { type: 'money', min: 0, max: 100000 },
  pensionEmployer: { type: 'money', min: 0, max: 100000 },
  hoursPerWeek: { type: 'number', min: 1, max: 80 },
  atRate: { type: 'percent', min: 0, max: 10 },
}

const ENUMS = {
  period: PERIODS, mode: MODES, payments: PAYMENTS, regime: REGIMES, age: AGES,
  contract: CONTRACTS, disability: DISABILITY, joint: JOINT,
  healthMode: FLEX_MODES, mealsMode: FLEX_MODES, transportMode: FLEX_MODES, nurseryMode: FLEX_MODES,
}
const BOOL_KEYS = ['mobility', 'sharedCustody']
const LIST_KEYS = { descDisab: MAX_DESC_DISAB, ascDisab: MAX_ASC_DISAB }

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
  return Math.min(lim.max, Math.max(lim.min, n))
}

function sanitizeList(raw, max) {
  const items = Array.isArray(raw) ? raw : typeof raw === 'string' && raw ? raw.split(',') : []
  return items.filter(v => DISABILITY_LIST.includes(v)).slice(0, max)
}

/**
 * Every field falls back to DEFAULTS on garbage.
 * regions: valid region ids (injected for testability); null accepts any non-empty id.
 */
export function sanitizeState(raw = {}, regions = null) {
  const out = {}
  for (const key of Object.keys(FIELD_LIMITS)) out[key] = clampField(key, raw[key])
  for (const [key, values] of Object.entries(ENUMS)) out[key] = values.includes(raw[key]) ? raw[key] : DEFAULTS[key]
  for (const key of BOOL_KEYS) out[key] = toBool(raw[key])
  for (const [key, max] of Object.entries(LIST_KEYS)) out[key] = sanitizeList(raw[key], max)
  const valid = regions ? new Set(regions) : null
  out.region = valid ? (valid.has(raw.region) ? raw.region : DEFAULTS.region) : (raw.region || DEFAULTS.region)
  // Single-parent joint taxation (familia monoparental) requires a child.
  if (out.joint === 'single' && out.kids + out.kidsU3 === 0) out.joint = 'none'
  return out
}

/** Parse shareable-URL state. Returns null when no ns_ params are present. */
export function parseStateFromParams(search, regions = null) {
  const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search)
  if (!Object.values(QUERY_KEYS).some(k => params.has(k))) return null
  const raw = {}
  for (const [field, key] of Object.entries(QUERY_KEYS)) {
    if (params.has(key)) raw[field] = params.get(key)
  }
  return sanitizeState(raw, regions)
}

const encode = v => (typeof v === 'boolean' ? (v ? '1' : '0') : Array.isArray(v) ? v.join(',') : String(v))

/** URL params for a state: always the amount, plus every value that differs from DEFAULTS. */
export function stateToParams(state) {
  const out = []
  for (const [field, key] of Object.entries(QUERY_KEYS)) {
    const v = encode(state[field])
    if (field === 'amount' || v !== encode(DEFAULTS[field])) out.push([key, v])
  }
  return out
}
