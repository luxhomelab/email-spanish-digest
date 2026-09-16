/**
 * Spain property buying cost calculator (ITP / IVA+AJD / IGIC+AJD + fees).
 *
 * ES-module port of dsinvestments/app/src/property-buying-cost/calculation.js
 * + app/src/data/itp.js. Logic is IDENTICAL to the source; regional rates are
 * copied verbatim from app/src/data/spain-tax-data.json (iva_rate=10).
 *
 * Notes vs source UI strings (kept as-is, flagged for review):
 * - pbc_faq_regions_text claims Basque Country ITP 4%, but the data table used
 *   by the engine says itp_standard 7.0 (4% only for residential property per
 *   the region notes). The engine follows the data table.
 * - Comunidad Valenciana uses date-conditional brackets: 10% before 2026-07-01,
 *   9% (≤€1M) / 11% (>€1M) from 2026-07-01, evaluated against `new Date()` at
 *   runtime — same as source.
 */

export const MIN_PRICE = 10000

const IVA_RATE = 10.0

const REGIONS = [
  { id: 'andalucia', itp_standard: 7.0, ajd_standard: 1.2, igic_rate: null },
  { id: 'aragon', itp_standard: 8.0, itp_brackets: [
    { upTo: 400000, rate: 8.0 }, { upTo: 450000, rate: 8.5 },
    { upTo: 500000, rate: 9.0 }, { upTo: 750000, rate: 9.5 },
    { upTo: null, rate: 10.0 },
  ], ajd_standard: 1.5, igic_rate: null },
  { id: 'asturias', itp_standard: 8.0, itp_brackets: [
    { upTo: 300000, rate: 8.0 }, { upTo: 500000, rate: 9.0 },
    { upTo: null, rate: 10.0 },
  ], ajd_standard: 1.2, igic_rate: null },
  { id: 'baleares', itp_standard: 8.0, itp_brackets: [
    { upTo: 400000, rate: 8.0 }, { upTo: 600000, rate: 9.0 },
    { upTo: 1000000, rate: 10.0 }, { upTo: 3000000, rate: 12.0 },
    { upTo: null, rate: 13.0 },
  ], ajd_standard: 1.5, igic_rate: null },
  { id: 'canarias', itp_standard: 6.5, ajd_standard: 0.75, igic_rate: 7.0 },
  { id: 'cantabria', itp_standard: 9.0, ajd_standard: 1.5, igic_rate: null },
  { id: 'castilla_la_mancha', itp_standard: 9.0, ajd_standard: 1.5, igic_rate: null },
  { id: 'castilla_leon', itp_standard: 8.0, itp_brackets: [
    { upTo: 250000, rate: 8.0 }, { upTo: null, rate: 10.0 },
  ], ajd_standard: 1.5, igic_rate: null },
  { id: 'catalunya', itp_standard: 10.0, itp_brackets: [
    { upTo: 600000, rate: 10.0 }, { upTo: 900000, rate: 11.0 },
    { upTo: 1500000, rate: 12.0 }, { upTo: null, rate: 13.0 },
  ], ajd_standard: 1.5, igic_rate: null },
  { id: 'comunidad_valenciana', itp_standard: 10.0, itp_brackets: [
    { upTo: 1000000, rate: 10.0 }, { upTo: null, rate: 11.0 },
  ], itp_brackets_transition: { effective_from: '2026-07-01', brackets: [
    { upTo: 1000000, rate: 9.0 }, { upTo: null, rate: 11.0 },
  ]}, ajd_standard: 1.5, igic_rate: null },
  { id: 'ceuta', itp_standard: 6.0, ajd_standard: 0.5, igic_rate: null },
  { id: 'extremadura', itp_standard: 8.0, itp_brackets: [
    { upTo: 360000, rate: 8.0 }, { upTo: 600000, rate: 10.0 },
    { upTo: null, rate: 11.0 },
  ], ajd_standard: 1.5, igic_rate: null },
  { id: 'galicia', itp_standard: 8.0, ajd_standard: 1.5, igic_rate: null },
  { id: 'madrid', itp_standard: 6.0, ajd_standard: 0.75, igic_rate: null },
  { id: 'melilla', itp_standard: 6.0, ajd_standard: 0.5, igic_rate: null },
  { id: 'murcia', itp_standard: 8.0, ajd_standard: 1.5, igic_rate: null },
  { id: 'navarra', itp_standard: 6.0, ajd_standard: 0.5, igic_rate: null },
  { id: 'pais_vasco', itp_standard: 7.0, itp_brackets: [
    { upTo: null, rate: 7.0 },
  ], ajd_standard: 0.0, igic_rate: null },
  { id: 'la_rioja', itp_standard: 7.0, ajd_standard: 1.0, igic_rate: null },
]

/**
 * Calculate ITP (property transfer tax) for a resale property.
 * Uses marginal progressive brackets if the region defines them,
 * otherwise falls back to itp_standard flat rate.
 */
export function calculateItpAmount(price, region) {
  if (region == null || !price || price <= 0) return 0

  let brackets = region.itp_brackets
  if (!brackets || brackets.length === 0) return price * (region.itp_standard || 0) / 100

  // Date-conditional transition (e.g. Comunidad Valenciana from 2026-07-01)
  if (region.itp_brackets_transition) {
    const transitionDate = new Date(region.itp_brackets_transition.effective_from)
    const transitionBrackets = region.itp_brackets_transition.brackets
    if (
      !isNaN(transitionDate.getTime()) &&
      new Date() >= transitionDate &&
      Array.isArray(transitionBrackets) &&
      transitionBrackets.length > 0
    ) {
      brackets = transitionBrackets
    }
  }

  // Marginal calculation: each price tranche taxed at its bracket rate
  let total = 0
  let prev = 0
  for (const bracket of brackets) {
    const limit = bracket.upTo ?? Infinity
    const portion = Math.min(price - prev, limit - prev)
    if (portion <= 0) break
    total += portion * bracket.rate / 100
    prev = limit
    if (prev >= price) break
  }
  return Math.round(total * 100) / 100
}

export function estimateNotaryFee(price) {
  if (price == null || price < 0) return 0
  if (price < 100000) return 700
  if (price < 200000) return 850
  if (price < 400000) return 1050
  if (price < 700000) return 1150
  return 1200
}

export function estimateRegistryFee(price) {
  if (price == null || price < 0) return 0
  if (price < 100000) return 450
  if (price < 200000) return 550
  if (price < 400000) return 700
  if (price < 700000) return 850
  return 1000
}

export function calculateBuyingCost({ price, isNewBuild, regionId }) {
  const region = REGIONS.find(r => r.id === regionId)
  const ivaRate = IVA_RATE
  if (ivaRate == null) {
    console.error('calculateBuyingCost: IVA rate is missing')
    return null
  }
  if (!region || !price || price < MIN_PRICE) return null

  let taxType, primaryTaxRate, primaryTaxAmount, ajdRate = null, ajdAmount = null

  if (isNewBuild) {
    const usesIgic = region.igic_rate != null
    primaryTaxRate = usesIgic ? region.igic_rate : ivaRate
    taxType = usesIgic ? 'IGIC+AJD' : 'IVA+AJD'
    primaryTaxAmount = price * primaryTaxRate / 100
    ajdRate = region.ajd_standard
    ajdAmount = price * ajdRate / 100
  } else {
    taxType = 'ITP'
    primaryTaxAmount = calculateItpAmount(price, region)
    primaryTaxRate = (primaryTaxAmount / price) * 100
  }

  const totalTax = primaryTaxAmount + (ajdAmount || 0)
  const notaryFee = estimateNotaryFee(price)
  const registryFee = estimateRegistryFee(price)
  const totalCosts = totalTax + notaryFee + registryFee
  const totalPct = (totalCosts / price) * 100

  const breakdown = []
  if (taxType === 'ITP') {
    breakdown.push({ key: 'itp', rate: primaryTaxRate, amount: primaryTaxAmount })
  } else if (taxType === 'IVA+AJD') {
    breakdown.push({ key: 'iva', rate: primaryTaxRate, amount: primaryTaxAmount })
    if (ajdAmount > 0) breakdown.push({ key: 'ajd', rate: ajdRate, amount: ajdAmount })
  } else {
    breakdown.push({ key: 'igic', rate: primaryTaxRate, amount: primaryTaxAmount })
    if (ajdAmount > 0) breakdown.push({ key: 'ajd', rate: ajdRate, amount: ajdAmount })
  }
  breakdown.push({ key: 'notary', rate: null, amount: notaryFee })
  breakdown.push({ key: 'registry', rate: null, amount: registryFee })

  return { taxType, primaryTaxRate, primaryTaxAmount, ajdRate, ajdAmount, totalTax, notaryFee, registryFee, totalCosts, totalPct, breakdown }
}
