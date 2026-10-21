/**
 * Spain rental yield calculator (net yield, cash-on-cash, IRR, taxes by tax status).
 *
 * ES-module port of dsinvestments/app/src/calculator/simulation.js with the
 * following deliberate corrections (verified October 2026):
 *
 * - Purchase taxes reuse REGIONS + calculateItpAmount from
 *   property-buying-cost-calc.js (QA 2026-09-16 table) instead of a second JSON copy.
 * - New build = IVA 10% (IGIC 7% in Canarias) PLUS AJD (the source charged IVA only).
 * - Resident: rental-income reduction is user-selectable (art. 23.2 LIRPF after
 *   Ley 12/2023: 50% general, 60%, 70%, 90%; 100% kept for the RDL 29/2026 scale,
 *   BOE-A-2026-20823, in force since 08.10.2026,
 *   pending convalidation). Default 50%.
 * - Non-resident EU/EEA: 19% on income minus expenses, mortgage interest and
 *   amortization (art. 24.6 TRLIRNR). No reduction.
 * - Non-resident non-EU: 24% on gross income (current rule). Optional flag applies
 *   the Audiencia Nacional 28.07.2025 ruling (rec. 636/2021, under appeal): net
 *   base like EU, rate 24%.
 * - Capital gain on sale: residents savings scale 19/21/23/27/30%; non-residents
 *   flat 19% (art. 25.1.f TRLIRNR). The 3% buyer withholding (modelo 211) is an
 *   advance payment and is not modelled.
 * - Amortization: 3%/yr of (price + purchase taxes + closing costs) x construction
 *   share + renovation cost (art. 14 RIRPF, land excluded); cumulative cap = base.
 * - Optional municipal plusvalia added to selling costs.
 * - Adds gross yield = annual rent / purchase price.
 * Mortgage annuity, NOI, vacancy, growth, cash-on-cash, IRR bisection and ROI
 * are unchanged from the source.
 */
import { REGIONS, IVA_RATE, calculateItpAmount } from './property-buying-cost-calc.js'

export const PROJECTION_YEARS = 50
export const AMORTIZATION_RATE = 0.03
export const EU_RATE = 0.19
export const NON_EU_RATE = 0.24
export const NON_RESIDENT_GAIN_RATE = 0.19
export const REDUCTION_OPTIONS = [0, 50, 60, 70, 90, 100]

export function parseNumber(value) {
  if (value === '' || value === null || value === undefined) return 0
  const n = Number(value)
  if (Number.isNaN(n) || !Number.isFinite(n)) return 0
  return n
}

export function buildMortgageSchedule(loanAmount, annualRate, termYears, projectionYears) {
  if (loanAmount <= 0 || annualRate == null || termYears <= 0) {
    return {
      monthlyPayment: 0,
      interestByYear: Array(projectionYears).fill(0),
      principalByYear: Array(projectionYears).fill(0),
      totalPaidByYear: Array(projectionYears).fill(0),
      principalRemainingByYear: Array(projectionYears + 1).fill(0),
    }
  }

  const monthsTotal = termYears * 12
  const monthlyRate = annualRate / 12 / 100

  let monthlyPayment
  if (!monthlyRate) {
    monthlyPayment = loanAmount / monthsTotal
  } else {
    const factor = (1 + monthlyRate) ** monthsTotal
    monthlyPayment = loanAmount * (monthlyRate * factor) / (factor - 1)
  }

  const interestByYear = Array(projectionYears).fill(0)
  const principalByYear = Array(projectionYears).fill(0)
  const totalPaidByYear = Array(projectionYears).fill(0)
  const principalRemainingByYear = Array(projectionYears + 1).fill(0)

  let principal = loanAmount
  principalRemainingByYear[0] = principal

  for (let m = 1; m <= monthsTotal; m += 1) {
    const yearIndex = Math.floor((m - 1) / 12)
    if (yearIndex >= projectionYears) break

    const interest = principal * monthlyRate
    const principalPaid = monthlyPayment - interest
    principal = Math.max(0, principal - principalPaid)

    interestByYear[yearIndex] += interest
    principalByYear[yearIndex] += principalPaid
    totalPaidByYear[yearIndex] += monthlyPayment

    if (m % 12 === 0 || m === monthsTotal) {
      principalRemainingByYear[yearIndex + 1] = principal
    }
  }

  return { monthlyPayment, interestByYear, principalByYear, totalPaidByYear, principalRemainingByYear }
}

/**
 * Capital gains tax on the sale.
 * Residents: 2026 savings scale 19/21/23/27/30% (6k/50k/200k/300k).
 * Non-residents (EU or not): flat 19% (art. 25.1.f TRLIRNR).
 */
export function calculateExitTax(gain, taxStatus = 'resident') {
  if (!(gain > 0)) return 0
  if (taxStatus !== 'resident') return gain * NON_RESIDENT_GAIN_RATE

  let tax
  if (gain <= 6000) {
    tax = gain * 0.19
  } else if (gain <= 50000) {
    tax = (6000 * 0.19) + (gain - 6000) * 0.21
  } else if (gain <= 200000) {
    tax = (6000 * 0.19) + (44000 * 0.21) + (gain - 50000) * 0.23
  } else if (gain <= 300000) {
    tax = (6000 * 0.19) + (44000 * 0.21) + (150000 * 0.23) + (gain - 200000) * 0.27
  } else {
    tax = (6000 * 0.19) + (44000 * 0.21) + (150000 * 0.23) + (100000 * 0.27) + (gain - 300000) * 0.30
  }
  return tax
}

/** IRR by bisection on annual cash flows. Returns percent. */
export function calculateIrrFromCashflows(cashflows) {
  if (!cashflows || cashflows.length < 2) return 0
  if (cashflows.every(cf => cf === 0)) return 0

  const npv = (rate) => cashflows.reduce((acc, cf, i) => acc + (cf / ((1 + rate) ** i)), 0)

  let low = -0.9999
  let high = 10
  let npvLow = npv(low)
  const npvHigh = npv(high)
  if (npvLow * npvHigh > 0) return 0

  for (let i = 0; i < 100; i += 1) {
    const mid = (low + high) / 2
    const npvMid = npv(mid)
    if (Math.abs(npvMid) < 1e-6) return mid * 100
    if (npvLow * npvMid < 0) {
      high = mid
    } else {
      low = mid
      npvLow = npvMid
    }
  }
  return ((low + high) / 2) * 100
}

/**
 * Verdict under the KPIs: IRR against an alternative return, and how much of the
 * profit comes from price growth. `flat` is the same scenario simulated with 0%
 * price growth, so growth's share is net of the extra selling costs and gains tax.
 * kind: 'loss' (no profit), 'rent_only', 'growth_only' (rent alone loses money), 'mixed'.
 */
export function buildVerdict(result, flat, benchmarkPct) {
  const profit = result.totalNetProfit
  const rentProfit = flat.totalNetProfit
  const growthProfit = profit - rentProfit
  let kind = 'mixed'
  if (!(profit > 0)) kind = 'loss'
  else if (!(growthProfit > 0)) kind = 'rent_only'
  else if (!(rentProfit > 0)) kind = 'growth_only'
  const growthSharePct = kind === 'mixed' ? (growthProfit / profit) * 100
    : kind === 'growth_only' ? 100 : 0
  return {
    kind,
    benchmarkPct,
    irrGap: result.irr - benchmarkPct,
    beatsBenchmark: result.irr >= benchmarkPct,
    profit,
    rentProfit,
    growthProfit,
    growthSharePct,
  }
}

/**
 * Purchase tax for the region: resale ITP, or new build IVA/IGIC + AJD.
 * Returns { purchaseTax, ivaRate, ajdRate, taxType }.
 */
export function calculatePurchaseTax(price, region, propertyType) {
  if (!region || !(price > 0)) return { purchaseTax: 0, ivaRate: null, ajdRate: null, taxType: 'ITP' }
  if (propertyType === 'new') {
    const ivaRate = region.igic_rate ?? IVA_RATE
    const ajdRate = region.ajd_standard || 0
    return {
      purchaseTax: price * ivaRate / 100 + price * ajdRate / 100,
      ivaRate,
      ajdRate,
      taxType: region.igic_rate != null ? 'IGIC+AJD' : 'IVA+AJD',
    }
  }
  return { purchaseTax: calculateItpAmount(price, region), ivaRate: null, ajdRate: region.ajd_standard || 0, taxType: 'ITP' }
}

/**
 * Full projection. `params` uses the field names of rental-yield-form.js.
 * `region` is optional; defaults to REGIONS lookup by params.regionId.
 */
export function simulateProjection(params, region = null) {
  const reg = region || REGIONS.find(r => r.id === params.regionId)
  if (!reg) throw new Error('region is required')
  const years = PROJECTION_YEARS

  const purchasePrice = params.purchasePrice || 0
  const closingCosts = purchasePrice * (params.closingCostsPct || 0) / 100
  const renovationCost = params.useRenovation ? (params.renovationCost || 0) : 0

  const { purchaseTax, ivaRate, ajdRate, taxType } = calculatePurchaseTax(purchasePrice, reg, params.propertyType)
  const effectiveTaxRate = purchasePrice > 0 ? (purchaseTax / purchasePrice) * 100 : 0

  const loanOpeningFee = params.useLoan ? (params.loanOpeningFee || 0) : 0
  const totalInvestment = purchasePrice + purchaseTax + closingCosts + renovationCost + loanOpeningFee

  let loanAmount = 0
  if (params.useLoan) {
    loanAmount = purchasePrice * (1 - (params.downPaymentPct || 0) / 100)
  }

  const schedule = buildMortgageSchedule(
    loanAmount, params.interestRateAnnual || 0, params.loanTermYears || 0, years,
  )

  const initialCashOutlay = (purchasePrice - loanAmount) + purchaseTax + closingCosts + loanOpeningFee + renovationCost

  const valueAfterRepairs = params.useRenovation
    ? (params.valueAfterRepairs || (purchasePrice + (params.renovationCost || 0)))
    : purchasePrice

  // Amortization base (art. 14 RIRPF): construction share of price + taxes + costs, plus improvements.
  const constructionShare = Math.min(Math.max(params.constructionSharePct ?? 70, 0), 100) / 100
  const amortizationBase = (purchasePrice + purchaseTax + closingCosts) * constructionShare + renovationCost

  const reductionPct = params.rentalReductionPct ?? 50
  const taxStatus = params.taxStatus

  const annualCashFlows = []
  const cumulativeCashFlows = []
  const netOperatingIncomes = []
  const annualTaxes = []
  const effectiveGrossIncomes = []
  const operatingExpensesByYear = []
  const amortizationByYear = []
  const netBaseByYear = []
  const taxBaseByYear = []

  let cumulative = 0
  let cumulativeAmortization = 0

  for (let year = 1; year <= years; year += 1) {
    const index = year - 1
    const rentMultiplier = (1 + (params.rentGrowthPct || 0) / 100) ** index
    const monthlyRentYear = (params.monthlyRent || 0) * rentMultiplier

    const renovationMonths = Math.min(Math.max(params.useRenovation ? (params.renovationDurationMonths || 0) : 0, 0), 12)
    const monthsRented = year === 1 ? Math.max(0, 12 - renovationMonths) : 12

    const effectiveGrossIncome = (monthlyRentYear * monthsRented) * (1 - (params.vacancyRatePct || 0) / 100)

    const maintenance = effectiveGrossIncome * (params.maintenanceRatePct || 0) / 100
    const management = effectiveGrossIncome * (params.managementFeePct || 0) / 100

    const expMult = (1 + (params.expenseGrowthRatePct || 0) / 100) ** index
    const totalAnnualExpenses = (params.annualIBI || 0) * expMult
      + ((params.monthlyCommunity || 0) * 12) * expMult
      + (params.annualHomeInsurance || 0) * expMult
      + (params.annualRentalInsurance || 0) * expMult
      + maintenance
      + management

    const netOperatingIncome = effectiveGrossIncome - totalAnnualExpenses

    effectiveGrossIncomes.push(effectiveGrossIncome)
    operatingExpensesByYear.push(totalAnnualExpenses)

    const remainingAmortization = Math.max(amortizationBase - cumulativeAmortization, 0)
    const annualAmortization = Math.min(amortizationBase * AMORTIZATION_RATE, remainingAmortization)
    cumulativeAmortization += annualAmortization
    amortizationByYear.push(annualAmortization)

    const interest = schedule.interestByYear[index] || 0
    const netBase = Math.max(effectiveGrossIncome - totalAnnualExpenses - interest - annualAmortization, 0)

    let taxBase = 0
    let annualRentalTax = 0
    if (taxStatus === 'resident') {
      taxBase = netBase * (1 - reductionPct / 100)
      annualRentalTax = taxBase * ((params.personalTaxRatePct || 0) / 100)
    } else if (taxStatus === 'non_resident_eu') {
      taxBase = netBase
      annualRentalTax = taxBase * EU_RATE
    } else if (taxStatus === 'non_resident_non_eu') {
      taxBase = params.useNonEuDeductions ? netBase : effectiveGrossIncome
      annualRentalTax = taxBase * NON_EU_RATE
    }
    netBaseByYear.push(netBase)
    taxBaseByYear.push(taxBase)

    const annualMortgagePayment = schedule.totalPaidByYear[index] || 0
    const annualCashFlow = netOperatingIncome - annualMortgagePayment - annualRentalTax

    cumulative += annualCashFlow
    annualCashFlows.push(annualCashFlow)
    cumulativeCashFlows.push(cumulative)
    netOperatingIncomes.push(netOperatingIncome)
    annualTaxes.push(annualRentalTax)
  }

  const firstYearNOI = netOperatingIncomes[0] || 0
  const firstYearTax = annualTaxes[0] || 0
  const firstYearMortgage = schedule.totalPaidByYear[0] || 0
  const firstYearCashFlow = annualCashFlows[0] || 0

  let netYield = 0
  const acquisitionBase = purchasePrice + purchaseTax + closingCosts + renovationCost
  if (acquisitionBase > 0) netYield = ((firstYearNOI - firstYearTax) / acquisitionBase) * 100

  const grossYield = purchasePrice > 0 ? ((params.monthlyRent || 0) * 12 / purchasePrice) * 100 : 0

  const holdYears = Math.min(Math.max(params.holdYears || 1, 1), 50)
  const appreciationRate = params.appreciationRatePct || 0
  const priceAfterHold = valueAfterRepairs * (1 + appreciationRate / 100) ** holdYears
  const plusvalia = params.plusvalia || 0
  const sellingCostsAmount = priceAfterHold * ((params.costToSellPct || 0) / 100) + plusvalia
  const netSalePrice = priceAfterHold - sellingCostsAmount

  const amortizationUsed = amortizationByYear.slice(0, holdYears).reduce((s, v) => s + v, 0)
  const loanCost = params.useLoan ? (params.loanOpeningFee || 0) : 0
  const taxAcquisitionCost = purchasePrice + purchaseTax + closingCosts + renovationCost + loanCost - amortizationUsed
  const capitalGain = netSalePrice - valueAfterRepairs
  const capitalGainForTax = netSalePrice - taxAcquisitionCost

  const principalRemaining = schedule.principalRemainingByYear[holdYears] || 0

  const exitTax = calculateExitTax(capitalGainForTax, taxStatus)

  const netSaleAfterTax = netSalePrice - exitTax
  const netFromSale = netSaleAfterTax - principalRemaining
  const cumulativeCashFlowToHold = cumulativeCashFlows[holdYears - 1] || 0

  const totalCashReceivedAfterTax = netFromSale + cumulativeCashFlowToHold
  const totalNetProfit = totalCashReceivedAfterTax - initialCashOutlay
  const totalPurchaseCosts = purchaseTax + closingCosts
  const totalSaleCosts = sellingCostsAmount + exitTax

  let totalRoi = 0
  if (initialCashOutlay > 0) totalRoi = (totalNetProfit / initialCashOutlay) * 100

  const sumHold = arr => arr.slice(0, holdYears).reduce((s, v) => s + v, 0)
  const totalRentalIncome = sumHold(effectiveGrossIncomes)
  const totalExpenses = sumHold(operatingExpensesByYear)
  const totalNetOperatingIncome = sumHold(netOperatingIncomes)
  const totalMortgagePayments = sumHold(schedule.totalPaidByYear)
  const totalIncomeTaxes = sumHold(annualTaxes)
  const totalNetCashFlow = totalRentalIncome - totalExpenses - totalMortgagePayments - totalIncomeTaxes

  const principalRepaidToDate = Math.max(0, loanAmount - principalRemaining)
  const principalRepaidPct = loanAmount > 0 ? (principalRepaidToDate / loanAmount) * 100 : 0

  const cashOnCashReturn = initialCashOutlay > 0 ? (firstYearCashFlow / initialCashOutlay) * 100 : 0

  let irr = 0
  if (initialCashOutlay > 0) {
    const cashflows = [-initialCashOutlay]
    for (let year = 1; year <= holdYears; year += 1) {
      let cf = annualCashFlows[year - 1] || 0
      if (year === holdYears) cf += netFromSale
      cashflows.push(cf)
    }
    irr = calculateIrrFromCashflows(cashflows)
  }

  // Chart series, index 0..years (year 0 = purchase).
  const propertyValueByYear = []
  const equityByYear = []
  for (let y = 0; y <= years; y += 1) {
    const value = valueAfterRepairs * (1 + appreciationRate / 100) ** y
    propertyValueByYear.push(value)
    equityByYear.push(value - (schedule.principalRemainingByYear[y] || 0))
  }

  return {
    holdYears,
    taxType,
    totalInvestment,
    purchaseTax,
    closingCosts,
    initialCashOutlay,
    annualCashFlows,
    cumulativeCashFlows,
    netOperatingIncomes,
    annualTaxes,
    firstYearCashFlow,
    monthlyCashFlow: firstYearCashFlow / 12,
    firstYearNOI,
    firstYearTax,
    firstYearMortgage,
    grossYield,
    netYield,
    cashOnCashReturn,
    totalRoi,
    schedule,
    ivaRate,
    effectiveTaxRate,
    ajdRate,
    effectiveGrossIncomes,
    operatingExpensesByYear,
    amortizationByYear,
    amortizationBase,
    amortizationUsed,
    netBaseByYear,
    taxBaseByYear,
    valueAfterRepairs,
    priceAfterHold,
    propertyValueByYear,
    equityByYear,
    capitalGain,
    capitalGainForTax,
    taxAcquisitionCost,
    exitTax,
    sellingCostsAmount,
    netSalePrice,
    netSaleAfterTax,
    netFromSale,
    totalCashReceivedAfterTax,
    totalRentalIncome,
    totalMortgagePayments,
    totalIncomeTaxes,
    totalExpenses,
    totalNetOperatingIncome,
    totalNetCashFlow,
    totalNetProfit,
    totalPurchaseCosts,
    totalSaleCosts,
    loanAmount,
    principalRepaidToDate,
    principalRepaidPct,
    remainingMortgagePrincipal: principalRemaining,
    cumulativeCashFlowToHold,
    irr,
  }
}
