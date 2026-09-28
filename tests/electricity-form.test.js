import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import {
  sanitizeState,
  sanitizeProvider,
  parseStateFromParams,
  encodeProviders,
  decodeProviders,
  DEFAULTS,
  DEFAULT_CONSUMPTION,
  DEFAULT_PROVIDERS,
  EMPTY_PROVIDER,
  MAX_PROVIDERS,
  QUERY_KEYS,
} from '../static/js/electricity-form.js'

// ── defaults ────────────────────────────────────────────────────────────────
describe('defaults', () => {
  it('consumption defaults: 30 days, 5.7 kW, 300 kWh flat, 75/150/75 periods', () => {
    assert.deepEqual(DEFAULT_CONSUMPTION, {
      days: 30,
      contractedKw: 5.7,
      kwhFlat: 300,
      kwhPunta: 75,
      kwhLlano: 150,
      kwhValle: 75,
    })
  })

  it('ships 3 market suppliers: naturgy, octopus, iberdrola', () => {
    assert.deepEqual(DEFAULT_PROVIDERS.map(p => p.id), ['naturgy', 'octopus', 'iberdrola'])
    assert.deepEqual(DEFAULT_PROVIDERS.map(p => p.name), ['Naturgy', 'Octopus Energy', 'Iberdrola'])
    for (const p of DEFAULT_PROVIDERS) {
      assert.equal(p.energyType, 'flat')
      assert.ok(p.energiaFlat > 0)
      assert.ok(p.potenciaP1 > 0)
      assert.ok(p.potenciaP2 > 0)
      assert.equal(p.bonoSocialDaily, 0)
      assert.equal(p.alquilerContadorDaily, 0)
    }
  })

  it('EMPTY_PROVIDER is all-zero flat tariff', () => {
    assert.equal(EMPTY_PROVIDER.energyType, 'flat')
    assert.equal(EMPTY_PROVIDER.name, '')
    for (const k of ['potenciaP1', 'potenciaP2', 'energiaFlat', 'energiaPunta', 'energiaLlano', 'energiaValle', 'bonoSocialDaily', 'alquilerContadorDaily']) {
      assert.equal(EMPTY_PROVIDER[k], 0)
    }
  })

  it('MAX_PROVIDERS is 5', () => {
    assert.equal(MAX_PROVIDERS, 5)
  })

  it('QUERY_KEYS cover consumption + encoded provider list', () => {
    assert.deepEqual(Object.keys(QUERY_KEYS), [
      'days', 'contractedKw', 'kwhFlat', 'kwhPunta', 'kwhLlano', 'kwhValle', 'providers',
    ])
  })

  it('DEFAULTS is {consumption, providers}', () => {
    assert.deepEqual(DEFAULTS.consumption, DEFAULT_CONSUMPTION)
    assert.deepEqual(DEFAULTS.providers, DEFAULT_PROVIDERS)
  })
})

// ── sanitizeState: consumption ──────────────────────────────────────────────
describe('sanitizeState — consumption', () => {
  it('returns defaults for empty input', () => {
    const s = sanitizeState({})
    assert.deepEqual(s.consumption, DEFAULT_CONSUMPTION)
    assert.deepEqual(s.providers, DEFAULT_PROVIDERS)
    // clones, not shared references
    assert.notEqual(s.consumption, DEFAULT_CONSUMPTION)
    assert.notEqual(s.providers[0], DEFAULT_PROVIDERS[0])
  })

  it('keeps valid values', () => {
    const s = sanitizeState({ consumption: { days: 45, contractedKw: 4.4, kwhFlat: 520, kwhPunta: 100, kwhLlano: 200, kwhValle: 100 } })
    assert.deepEqual(s.consumption, { days: 45, contractedKw: 4.4, kwhFlat: 520, kwhPunta: 100, kwhLlano: 200, kwhValle: 100 })
  })

  it('falls back to defaults on garbage', () => {
    const s = sanitizeState({ consumption: { days: 'abc', contractedKw: 'x', kwhFlat: {}, kwhPunta: null, kwhLlano: undefined, kwhValle: '' } })
    assert.deepEqual(s.consumption, DEFAULT_CONSUMPTION)
  })

  it('clamps days to 1..366 and truncates fractions', () => {
    assert.equal(sanitizeState({ consumption: { days: -5 } }).consumption.days, 1)
    assert.equal(sanitizeState({ consumption: { days: 500 } }).consumption.days, 366)
    assert.equal(sanitizeState({ consumption: { days: 30.9 } }).consumption.days, 30)
    assert.equal(sanitizeState({ consumption: { days: 0 } }).consumption.days, 1)
  })

  it('clamps negatives to 0 for kW and kWh', () => {
    const s = sanitizeState({ consumption: { contractedKw: -3, kwhFlat: -100, kwhPunta: -1, kwhLlano: -1, kwhValle: -1 } })
    assert.equal(s.consumption.contractedKw, 0)
    assert.equal(s.consumption.kwhFlat, 0)
    assert.equal(s.consumption.kwhPunta, 0)
    assert.equal(s.consumption.kwhLlano, 0)
    assert.equal(s.consumption.kwhValle, 0)
  })

  it('caps absurd values (kW ≤ 100, kWh ≤ 1,000,000)', () => {
    const s = sanitizeState({ consumption: { contractedKw: 1e9, kwhFlat: 1e12 } })
    assert.equal(s.consumption.contractedKw, 100)
    assert.equal(s.consumption.kwhFlat, 1000000)
  })

  it('parses numeric strings', () => {
    assert.equal(sanitizeState({ consumption: { days: '60', contractedKw: '3.45', kwhFlat: '250' } }).consumption.contractedKw, 3.45)
  })
})

// ── sanitizeState: providers ────────────────────────────────────────────────
describe('sanitizeState — providers', () => {
  it('falls back to defaults when list is missing, empty or not an array', () => {
    assert.deepEqual(sanitizeState({ providers: null }).providers, DEFAULT_PROVIDERS)
    assert.deepEqual(sanitizeState({ providers: [] }).providers, DEFAULT_PROVIDERS)
    assert.deepEqual(sanitizeState({ providers: 'nonsense' }).providers, DEFAULT_PROVIDERS)
  })

  it('keeps at most 5 providers', () => {
    const many = Array.from({ length: 9 }, (_, i) => ({ ...EMPTY_PROVIDER, id: `x${i}` }))
    const s = sanitizeState({ providers: many })
    assert.equal(s.providers.length, MAX_PROVIDERS)
  })

  it('accepts a single provider', () => {
    const s = sanitizeState({ providers: [{ ...DEFAULT_PROVIDERS[0] }] })
    assert.equal(s.providers.length, 1)
    assert.equal(s.providers[0].id, 'naturgy')
  })

  it('always yields at least one provider', () => {
    assert.equal(sanitizeState({ providers: ['junk', null] }).providers.length, 2)
  })

  it('invalid energyType falls back to flat', () => {
    const s = sanitizeState({ providers: [{ ...EMPTY_PROVIDER, energyType: 'hourly' }] })
    assert.equal(s.providers[0].energyType, 'flat')
    assert.equal(sanitizeState({ providers: [{ ...EMPTY_PROVIDER, energyType: 'punta_llano_valle' }] }).providers[0].energyType, 'punta_llano_valle')
  })

  it('clamps negative rates to 0', () => {
    const s = sanitizeState({ providers: [{ ...EMPTY_PROVIDER, potenciaP1: -1, energiaFlat: -0.5, bonoSocialDaily: -3 }] })
    assert.equal(s.providers[0].potenciaP1, 0)
    assert.equal(s.providers[0].energiaFlat, 0)
    assert.equal(s.providers[0].bonoSocialDaily, 0)
  })

  it('keeps valid rates and names', () => {
    const s = sanitizeState({ providers: [{ ...DEFAULT_PROVIDERS[1] }] })
    assert.equal(s.providers[0].name, 'Octopus Energy')
    assert.equal(s.providers[0].potenciaP1, 0.097)
    assert.equal(s.providers[0].energiaFlat, 0.119)
  })

  it('strips URL separators and caps length in names', () => {
    const p = sanitizeProvider({ name: 'A|B;C' + 'x'.repeat(80) })
    assert.ok(!p.name.includes('|') && !p.name.includes(';'))
    assert.equal(p.name.length, 40)
    assert.equal(sanitizeProvider({ name: 12345 }).name, '')
  })

  it('repairs invalid ids with a positional fallback', () => {
    assert.equal(sanitizeProvider({ id: 'ok-id_1' }).id, 'ok-id_1')
    assert.equal(sanitizeProvider({ id: 'bad id with spaces' }, 'p2').id, 'p2')
    assert.equal(sanitizeProvider({}, 'p3').id, 'p3')
    assert.equal(sanitizeProvider({ id: '' }, 'p4').id, 'p4')
  })

  it('garbage provider entries become empty providers with fallback ids', () => {
    const s = sanitizeState({ providers: ['nope', 42, null] })
    assert.equal(s.providers.length, 3)
    assert.equal(s.providers[0].id, 'p1')
    assert.equal(s.providers[1].id, 'p2')
    assert.equal(s.providers[2].id, 'p3')
    assert.equal(s.providers[0].potenciaP1, 0)
    assert.equal(s.providers[0].energyType, 'flat')
  })
})

// ── provider URL encoding ───────────────────────────────────────────────────
describe('encodeProviders / decodeProviders', () => {
  it('round-trips the default supplier list', () => {
    const encoded = encodeProviders(DEFAULT_PROVIDERS)
    const decoded = sanitizeState({ providers: decodeProviders(encoded) }).providers
    assert.deepEqual(decoded, DEFAULT_PROVIDERS)
  })

  it('round-trips a custom single provider', () => {
    const custom = [{ ...EMPTY_PROVIDER, id: 'custom1', name: 'Endesa', potenciaP1: 0.1045, potenciaP2: 0.045, energyType: 'punta_llano_valle', energiaPunta: 0.16, energiaLlano: 0.12, energiaValle: 0.07, bonoSocialDaily: 0.02 }]
    const decoded = sanitizeState({ providers: decodeProviders(encodeProviders(custom)) }).providers
    assert.deepEqual(decoded, custom)
  })

  it('strips structural separators from names', () => {
    const encoded = encodeProviders([{ ...EMPTY_PROVIDER, id: 'x', name: 'A|B;C' }])
    assert.equal(encoded.split(';').length, 1)
    assert.ok(!encoded.split('|')[1].includes('|'))
  })

  it('encodes empty list to empty string and decodes back to []', () => {
    assert.equal(encodeProviders([]), '')
    assert.equal(encodeProviders(null), '')
    assert.deepEqual(decodeProviders(''), [])
    assert.deepEqual(decodeProviders(undefined), [])
    assert.deepEqual(decodeProviders(';;;'), [])
  })

  it('tolerates short/malformed entries', () => {
    const decoded = sanitizeState({ providers: decodeProviders('onlyid|OnlyName') }).providers
    assert.equal(decoded.length, 1)
    assert.equal(decoded[0].id, 'onlyid')
    assert.equal(decoded[0].name, 'OnlyName')
    assert.equal(decoded[0].potenciaP1, 0)
    assert.equal(decoded[0].energyType, 'flat')
  })
})

// ── parseStateFromParams ────────────────────────────────────────────────────
describe('parseStateFromParams', () => {
  it('returns null when no known params are present', () => {
    assert.equal(parseStateFromParams(''), null)
    assert.equal(parseStateFromParams('?foo=1'), null)
    assert.equal(parseStateFromParams('?el_x=3'), null)
  })

  it('parses consumption params', () => {
    const s = parseStateFromParams('?el_d=45&el_kw=4.4&el_f=520&el_p=100&el_l=250&el_v=170')
    assert.deepEqual(s.consumption, { days: 45, contractedKw: 4.4, kwhFlat: 520, kwhPunta: 100, kwhLlano: 250, kwhValle: 170 })
    assert.deepEqual(s.providers, DEFAULT_PROVIDERS)
  })

  it('parses the encoded provider list', () => {
    const pr = encodeURIComponent(encodeProviders(DEFAULT_PROVIDERS))
    const s = parseStateFromParams(`?el_pr=${pr}`)
    assert.deepEqual(s.providers, DEFAULT_PROVIDERS)
    assert.deepEqual(s.consumption, DEFAULT_CONSUMPTION)
  })

  it('round-trips a full state through the URL', () => {
    const original = sanitizeState({
      consumption: { days: 60, contractedKw: 3.45, kwhFlat: 410, kwhPunta: 60, kwhLlano: 250, kwhValle: 100 },
      providers: [{ ...EMPTY_PROVIDER, id: 'end', name: 'Endesa', potenciaP1: 0.1045, potenciaP2: 0.045, energyType: 'punta_llano_valle', energiaPunta: 0.16, energiaLlano: 0.12, energiaValle: 0.07 }],
    })
    const params = new URLSearchParams()
    for (const [key, param] of Object.entries(QUERY_KEYS)) {
      params.set(param, key === 'providers' ? encodeProviders(original.providers) : String(original.consumption[key]))
    }
    const parsed = parseStateFromParams(`?${params.toString()}`)
    assert.deepEqual(parsed, original)
  })

  it('sanitizes hostile query values', () => {
    const s = parseStateFromParams('?el_d=-40&el_kw=abc&el_f=%3Cscript%3E&el_pr=bogus')
    assert.equal(s.consumption.days, 1)
    assert.equal(s.consumption.contractedKw, DEFAULT_CONSUMPTION.contractedKw)
    assert.equal(s.consumption.kwhFlat, DEFAULT_CONSUMPTION.kwhFlat)
    assert.equal(s.providers.length, 1)
    assert.equal(s.providers[0].id, 'bogus')
  })

  it('accepts a query string with or without a leading ?', () => {
    const a = parseStateFromParams('el_d=10')
    const b = parseStateFromParams('?el_d=10')
    assert.deepEqual(a, b)
    assert.equal(a.consumption.days, 10)
  })
})
