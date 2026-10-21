import { simulateProjection } from './rental-yield-calc.js'
import { REGIONS } from './property-buying-cost-calc.js'
import {
  sanitizeState, parseStateFromParams, stateToParams, clampField,
  DEFAULTS, FIELD_LIMITS,
} from './rental-yield-form.js'

const STORAGE_KEY = 'ry-calculator-state'
const MIN_PRICE = 10000
const $ = id => document.getElementById(id)

const COLOR_EQUITY = '#0E7A3D'
const COLOR_CASH = '#E8933C'
const COLOR_AXIS = '#9AA5B1'
const COLOR_GRID = '#EFE7D8'
const COLOR_TEXT = '#6C7A89'

let lastResult = null
let chartYear = null

// ── formatting ──────────────────────────────────────────────────────────────
function fmtEur(n) {
  const num = Number(n)
  if (!Number.isFinite(num)) return '—'
  const r = Math.round(num)
  return `${(r < 0 ? '−' : '')}${Math.abs(r).toLocaleString('en-US')} €`
}

function fmtPct(n, digits = 1) {
  if (typeof n !== 'number' || !Number.isFinite(n)) return '—'
  return `${n.toFixed(digits)}%`
}

function fmtCompact(n) {
  const abs = Math.abs(n)
  const sign = n < 0 ? '−' : ''
  if (abs >= 1e6) return `${sign}${(abs / 1e6).toFixed(abs >= 1e7 ? 0 : 1).replace(/\.0$/, '')}M`
  if (abs >= 1e3) return `${sign}${Math.round(abs / 1e3)}k`
  return `${sign}${Math.round(abs)}`
}

// ── state ───────────────────────────────────────────────────────────────────
function regionIds() {
  return Array.from($('f-regionId').options).map(o => o.value)
}

function loadState() {
  const regions = regionIds()
  try {
    const fromUrl = parseStateFromParams(window.location.search, regions)
    if (fromUrl) return fromUrl
  } catch { /* malformed URL */ }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (raw) return sanitizeState(JSON.parse(raw), regions)
  } catch { /* corrupted storage -> defaults */ }
  return { ...DEFAULTS }
}

function persist(state) {
  try { window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state)) } catch { /* private mode */ }
  try {
    const url = new URL(window.location.href)
    for (const [k, v] of stateToParams(state)) url.searchParams.set(k, v)
    window.history.replaceState({}, '', url.toString())
  } catch { /* ignore */ }
}

// ── form wiring ─────────────────────────────────────────────────────────────
function writeForm(state) {
  for (const key of Object.keys(FIELD_LIMITS)) $(`f-${key}`).value = String(state[key])
  $('f-regionId').value = state.regionId
  $('f-taxStatus').value = state.taxStatus
  $('f-rentalReductionPct').value = String(state.rentalReductionPct)
  for (const key of ['useRenovation', 'useLoan', 'useNonEuDeductions']) $(`f-${key}`).checked = !!state[key]
  syncSeg(state.propertyType)
}

function syncSeg(type) {
  $('f-propertyType').querySelectorAll('button[data-v]').forEach(b => {
    const on = b.dataset.v === type
    b.classList.toggle('on', on)
    b.setAttribute('aria-pressed', on ? 'true' : 'false')
  })
}

// New builds pay IGIC instead of IVA in regions that define an igic_rate (Canarias).
function syncNewBuildLabel(regionId) {
  const region = REGIONS.find(r => r.id === regionId)
  $('f-newbuild-tax').textContent = region && region.igic_rate != null ? 'IGIC + AJD' : 'IVA + AJD'
}

function applyVisibility(state) {
  const show = {
    renovation: state.useRenovation,
    loan: state.useLoan,
    resident: state.taxStatus === 'resident',
    noneu: state.taxStatus === 'non_resident_non_eu',
  }
  document.querySelectorAll('.calc [data-show]').forEach(el => {
    el.hidden = !show[el.dataset.show]
  })
}

function bindInputs(state, onChange) {
  for (const key of Object.keys(FIELD_LIMITS)) {
    const el = $(`f-${key}`)
    const lim = FIELD_LIMITS[key]
    el.addEventListener('input', () => {
      if (el.value === '') return
      const num = Number(el.value)
      if (!Number.isFinite(num)) return
      state[key] = clampField(key, num)
      onChange()
    })
    el.addEventListener('blur', () => {
      const num = Number(el.value)
      const fixed = el.value === '' || !Number.isFinite(num) ? lim.min : clampField(key, num)
      if (el.value === '' || String(fixed) !== String(num)) {
        el.value = String(fixed)
        state[key] = fixed
        onChange()
      }
    })
  }
  $('f-regionId').addEventListener('change', e => { state.regionId = e.target.value; onChange() })
  $('f-taxStatus').addEventListener('change', e => { state.taxStatus = e.target.value; onChange() })
  $('f-rentalReductionPct').addEventListener('change', e => { state.rentalReductionPct = Number(e.target.value); onChange() })
  for (const key of ['useRenovation', 'useLoan', 'useNonEuDeductions']) {
    $(`f-${key}`).addEventListener('change', e => { state[key] = e.target.checked; onChange() })
  }
  $('f-propertyType').addEventListener('click', e => {
    const btn = e.target.closest('button[data-v]')
    if (!btn || state.propertyType === btn.dataset.v) return
    state.propertyType = btn.dataset.v
    syncSeg(state.propertyType)
    onChange()
  })
}

// ── results ─────────────────────────────────────────────────────────────────
function showError(msg) {
  $('r-error').hidden = false
  $('r-error-text').textContent = msg
  $('r-results').hidden = true
}

// Inline validation message under the purchase price field.
function setPriceError(msg) {
  const err = $('e-purchasePrice')
  const input = $('f-purchasePrice')
  err.textContent = msg || ''
  err.hidden = !msg
  if (msg) input.setAttribute('aria-invalid', 'true')
  else input.removeAttribute('aria-invalid')
}

function setSigned(el, value) {
  el.classList.toggle('neg', value < 0)
}

function taxNote(state, r) {
  const sale = state.taxStatus === 'resident'
    ? 'Sale gain is taxed on the 2026 savings scale (19–30%).'
    : 'Sale gain is taxed at a flat 19% for non-residents.'
  if (state.taxStatus === 'resident') {
    const red = state.rentalReductionPct
    return `Resident: IRPF on net rental income (rent − expenses − mortgage interest − amortization), `
      + `${red ? `reduced by ${red}%` : 'with no reduction'}, taxed at your ${state.personalTaxRatePct}% marginal rate. ${sale}`
  }
  if (state.taxStatus === 'non_resident_eu') {
    return `Non-resident EU/EEA: 19% of net rental income (rent − expenses − mortgage interest − amortization). No reduction applies. ${sale}`
  }
  if (state.useNonEuDeductions) {
    return `Non-resident outside the EU/EEA, Audiencia Nacional 2025 ruling applied: 24% of net rental income. The ruling is under appeal, so treat this as a best case. ${sale}`
  }
  return `Non-resident outside the EU/EEA: 24% of gross rent, no deductions (current rule). ${sale}`
}

function summaryRows(r, state) {
  const rows = [
    ['Purchase price', fmtEur(state.purchasePrice)],
    [`Purchase tax (${r.taxType}, ${fmtPct(r.effectiveTaxRate, 2)})`, fmtEur(r.purchaseTax)],
    ['Closing costs', fmtEur(r.closingCosts)],
  ]
  if (state.useRenovation) rows.push(['Renovation', fmtEur(state.renovationCost)])
  if (state.useLoan) {
    rows.push(['Loan amount', fmtEur(r.loanAmount)])
    rows.push(['Monthly mortgage payment', fmtEur(r.schedule.monthlyPayment)])
  }
  rows.push(['Cash needed up front', fmtEur(r.initialCashOutlay), 'b'])
  rows.push([`Rental income, ${r.holdYears} yrs`, fmtEur(r.totalRentalIncome)])
  rows.push(['Operating expenses', fmtEur(-r.totalExpenses)])
  if (state.useLoan) rows.push(['Mortgage payments', fmtEur(-r.totalMortgagePayments)])
  rows.push(['Rental income tax', fmtEur(-r.totalIncomeTaxes)])
  rows.push(['Net cash flow from rent', fmtEur(r.totalNetCashFlow), 'b'])
  rows.push([`Sale price after ${r.holdYears} yrs`, fmtEur(r.priceAfterHold)])
  rows.push(['Selling costs (incl. plusvalía)', fmtEur(-r.sellingCostsAmount)])
  rows.push(['Capital gains tax', fmtEur(-r.exitTax)])
  if (state.useLoan) rows.push(['Mortgage payoff', fmtEur(-r.remainingMortgagePrincipal)])
  rows.push(['Cash from sale', fmtEur(r.netFromSale), 'b'])
  rows.push(['Total profit when sold', fmtEur(r.totalNetProfit), 'total'])
  return rows
}

function renderSummary(r, state) {
  const body = $('r-summary')
  body.innerHTML = ''
  for (const [label, value, cls] of summaryRows(r, state)) {
    const tr = document.createElement('tr')
    if (cls === 'total') tr.className = 'total'
    const a = document.createElement('td')
    a.className = 'row-l' + (cls === 'b' ? ' row-h' : '')
    a.textContent = label
    const b = document.createElement('td')
    b.className = 'num' + (cls === 'b' || cls === 'total' ? ' b' : '')
    b.textContent = value
    tr.append(a, b)
    body.appendChild(tr)
  }
}

function renderYears(r) {
  const rows = []
  for (let i = 0; i < r.holdYears; i += 1) {
    const mort = r.schedule.totalPaidByYear[i] || 0
    rows.push(
      `<tr><td class="row-l">${i + 1}</td>`
      + `<td class="num">${fmtEur(r.effectiveGrossIncomes[i])}</td>`
      + `<td class="num">${fmtEur(r.operatingExpensesByYear[i])}</td>`
      + `<td class="num">${fmtEur(mort)}</td>`
      + `<td class="num">${fmtEur(r.annualTaxes[i])}</td>`
      + `<td class="num b">${fmtEur(r.annualCashFlows[i])}</td>`
      + `<td class="num">${fmtEur(r.cumulativeCashFlows[i])}</td></tr>`,
    )
  }
  $('r-years').innerHTML = rows.join('')
}

// ── chart ───────────────────────────────────────────────────────────────────
function niceStep(range, ticks) {
  const raw = range / ticks
  const mag = 10 ** Math.floor(Math.log10(raw))
  const f = raw / mag
  const nice = f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10
  return nice * mag
}

function chartSeries(r) {
  const n = r.holdYears
  const equity = []
  const cash = []
  for (let y = 0; y <= n; y += 1) {
    equity.push(r.equityByYear[y])
    cash.push(y === 0 ? 0 : r.cumulativeCashFlows[y - 1])
  }
  return { n, equity, cash }
}

function renderChart(r) {
  const host = $('r-chart')
  const W = Math.max(280, Math.floor(host.clientWidth || 320))
  const H = Math.round(Math.max(230, Math.min(340, W * 0.62)))
  const m = { l: 46, r: 12, t: 12, b: 28 }
  const { n, equity, cash } = chartSeries(r)

  const all = equity.concat(cash, [0])
  let lo = Math.min(...all)
  let hi = Math.max(...all)
  if (hi === lo) hi = lo + 1
  const step = niceStep(hi - lo, 4)
  lo = Math.floor(lo / step) * step
  hi = Math.ceil(hi / step) * step

  const pw = W - m.l - m.r
  const ph = H - m.t - m.b
  const x = y => m.l + (n === 0 ? 0 : (y / n) * pw)
  const yv = v => m.t + (1 - (v - lo) / (hi - lo)) * ph
  const path = arr => arr.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)} ${yv(v).toFixed(1)}`).join(' ')

  let grid = ''
  for (let v = lo; v <= hi + step / 2; v += step) {
    const py = yv(v).toFixed(1)
    grid += `<line x1="${m.l}" x2="${W - m.r}" y1="${py}" y2="${py}" stroke="${COLOR_GRID}" stroke-width="1"/>`
      + `<text x="${m.l - 6}" y="${py}" text-anchor="end" dominant-baseline="middle" font-size="11" fill="${COLOR_TEXT}">${fmtCompact(v)}</text>`
  }
  const everyX = n <= 6 ? 1 : n <= 12 ? 2 : n <= 30 ? 5 : 10
  let xlabels = ''
  for (let y = 0; y <= n; y += everyX) {
    xlabels += `<text x="${x(y).toFixed(1)}" y="${H - 8}" text-anchor="middle" font-size="11" fill="${COLOR_TEXT}">${y}</text>`
  }
  if (n % everyX !== 0 && n - Math.floor(n / everyX) * everyX >= everyX / 2) {
    xlabels += `<text x="${x(n).toFixed(1)}" y="${H - 8}" text-anchor="middle" font-size="11" fill="${COLOR_TEXT}">${n}</text>`
  }

  const sel = Math.min(chartYear ?? n, n)
  const sx = x(sel).toFixed(1)
  const marker = `<line x1="${sx}" x2="${sx}" y1="${m.t}" y2="${m.t + ph}" stroke="${COLOR_AXIS}" stroke-width="1" stroke-dasharray="3 3"/>`
    + `<circle cx="${sx}" cy="${yv(equity[sel]).toFixed(1)}" r="4" fill="${COLOR_EQUITY}"/>`
    + `<circle cx="${sx}" cy="${yv(cash[sel]).toFixed(1)}" r="4" fill="${COLOR_CASH}"/>`

  host.innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" role="img" aria-label="Chart: equity and cumulative cash flow by year" preserveAspectRatio="xMidYMid meet">`
    + grid
    + `<line x1="${m.l}" x2="${W - m.r}" y1="${yv(0).toFixed(1)}" y2="${yv(0).toFixed(1)}" stroke="${COLOR_AXIS}" stroke-width="1" stroke-dasharray="4 3"/>`
    + `<path d="${path(equity)}" fill="none" stroke="${COLOR_EQUITY}" stroke-width="2.5" stroke-linejoin="round"/>`
    + `<path d="${path(cash)}" fill="none" stroke="${COLOR_CASH}" stroke-width="2.5" stroke-linejoin="round"/>`
    + marker + xlabels
    + `<rect class="ry-hit" x="${m.l}" y="${m.t}" width="${pw}" height="${ph}" fill="transparent"/>`
    + `</svg>`

  $('r-chart-read').textContent = `Year ${sel}: equity ${fmtEur(equity[sel])} · cumulative cash flow ${fmtEur(cash[sel])}`

  const svg = host.querySelector('svg')
  const pick = ev => {
    const rect = svg.getBoundingClientRect()
    const px = (ev.clientX - rect.left) * (W / rect.width)
    chartYear = Math.max(0, Math.min(n, Math.round(((px - m.l) / pw) * n)))
    renderChart(r)
  }
  svg.addEventListener('pointerdown', pick)
  svg.addEventListener('pointermove', ev => { if (ev.pointerType === 'mouse') pick(ev) })
}

function render(state) {
  applyVisibility(state)
  syncNewBuildLabel(state.regionId)
  if (!(state.purchasePrice >= MIN_PRICE)) {
    const min = `${MIN_PRICE.toLocaleString('en-US')} €`
    setPriceError(`Minimum ${min}.`)
    showError(`Enter a purchase price of at least ${min} to see the results.`)
    return
  }
  setPriceError('')
  let r
  try {
    r = simulateProjection(state)
  } catch (e) {
    showError(`Calculation error: ${e.message}.`)
    return
  }
  lastResult = r
  $('r-error').hidden = true
  $('r-results').hidden = false

  $('r-gross').textContent = fmtPct(r.grossYield, 2)
  $('r-net').textContent = fmtPct(r.netYield, 2)
  $('r-coc').textContent = fmtPct(r.cashOnCashReturn, 2)
  $('r-monthly').textContent = fmtEur(r.monthlyCashFlow)
  $('r-irr').textContent = fmtPct(r.irr, 2)
  $('r-irr-sub').textContent = `over ${r.holdYears} yrs, incl. sale`
  setSigned($('r-monthly'), r.monthlyCashFlow)
  setSigned($('r-coc'), r.cashOnCashReturn)
  setSigned($('r-net'), r.netYield)
  setSigned($('r-irr'), r.irr)

  $('r-profit').textContent = fmtEur(r.totalNetProfit)
  setSigned($('r-profit'), r.totalNetProfit)
  $('r-roi').textContent = `${fmtPct(r.totalRoi, 0)} total return on cash invested`
  $('r-outlay').textContent = fmtEur(r.initialCashOutlay)
  $('r-outlay-sub').textContent = `incl. ${fmtEur(r.purchaseTax)} ${r.taxType}`

  $('r-taxnote').textContent = taxNote(state, r)
  $('r-tax1').textContent = `Year-1 rental tax: ${fmtEur(r.firstYearTax)}`
  $('r-hold-label').textContent = String(r.holdYears)

  renderSummary(r, state)
  renderYears(r)
  if (chartYear !== null && chartYear > r.holdYears) chartYear = null
  renderChart(r)
}

// ── share ───────────────────────────────────────────────────────────────────
function syncShareLinks() {
  const wrap = document.querySelector('.calc-share .share-wrap')
  if (!wrap) return
  const pageUrl = window.location.href
  const text = 'Spain Rental Yield Calculator — net yield, cash-on-cash, IRR & taxes — Spanified'
  const u = encodeURIComponent(pageUrl)
  const t = encodeURIComponent(text)
  const set = (sel, href) => { const a = wrap.querySelector(sel); if (a) a.href = href }
  set('a[href*="x.com/intent"]', `https://x.com/intent/tweet?text=${t}&url=${u}`)
  set('a[href*="facebook.com/sharer"]', `https://www.facebook.com/sharer/sharer.php?u=${u}`)
  set('a[href*="t.me/share"]', `https://t.me/share/url?url=${u}&text=${t}`)
  set('a[href*="wa.me"]', `https://wa.me/?text=${t}%20${u}`)
  const copy = wrap.querySelector('.share-copy')
  if (copy) copy.dataset.url = pageUrl
}

function wireShareCopy() {
  const wrap = document.querySelector('.calc-share .share-wrap')
  if (!wrap) return
  wrap.addEventListener('click', e => {
    const btn = e.target.closest('.share-copy')
    if (!btn) return
    const label = btn.querySelector('span')
    const done = () => {
      if (label) label.textContent = 'Copied!'
      btn.classList.add('is-copied')
      setTimeout(() => {
        if (label) label.textContent = 'Copy link'
        btn.classList.remove('is-copied')
      }, 1500)
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(btn.dataset.url).then(done, done)
    } else {
      const inp = document.createElement('input')
      inp.value = btn.dataset.url
      document.body.appendChild(inp)
      inp.select()
      try { document.execCommand('copy') } catch (err) { /* ignore */ }
      document.body.removeChild(inp)
      done()
    }
  })
}

// ── init ────────────────────────────────────────────────────────────────────
function init() {
  const state = loadState()
  writeForm(state)

  const update = () => {
    render(state)
    persist(state)
    syncShareLinks()
  }

  bindInputs(state, update)
  $('r-reset').addEventListener('click', () => {
    Object.assign(state, DEFAULTS)
    writeForm(state)
    chartYear = null
    update()
  })

  wireShareCopy()
  render(state)
  syncShareLinks()

  if (typeof ResizeObserver !== 'undefined') {
    let lastW = $('r-chart').clientWidth
    new ResizeObserver(() => {
      const w = $('r-chart').clientWidth
      if (w !== lastW && lastResult && !$('r-results').hidden) { lastW = w; renderChart(lastResult) }
    }).observe($('r-chart'))
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init)
} else {
  init()
}
