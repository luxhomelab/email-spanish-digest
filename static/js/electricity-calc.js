// Spain electricity bill calculation engine (ported 1:1 from dsinvestments).
// Pure functions only — no DOM access, unit-tested with node:test.
//
// Structure of a Spanish electricity bill:
//   Término de potencia  = (P1_rate + P2_rate) × days × contracted_kW
//   Término de energía   = flat: kWh × price
//                          punta_llano_valle: kWh_p×p_p + kWh_l×p_l + kWh_v×p_v
//   Bono Social          = daily_rate × days
//   ──────────────────────────────────────
//   Subtotal             = potencia + energía + bono_social
//   Impuesto electricidad= subtotal × 5.112696%
//   Alquiler contador    = daily_rate × days
//   ──────────────────────────────────────
//   Total electricidad   = subtotal + impuesto + alquiler
//   IVA                  = total_electricidad × 21%
//   ══════════════════════════════════════
//   TOTAL A PAGAR        = total_electricidad + IVA

export const ELECTRICITY_TAX_RATE = 0.05112696 // Impuesto especial electricidad
export const VAT_RATE = 0.21 // IVA

/**
 * @typedef {Object} ProviderTariff
 * @property {string}  id
 * @property {string}  name
 * @property {number}  potenciaP1       - €/kW/día (punta)
 * @property {number}  potenciaP2       - €/kW/día (valle)
 * @property {'flat'|'punta_llano_valle'} energyType
 * @property {number}  [energiaFlat]    - €/kWh (flat tariff)
 * @property {number}  [energiaPunta]   - €/kWh
 * @property {number}  [energiaLlano]   - €/kWh
 * @property {number}  [energiaValle]   - €/kWh
 * @property {number}  [bonoSocialDaily]        - €/día (advanced)
 * @property {number}  [alquilerContadorDaily]  - €/día (advanced)
 *
 * @typedef {Object} ConsumptionInputs
 * @property {number}  days             - Billing period in days
 * @property {number}  contractedKw     - Contracted power (kW)
 * @property {number}  [kwhFlat]        - Total kWh (used for flat tariff)
 * @property {number}  [kwhPunta]       - kWh in punta period
 * @property {number}  [kwhLlano]       - kWh in llano period
 * @property {number}  [kwhValle]       - kWh in valle period
 */

/**
 * Calculate electricity bill for a single provider.
 * @param {ProviderTariff} provider
 * @param {ConsumptionInputs} inputs
 * @returns {{terminoPotenciaP1:number,terminoPotenciaP2:number,terminoPotencia:number,terminoEnergia:number,bonoSocial:number,subtotal:number,impuestoElectricidad:number,alquilerContador:number,totalElectricidad:number,iva:number,total:number}}
 */
export function calculateBill(provider, inputs) {
  const { days, contractedKw } = inputs

  // Término de potencia
  const terminoPotenciaP1 = (provider.potenciaP1 || 0) * days * contractedKw
  const terminoPotenciaP2 = (provider.potenciaP2 || 0) * days * contractedKw
  const terminoPotencia = terminoPotenciaP1 + terminoPotenciaP2

  // Término de energía
  let terminoEnergia = 0
  if (provider.energyType === 'flat') {
    terminoEnergia = (inputs.kwhFlat || 0) * (provider.energiaFlat || 0)
  } else {
    terminoEnergia =
      (inputs.kwhPunta || 0) * (provider.energiaPunta || 0) +
      (inputs.kwhLlano || 0) * (provider.energiaLlano || 0) +
      (inputs.kwhValle || 0) * (provider.energiaValle || 0)
  }

  // Bono Social
  const bonoSocial = (provider.bonoSocialDaily || 0) * days

  const subtotal = terminoPotencia + terminoEnergia + bonoSocial

  // Impuesto especial sobre electricidad (5.112696%)
  const impuestoElectricidad = subtotal * ELECTRICITY_TAX_RATE

  // Alquiler de contador
  const alquilerContador = (provider.alquilerContadorDaily || 0) * days

  const totalElectricidad = subtotal + impuestoElectricidad + alquilerContador

  // IVA 21%
  const iva = totalElectricidad * VAT_RATE

  const total = totalElectricidad + iva

  return {
    terminoPotenciaP1,
    terminoPotenciaP2,
    terminoPotencia,
    terminoEnergia,
    bonoSocial,
    subtotal,
    impuestoElectricidad,
    alquilerContador,
    totalElectricidad,
    iva,
    total,
  }
}

/**
 * Calculate bills for multiple providers and rank them (cheapest first).
 * @param {ProviderTariff[]} providers
 * @param {ConsumptionInputs} inputs
 * @returns {{provider: ProviderTariff, breakdown: ReturnType<typeof calculateBill>, rank: number}[]}
 */
export function compareProviders(providers, inputs) {
  const results = providers.map((provider) => ({
    provider,
    breakdown: calculateBill(provider, inputs),
  }))

  results.sort((a, b) => a.breakdown.total - b.breakdown.total)

  return results.map((r, i) => ({ ...r, rank: i + 1 }))
}

/**
 * Total kWh for the active tariff (flat total, or sum of periods).
 * @param {ConsumptionInputs} inputs
 * @returns {number}
 */
export function getTotalKwh(inputs) {
  if (inputs.kwhFlat !== undefined) {
    return inputs.kwhFlat || 0
  }
  return (inputs.kwhPunta || 0) + (inputs.kwhLlano || 0) + (inputs.kwhValle || 0)
}
