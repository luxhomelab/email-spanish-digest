// Pure state validation for the Spanified property buying cost calculator.
// No DOM access here — unit-tested with node:test, reused by property-buying-cost.js.

export const MIN_PRICE = 10000

export const DEFAULTS = {
  price: 200000,
  isNewBuild: false,
  regionId: 'madrid',
}

export const QUERY_KEYS = {
  price: 'pbc_p',
  isNewBuild: 'pbc_nb',
  regionId: 'pbc_r',
}

function safeInt(raw, fallback, min) {
  const n = Math.trunc(Number(raw))
  if (!Number.isFinite(n)) return fallback
  return Math.max(min, n)
}

/**
 * Totally ordered sanitizer: every field falls back to DEFAULTS on garbage.
 * regions must be a Set/Array of valid region ids (injected for testability).
 */
export function sanitizeState(raw = {}, regions = null) {
  const validRegions = regions ? new Set(regions) : null
  return {
    price: safeInt(raw.price, DEFAULTS.price, 0),
    isNewBuild: raw.isNewBuild === true || raw.isNewBuild === 1 || raw.isNewBuild === '1' || raw.isNewBuild === 'true',
    regionId: validRegions && validRegions.has(raw.regionId) ? raw.regionId : (validRegions ? DEFAULTS.regionId : (raw.regionId || DEFAULTS.regionId)),
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
    price: get('price'),
    isNewBuild: get('isNewBuild'),
    regionId: get('regionId'),
  }, regions)
}
