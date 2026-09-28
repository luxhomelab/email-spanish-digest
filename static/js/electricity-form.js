// Pure state defaults/validation for the Spanified electricity bill calculator.
// No DOM access here — unit-tested with node:test, reused by electricity.js.
//
// Tariff data (defaults) ported from the dsinvestments electricity calculator:
// real market data from the Spanish energy market (2025-2026).

export const MAX_PROVIDERS = 5

export const DEFAULT_CONSUMPTION = {
  days: 30,
  contractedKw: 5.7,
  // For flat tariff
  kwhFlat: 300,
  // For punta/llano/valle tariff (roughly 25/50/25 split)
  kwhPunta: 75,
  kwhLlano: 150,
  kwhValle: 75,
}

export const DEFAULT_PROVIDERS = [
  {
    id: 'naturgy',
    name: 'Naturgy',
    potenciaP1: 0.11362,
    potenciaP2: 0.040193,
    energyType: 'flat',
    energiaFlat: 0.108,
    energiaPunta: 0.14,
    energiaLlano: 0.11,
    energiaValle: 0.07,
    bonoSocialDaily: 0,
    alquilerContadorDaily: 0,
  },
  {
    id: 'octopus',
    name: 'Octopus Energy',
    potenciaP1: 0.097,
    potenciaP2: 0.027,
    energyType: 'flat',
    energiaFlat: 0.119,
    energiaPunta: 0.18,
    energiaLlano: 0.12,
    energiaValle: 0.065,
    bonoSocialDaily: 0,
    alquilerContadorDaily: 0,
  },
  {
    id: 'iberdrola',
    name: 'Iberdrola',
    potenciaP1: 0.1148,
    potenciaP2: 0.0378,
    energyType: 'flat',
    energiaFlat: 0.149,
    energiaPunta: 0.185,
    energiaLlano: 0.135,
    energiaValle: 0.072,
    bonoSocialDaily: 0,
    alquilerContadorDaily: 0,
  },
]

export const EMPTY_PROVIDER = {
  id: '',
  name: '',
  potenciaP1: 0,
  potenciaP2: 0,
  energyType: 'flat',
  energiaFlat: 0,
  energiaPunta: 0,
  energiaLlano: 0,
  energiaValle: 0,
  bonoSocialDaily: 0,
  alquilerContadorDaily: 0,
}

export const VALID_ENERGY_TYPES = ['flat', 'punta_llano_valle']

export const DEFAULTS = {
  consumption: { ...DEFAULT_CONSUMPTION },
  providers: DEFAULT_PROVIDERS.map((p) => ({ ...p })),
}

// Shareable-URL keys. Consumption uses one key per number; the provider list is
// encoded into a single param (`el_pr`) as id|name|… fields joined by `;`.
export const QUERY_KEYS = {
  days: 'el_d',
  contractedKw: 'el_kw',
  kwhFlat: 'el_f',
  kwhPunta: 'el_p',
  kwhLlano: 'el_l',
  kwhValle: 'el_v',
  providers: 'el_pr',
}

const PROVIDER_FIELDS = [
  'id', 'name', 'potenciaP1', 'potenciaP2', 'energyType',
  'energiaFlat', 'energiaPunta', 'energiaLlano', 'energiaValle',
  'bonoSocialDaily', 'alquilerContadorDaily',
]

function safeNum(raw, fallback, min, max) {
  if (raw === undefined || raw === null || raw === '') return fallback
  const n = Number(raw)
  if (!Number.isFinite(n)) return fallback
  if (max !== undefined) return Math.max(min, Math.min(max, n))
  return Math.max(min, n)
}

function safeInt(raw, fallback, min, max) {
  if (raw === undefined || raw === null || raw === '') return fallback
  const n = Math.trunc(Number(raw))
  if (!Number.isFinite(n)) return fallback
  if (max !== undefined) return Math.max(min, Math.min(max, n))
  return Math.max(min, n)
}

/**
 * Sanitize a single provider. Every field falls back to a safe value;
 * numbers are clamped to realistic tariff ranges.
 */
export function sanitizeProvider(raw = {}, fallbackId = '') {
  const id = typeof raw.id === 'string' && /^[A-Za-z0-9_-]{1,24}$/.test(raw.id)
    ? raw.id
    : fallbackId
  const name = typeof raw.name === 'string'
    ? raw.name.replace(/[|;]/g, ' ').slice(0, 40)
    : ''
  return {
    id,
    name,
    potenciaP1: safeNum(raw.potenciaP1, 0, 0, 10),
    potenciaP2: safeNum(raw.potenciaP2, 0, 0, 10),
    energyType: VALID_ENERGY_TYPES.includes(raw.energyType) ? raw.energyType : 'flat',
    energiaFlat: safeNum(raw.energiaFlat, 0, 0, 100),
    energiaPunta: safeNum(raw.energiaPunta, 0, 0, 100),
    energiaLlano: safeNum(raw.energiaLlano, 0, 0, 100),
    energiaValle: safeNum(raw.energiaValle, 0, 0, 100),
    bonoSocialDaily: safeNum(raw.bonoSocialDaily, 0, 0, 10),
    alquilerContadorDaily: safeNum(raw.alquilerContadorDaily, 0, 0, 10),
  }
}

/**
 * Totally ordered sanitizer: every field falls back to DEFAULTS on garbage.
 * State shape: { consumption: {...}, providers: [...] }.
 */
export function sanitizeState(raw = {}) {
  const rawConsumption = (raw && typeof raw.consumption === 'object' && raw.consumption) || {}
  const consumption = {
    days: safeInt(rawConsumption.days, DEFAULT_CONSUMPTION.days, 1, 366),
    contractedKw: safeNum(rawConsumption.contractedKw, DEFAULT_CONSUMPTION.contractedKw, 0, 100),
    kwhFlat: safeNum(rawConsumption.kwhFlat, DEFAULT_CONSUMPTION.kwhFlat, 0, 1000000),
    kwhPunta: safeNum(rawConsumption.kwhPunta, DEFAULT_CONSUMPTION.kwhPunta, 0, 1000000),
    kwhLlano: safeNum(rawConsumption.kwhLlano, DEFAULT_CONSUMPTION.kwhLlano, 0, 1000000),
    kwhValle: safeNum(rawConsumption.kwhValle, DEFAULT_CONSUMPTION.kwhValle, 0, 1000000),
  }

  let providers
  if (Array.isArray(raw.providers) && raw.providers.length > 0) {
    providers = raw.providers
      .slice(0, MAX_PROVIDERS)
      .map((p, i) => sanitizeProvider(p && typeof p === 'object' ? p : {}, `p${i + 1}`))
  } else {
    providers = DEFAULT_PROVIDERS.map((p) => ({ ...p }))
  }

  return { consumption, providers }
}

/**
 * Encode the provider list for the shareable URL:
 * each provider = fields joined by ``, providers joined by `;`.
 */
export function encodeProviders(providers) {
  if (!Array.isArray(providers) || providers.length === 0) return ''
  return providers
    .map((p) =>
      PROVIDER_FIELDS.map((f) => {
        let v = p && p[f] !== undefined && p[f] !== null ? p[f] : ''
        if (f === 'name') v = String(v).replace(/[|;]/g, ' ')
        if (f === 'id') v = String(v).replace(/[^A-Za-z0-9_-]/g, '')
        if (typeof v === 'number') v = String(Math.round(v * 1e6) / 1e6)
        return String(v)
      }).join('|')
    )
    .join(';')
}

/**
 * Decode the provider list from a shareable-URL param into raw objects
 * (strings). Sanitization happens later in sanitizeState.
 */
export function decodeProviders(str) {
  if (typeof str !== 'string' || str === '') return []
  return str
    .split(';')
    .filter((entry) => entry !== '')
    .map((entry) => {
      const parts = entry.split('|')
      const raw = {}
      PROVIDER_FIELDS.forEach((f, i) => {
        if (parts[i] !== undefined) raw[f] = parts[i]
      })
      return raw
    })
}

/**
 * Parse shareable-URL state. Returns null when no known params are present.
 */
export function parseStateFromParams(search) {
  const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search)
  const hasAny = Object.values(QUERY_KEYS).some((k) => params.has(k))
  if (!hasAny) return null
  const get = (k) => {
    const v = params.get(QUERY_KEYS[k])
    return v == null ? undefined : v
  }
  return sanitizeState({
    consumption: {
      days: get('days'),
      contractedKw: get('contractedKw'),
      kwhFlat: get('kwhFlat'),
      kwhPunta: get('kwhPunta'),
      kwhLlano: get('kwhLlano'),
      kwhValle: get('kwhValle'),
    },
    providers: params.has(QUERY_KEYS.providers) ? decodeProviders(get('providers')) : undefined,
  })
}
