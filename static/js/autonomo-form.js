// Pure state validation for the Spanified autónomo calculator.
// No DOM access here — unit-tested with node:test, reused by autonomo.js.

export const CURRENT_YEAR = 2026
export const YEARS = [CURRENT_YEAR]
export const VALID_TYPES = ['individual', 'director']
export const VALID_TIMES = ['new', 'mid', 'established']
export const VALID_DISABILITY = [0, 33, 65]

export const DEFAULTS = {
  annualNetRevenue: 30000,
  autonomoType: 'individual',
  timeAsAutonomo: 'established',
  region: 'madrid',
  year: 2026,
  age: 35,
  numChildren: 0,
  childrenUnder3: 0,
  disabilityLevel: 0,
  numParents65: 0,
  numParents75: 0,
  reducedMobility: false,
}

export const QUERY_KEYS = {
  annualNetRevenue: 'aut_r',
  year: 'aut_y',
  autonomoType: 'aut_t',
  timeAsAutonomo: 'aut_d',
  region: 'aut_reg',
  age: 'aut_age',
  numChildren: 'aut_ch',
  childrenUnder3: 'aut_chu3',
  disabilityLevel: 'aut_dis',
  numParents65: 'aut_par65',
  numParents75: 'aut_par75',
  reducedMobility: 'aut_mob',
}

function safeInt(raw, fallback, min, max) {
  const n = Math.trunc(Number(raw))
  if (!Number.isFinite(n)) return fallback
  if (max !== undefined) return Math.max(min, Math.min(max, n))
  return Math.max(min, n)
}

/**
 * Totally ordered sanitizer: every field falls back to DEFAULTS on garbage.
 * regions must be a Set/Array of valid region ids (injected for testability).
 */
export function sanitizeState(raw = {}, regions = null) {
  const numChildren = safeInt(raw.numChildren, DEFAULTS.numChildren, 0, 10)
  const numParents65 = safeInt(raw.numParents65, DEFAULTS.numParents65, 0, 4)
  const validRegions = regions ? new Set(regions) : null
  return {
    annualNetRevenue: safeInt(raw.annualNetRevenue, DEFAULTS.annualNetRevenue, 0),
    year: YEARS.includes(Number(raw.year)) ? Number(raw.year) : DEFAULTS.year,
    autonomoType: VALID_TYPES.includes(raw.autonomoType) ? raw.autonomoType : DEFAULTS.autonomoType,
    timeAsAutonomo: VALID_TIMES.includes(raw.timeAsAutonomo) ? raw.timeAsAutonomo : DEFAULTS.timeAsAutonomo,
    region: validRegions && validRegions.has(raw.region) ? raw.region : (validRegions ? DEFAULTS.region : (raw.region || DEFAULTS.region)),
    age: safeInt(raw.age, DEFAULTS.age, 18, 100),
    numChildren,
    childrenUnder3: Math.min(safeInt(raw.childrenUnder3, DEFAULTS.childrenUnder3, 0, 10), numChildren),
    disabilityLevel: VALID_DISABILITY.includes(Number(raw.disabilityLevel)) ? Number(raw.disabilityLevel) : DEFAULTS.disabilityLevel,
    numParents65,
    numParents75: Math.min(safeInt(raw.numParents75, DEFAULTS.numParents75, 0, 4), numParents65),
    reducedMobility: raw.reducedMobility === true || raw.reducedMobility === 1 || raw.reducedMobility === '1' || raw.reducedMobility === 'true',
  }
}

/**
 * Parse shareable-URL state. Returns null when no known params are present.
 * regions: valid region ids for whitelist checking.
 */
export function parseStateFromParams(search, regions = null) {
  const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search)
  const hasAny = Object.values(QUERY_KEYS).some(k => params.has(k))
  if (!hasAny) return null
  const get = k => {
    const v = params.get(QUERY_KEYS[k])
    return v == null ? undefined : v
  }
  return sanitizeState({
    annualNetRevenue: get('annualNetRevenue'),
    year: get('year'),
    autonomoType: get('autonomoType'),
    timeAsAutonomo: get('timeAsAutonomo'),
    region: get('region'),
    age: get('age'),
    numChildren: get('numChildren'),
    childrenUnder3: get('childrenUnder3'),
    disabilityLevel: get('disabilityLevel'),
    numParents65: get('numParents65'),
    numParents75: get('numParents75'),
    reducedMobility: get('reducedMobility'),
  }, regions)
}
