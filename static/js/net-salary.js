import { calculateNetSalary, compareRegions, resolveGross, combinedScale } from './net-salary-calc.js'
import { isForal } from './net-salary-foral.js'
import {
  sanitizeState, parseStateFromParams, stateToParams, clampField, inputValue,
  DEFAULTS, FIELD_LIMITS, QUERY_KEYS, MAX_DESC_DISAB, MAX_ASC_DISAB,
} from './net-salary-form.js'

const STORAGE_KEY = 'ns-calculator-state'
const $ = id => document.getElementById(id)

const COLOR = { net: '#2FA35F', irpf: '#D95D5D', ss: '#E8933C', employer: '#B0B9C4' }
const SEGS = ['mode', 'period', 'payments', 'regime', 'age', 'contract', 'healthMode', 'mealsMode', 'transportMode', 'nurseryMode']
const SELECTS = ['region', 'disability', 'joint']
const CHECKS = ['mobility', 'sharedCustody']
const DIS_LABELS = { 33: '33–64%', '33h': '33–64% with help', 65: '65% or more' }
const LIST_MAX = { descDisab: MAX_DESC_DISAB, ascDisab: MAX_ASC_DISAB }

let combineBrackets = false
let lastResult = null

// ── formatting ──────────────────────────────────────────────────────────────
function fmtEur(n, digits = 0) {
  const num = Number(n)
  if (!Number.isFinite(num)) return '—'
  const abs = Math.abs(num).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })
  return `${num < -0.004 ? '−' : ''}${abs} €`
}
const fmtEur2 = n => fmtEur(n, 2)
const fmtPct = (n, digits = 1) => (Number.isFinite(n) ? `${(n * 100).toFixed(digits)}%` : '—')
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]))

function regionName(id) {
  const opt = $('f-region').querySelector(`option[value="${id}"]`)
  return opt ? opt.textContent : id
}

// ── state ───────────────────────────────────────────────────────────────────
const regionIds = () => Array.from($('f-region').options).map(o => o.value)

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
  return structuredClone(DEFAULTS)
}

function persist(state) {
  try { window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state)) } catch { /* private mode */ }
  try {
    const url = new URL(window.location.href)
    for (const key of Object.values(QUERY_KEYS)) url.searchParams.delete(key)
    for (const [k, v] of stateToParams(state)) url.searchParams.set(k, v)
    window.history.replaceState({}, '', url.toString())
  } catch { /* ignore */ }
}

// ── form wiring ─────────────────────────────────────────────────────────────
function syncSeg(key, value) {
  $(`f-${key}`).querySelectorAll('button[data-v]').forEach(b => {
    const on = b.dataset.v === value
    b.classList.toggle('on', on)
    b.setAttribute('aria-pressed', on ? 'true' : 'false')
  })
}

function sliderRange(state) {
  const monthly = state.period === 'm'
  return monthly ? { max: 12000, step: 50 } : { max: 150000, step: 500 }
}

function syncAmountUi(state) {
  const net = state.mode === 'net'
  const per = state.period === 'm' ? (net ? 'a payslip' : 'a month') : 'a year'
  $('l-amount').textContent = net ? 'Net pay you want' : 'Gross salary'
  $('f-amount').setAttribute('aria-label', `${net ? 'Target net pay' : 'Gross salary'}, € ${per}`)
  const { max, step } = sliderRange(state)
  const slider = $('f-slider')
  slider.max = String(max)
  slider.step = String(step)
  slider.value = String(Math.min(state.amount, max))
}

function writeForm(state) {
  for (const key of Object.keys(FIELD_LIMITS)) $(`f-${key}`).value = String(state[key])
  for (const key of SELECTS) $(`f-${key}`).value = state[key]
  for (const key of CHECKS) $(`f-${key}`).checked = !!state[key]
  for (const key of SEGS) syncSeg(key, state[key])
  renderList('descDisab', state)
  renderList('ascDisab', state)
  syncAmountUi(state)
}

function renderList(key, state) {
  const root = $(`f-${key}`)
  const items = state[key]
  const ol = root.querySelector('ol')
  const who = key === 'descDisab' ? 'Child' : 'Parent'
  ol.innerHTML = items.map((level, i) => `
   <li class="ns-dis-item">
    <span class="ns-dis-name">${who} ${i + 1}</span>
    <select data-list="${key}" data-i="${i}" aria-label="${who} ${i + 1}: disability degree">
     ${Object.entries(DIS_LABELS).map(([v, t]) => `<option value="${v}"${v === level ? ' selected' : ''}>${t}</option>`).join('')}
    </select>
    <button type="button" class="ns-remove" data-remove="${key}" data-i="${i}" aria-label="Remove ${who.toLowerCase()} ${i + 1}">Remove</button>
   </li>`).join('')
  root.querySelector('.ns-add').hidden = items.length >= LIST_MAX[key]
}

function applyVisibility(state) {
  const show = { kids: state.kids + state.kidsU3 > 0 }
  document.querySelectorAll('.calc [data-show]').forEach(el => { el.hidden = !show[el.dataset.show] })
  // Region and family do not change the Beckham tax; say so instead of hiding them.
  $('g-family').classList.toggle('ns-muted', state.regime === 'beckham' && !isForal(state.region))
}

function bindInputs(state, onChange) {
  for (const key of Object.keys(FIELD_LIMITS)) {
    const el = $(`f-${key}`)
    el.addEventListener('input', () => {
      const v = inputValue(key, el.value)
      if (v === null) return
      state[key] = v
      if (key === 'amount') $('f-slider').value = String(state.amount)
      onChange()
    })
    el.addEventListener('blur', () => {
      const num = Number(el.value)
      const fixed = el.value === '' || !Number.isFinite(num) ? FIELD_LIMITS[key].min : clampField(key, num)
      if (el.value === '' || String(fixed) !== String(num)) {
        el.value = String(fixed)
        state[key] = fixed
        onChange()
      }
    })
  }
  $('f-slider').addEventListener('input', e => {
    state.amount = Number(e.target.value)
    $('f-amount').value = String(state.amount)
    onChange()
  })
  for (const key of SELECTS) $(`f-${key}`).addEventListener('change', e => { state[key] = e.target.value; onChange() })
  for (const key of CHECKS) $(`f-${key}`).addEventListener('change', e => { state[key] = e.target.checked; onChange() })
  for (const key of SEGS) {
    $(`f-${key}`).addEventListener('click', e => {
      const btn = e.target.closest('button[data-v]')
      if (!btn || state[key] === btn.dataset.v) return
      const prev = state[key]
      state[key] = btn.dataset.v
      if (key === 'period') convertAmountForPeriod(state, prev)
      if (key === 'mode') convertAmountForMode(state)
      syncSeg(key, state[key])
      syncAmountUi(state)
      onChange()
    })
  }
  for (const key of ['descDisab', 'ascDisab']) {
    const root = $(`f-${key}`)
    root.addEventListener('click', e => {
      if (e.target.closest('.ns-add')) {
        state[key] = [...state[key], '33']
      } else if (e.target.closest('.ns-remove')) {
        const i = Number(e.target.closest('.ns-remove').dataset.i)
        state[key] = state[key].filter((_, j) => j !== i)
      } else return
      renderList(key, state)
      onChange()
      const items = root.querySelectorAll('select')
      if (items.length) items[items.length - 1].focus()
      else root.querySelector('.ns-add').focus()
    })
    root.addEventListener('change', e => {
      const sel = e.target.closest('select[data-list]')
      if (!sel) return
      state[key] = state[key].map((v, j) => (j === Number(sel.dataset.i) ? sel.value : v))
      onChange()
    })
  }
  $('f-combine').addEventListener('change', e => {
    combineBrackets = e.target.checked
    if (lastResult) renderBrackets(lastResult)
  })
}

/** Keep the same salary when switching between gross and target net: show its other side. */
function convertAmountForMode(state) {
  if (!lastResult) return
  const monthly = state.period === 'm'
  let raw
  if (state.mode === 'net') raw = monthly ? lastResult.payslip.regular : lastResult.netAnnual
  else raw = monthly ? lastResult.gross / (state.payments === '14' ? 14 : 12) : lastResult.gross
  const step = monthly ? 10 : 100
  state.amount = clampField('amount', Math.round(raw / step) * step)
  $('f-amount').value = String(state.amount)
}

/** Keep the same yearly salary when switching between per year and per month. */
function convertAmountForPeriod(state, prev) {
  const n = state.mode === 'net' || state.payments !== '14' ? 12 : 14
  const raw = prev === 'y' ? state.amount / n : state.amount * n
  const step = state.period === 'm' ? 10 : 100
  state.amount = clampField('amount', Math.round(raw / step) * step)
  $('f-amount').value = String(state.amount)
}

// ── rendering ───────────────────────────────────────────────────────────────
const row = (label, value, cls = '', sub = '') => `<tr class="${cls}"><td>${label}${sub ? `<span class="ns-formula">${sub}</span>` : ''}</td><td class="num">${value}</td></tr>`

function renderPayslip(r, s) {
  const p = r.payslip
  const monthly = s.payments === '14' ? 'Ordinary month, one of 12' : s.payments === '14p' ? '12 payslips, extras prorated' : '12 payslips a year'
  $('r-ps-meta').textContent = `${monthly}, ${regionName(s.region)}${s.regime === 'beckham' ? ', Beckham law' : ''}`
  const n = 12
  const flexMonthly = r.flex.total / n
  const ssLines = r.ss.lines
  const earn = [
    row('Base salary', fmtEur2(p.grossRegular), 'ns-ps-h', 'Salario base'),
  ]
  if (r.flex.total > 0) earn.push(row('Benefits in kind', fmtEur2(flexMonthly), 'ns-ps-kind', 'Retribución en especie'))
  const ded = [
    `<tr class="ns-ps-sec"><th colspan="2" scope="rowgroup">Deductions <span lang="es">deducciones</span></th></tr>`,
    row('Social Security', `−${fmtEur2(r.ss.total / n)}`, 'ns-ps-ss', `${fmtPct((r.ss.total - ssLines.solidarity) / (r.ss.monthlyBase * 12 || 1), 2)} of ${fmtEur2(r.ss.monthlyBase)} base`),
    row(`IRPF withholding ${r.withholding.rate.toFixed(2)}%`, `−${fmtEur2(p.grossRegular - r.ss.total / n - r.pensionEmployee / n - p.regular)}`, 'ns-ps-irpf', 'Retención IRPF'),
  ]
  if (r.flex.total > 0) ded.push(row('Benefits already received', `−${fmtEur2(flexMonthly)}`, 'ns-ps-kind', 'Paid as the benefit, not in cash'))
  if (r.pensionEmployee > 0) ded.push(row('Your pension plan', `−${fmtEur2(r.pensionEmployee / n)}`, '', 'Aportación a plan de pensiones'))
  $('r-ps-earn').innerHTML = `<tr class="ns-ps-sec"><th colspan="2" scope="rowgroup">Earnings <span lang="es">devengos</span></th></tr>` + earn.join('')
  $('r-ps-ded').innerHTML = ded.join('')
  $('r-ps-net').textContent = fmtEur2(p.regular)
  $('r-ps-extra').textContent = p.extra != null
    ? `Plus 2 extra payslips of ${fmtEur2(p.extra)} in June and December`
    : ''
}

function renderKpis(r, s) {
  $('r-net-year').textContent = fmtEur(r.netAnnual)
  $('r-net-year-sub').textContent = r.hourly != null
    ? `${fmtEur2(r.hourly)} an hour at ${s.hoursPerWeek} h a week`
    : 'Enter your hours a week to see hourly pay'
  const warn = []
  if (r.warnings.includes('pensionAboveCash')) warn.push(`Your pension plan is more than the salary left after tax; counted as ${fmtEur(r.pensionEmployee)}.`)
  if (r.warnings.includes('pensionAboveLimit')) warn.push('Only €1,500 a year of your own pension contributions (more with employer contributions to a company plan) reduces your tax.')
  $('r-pension-warn').textContent = warn.join(' ')
  $('r-pension-warn').hidden = warn.length === 0
  const gross = r.totalComp || 1
  $('r-keep').textContent = fmtPct(r.annualTaxNet / gross, 1)
  $('r-keep-sub').textContent = r.marginalKeep != null
    ? `of your pay; ${Math.round(r.marginalKeep * 100)} € of every extra 100 €`
    : 'of your pay'
  const refund = r.refund
  const kpi = $('r-renta-kpi')
  kpi.classList.toggle('ns-pos', refund > 0.5)
  kpi.classList.toggle('ns-neg', refund < -0.5)
  if (Math.abs(refund) <= 0.5) {
    $('r-renta-kicker').textContent = 'At the Renta'
    $('r-renta').textContent = 'About even'
    $('r-renta-sub').textContent = 'withholding matches your tax'
  } else if (refund > 0) {
    $('r-renta-kicker').textContent = 'Refund at the Renta'
    $('r-renta').textContent = fmtEur(refund)
    $('r-renta-sub').textContent = 'withheld more than you owe'
  } else {
    $('r-renta-kicker').textContent = 'To pay at the Renta'
    $('r-renta').textContent = fmtEur(-refund)
    $('r-renta-sub').textContent = 'withheld less than you owe'
  }
}

function renderRenta(r, s) {
  const wh = r.withholding.annual
  const tax = r.irpf.total
  const max = Math.max(wh, tax, 1)
  const bar = (label, v, cls) => `
   <div class="ns-rb">
    <span class="ns-rb-l">${label}</span>
    <span class="ns-rb-track"><span class="ns-rb-fill ${cls}" style="width:${(v / max * 100).toFixed(1)}%"></span></span>
    <b class="ns-rb-v">${fmtEur(v)}</b>
   </div>`
  $('r-renta-bars').innerHTML = bar('Withheld from your payslips', wh, 'ns-rb-wh') + bar('Tax you owe for the year', tax, 'ns-rb-tax')
  let text
  if (s.regime === 'beckham') {
    text = 'Under the Beckham law the 24% withheld is final for salaries up to €600,000, so there is nothing to settle.'
  } else if (Math.abs(r.refund) <= 0.5) {
    text = 'Your withholding already matches the tax you owe for the year.'
  } else {
    const why = []
    if (r.irpf.smiDeduction > 0) why.push(`the ${fmtEur(r.irpf.smiDeduction)} deduction for low earners`)
    if (r.irpf.minimums.regional !== r.irpf.minimums.state) why.push(`${regionName(s.region)}'s higher personal minimums`)
    if (r.irpf.jointReduction > 0) why.push('the joint return')
    if (r.irpf.pensionReduction > 0) why.push('your pension contributions')
    const foral = r.irpf.regime === 'foral'
    const base = foral
      ? (r.refund > 0
        ? `Your employer withholds with the ${regionName(s.region)} percentage table, so you get about ${fmtEur(r.refund)} back when you file the Renta.`
        : `The ${regionName(s.region)} withholding table falls short of your tax for the year, so expect to pay about ${fmtEur(-r.refund)} with the Renta.`)
      : r.refund > 0
      ? `Your employer withholds with the national algorithm, so you get about ${fmtEur(r.refund)} back when you file the Renta in spring.`
      : `The national withholding falls short of what ${regionName(s.region)} charges, so expect to pay about ${fmtEur(-r.refund)} with the Renta in spring.`
    text = foral ? base : base + (why.length ? ` It comes from ${why.join(', ')} and your region's own tax scale.` : ` It comes from ${regionName(s.region)}'s own tax scale.`)
  }
  $('r-renta-text').textContent = text
}

function renderCost(r) {
  const total = r.employer.totalCost || 1
  const parts = [
    [r.flex.total > 0 ? 'Your net pay and benefits' : 'Your net pay', r.annualTaxNet + r.flex.total, COLOR.net, 'net'],
    ['IRPF', r.irpf.total, COLOR.irpf, 'irpf'],
    ['Your Social Security', r.ss.total, COLOR.ss, 'ss'],
    ['Employer Social Security', r.employer.total, COLOR.employer, 'employer'],
  ]
  const pension = (lastState.pensionEmployee || 0) + (lastState.pensionEmployer || 0)
  if (pension > 0) parts.splice(1, 0, ['Your pension plan', pension, COLOR.net, 'pension'])
  if (r.irpf.total === 0) parts.splice(parts.findIndex(x => x[3] === 'irpf'), 1)
  $('r-bar').innerHTML = parts.map(([label, v, , k]) => {
    const pct = v / total * 100
    return `<div class="ns-bar-${k}" style="width:${pct.toFixed(2)}%">${pct >= 9 ? `${Math.round(pct)}%` : ''}</div>`
  }).join('')
  $('r-bar').setAttribute('aria-label', parts.map(([l, v]) => `${l} ${Math.round(v / total * 100)}%`).join(', '))
  $('r-legend').innerHTML = parts.map(([label, v, , k]) => `<li><span class="dot ns-dot-${k}"></span>${label} <b>${fmtEur(v)}</b></li>`).join('')
    + `<li class="ns-legend-total">Total cost to your employer <b>${fmtEur(total)}</b></li>`
}

function renderDetails(r, s) {
  const ss = r.ss
  $('r-d-ss').innerHTML = [
    row('Monthly contribution base', fmtEur2(ss.monthlyBase), '', ss.capped ? 'Capped at the 5,101.20 € ceiling' : 'Yearly pay ÷ 12, extras included'),
    row('Common contingencies 4.70%', fmtEur2(ss.lines.cc), 'ind'),
    row(`Unemployment ${s.contract === 'temporary' ? '1.60' : '1.55'}%`, fmtEur2(ss.lines.unemployment), 'ind'),
    row('Training 0.10%', fmtEur2(ss.lines.fp), 'ind'),
    row('Intergenerational equity (MEI) 0.15%', fmtEur2(ss.lines.mei), 'ind'),
    ss.lines.solidarity > 0 ? row('Solidarity fee', fmtEur2(ss.lines.solidarity), 'ind', 'On pay above the ceiling, your 16.6% share') : '',
    row('Your Social Security a year', fmtEur2(ss.total), 'total b'),
  ].join('')

  const i = r.irpf
  if (i.regime === 'beckham') {
    $('r-d-irpf').innerHTML = [
      row('Taxable pay', fmtEur2(i.rit), '', 'Salary and taxable benefits, no deductions'),
      row('24% up to 600,000 €', fmtEur2(Math.min(i.rit, 600000) * 0.24), 'ind'),
      i.rit > 600000 ? row('47% above 600,000 €', fmtEur2((i.rit - 600000) * 0.47), 'ind') : '',
      row('IRPF for the year', fmtEur2(i.total), 'total b'),
    ].join('')
  } else if (i.regime === 'foral') {
    $('r-d-irpf').innerHTML = [
      row('Taxable pay', fmtEur2(i.rit), '', 'Rendimiento íntegro del trabajo'),
      row('− Social Security', fmtEur2(-ss.total), 'ind'),
      ...i.lines.map(([label, v, note, cls]) => row(label, fmtEur2(v), cls || 'ind', note || '')),
      row('IRPF for the year', fmtEur2(i.total), 'total b', `${regionName(s.region)} foral IRPF, no state share`),
      row('Effective rate', fmtPct(i.total / (r.totalComp || 1), 2), 'ind'),
      row('Marginal rate', fmtPct(i.marginalRate, 1), 'ind', 'On your next euro of taxable base'),
    ].join('')
  } else {
    $('r-d-irpf').innerHTML = [
      row('Taxable pay', fmtEur2(i.rit), '', r.flex.exempt > 0 ? `Excludes ${fmtEur(r.flex.exempt)} of tax-free benefits` : 'Rendimiento íntegro del trabajo'),
      row('− Social Security', fmtEur2(-ss.total), 'ind'),
      row('− Other deductible expenses', fmtEur2(-i.otherExpenses), 'ind', 'Art. 19.2.f: 2,000 €, more for mobility or disability'),
      i.workReduction > 0 ? row('− Work income reduction', fmtEur2(-i.workReduction), 'ind', 'Art. 20: up to 7,302 € on net pay under 19,747.50 €') : '',
      row('Taxable base', fmtEur2(i.baseImponible), 'b'),
      i.pensionReduction > 0 ? row('− Pension contributions', fmtEur2(-i.pensionReduction), 'ind') : '',
      i.jointReduction > 0 ? row('− Joint return', fmtEur2(-i.jointReduction), 'ind') : '',
      row('Base for the tax scales', fmtEur2(i.baseLiquidable), 'b', 'Base liquidable general'),
      row('State tax on the base', fmtEur2(i.stateGross), 'ind'),
      row('− State tax on your personal minimum', fmtEur2(-i.stateMin), 'ind', `Minimum ${fmtEur2(i.minimums.state)} taxed at 0%`),
      row(`${regionName(s.region)} tax on the base`, fmtEur2(i.regionalGross), 'ind'),
      row(`− ${regionName(s.region)} tax on your minimum`, fmtEur2(-i.regionalMin), 'ind', `Minimum ${fmtEur2(i.minimums.regional)}`),
      row('Gross tax', fmtEur2(i.cuotaIntegra), 'b', 'Cuota íntegra'),
      i.ceutaDeduction > 0 ? row('− Ceuta and Melilla deduction 60%', fmtEur2(-i.ceutaDeduction), 'ind') : '',
      i.smiDeduction > 0 ? row('− Deduction for low earners', fmtEur2(-i.smiDeduction), 'ind', 'Up to 590.89 € on pay under 20,048.45 €') : '',
      row('IRPF for the year', fmtEur2(i.total), 'total b', `State ${fmtEur2(i.state)}, regional ${fmtEur2(i.regional)}`),
      row('Effective rate', fmtPct(i.total / (r.totalComp || 1), 2), 'ind'),
      row('Marginal rate', fmtPct(i.marginalRate, 1), 'ind', 'On your next euro of taxable base'),
    ].join('')
  }

  const w = r.withholding
  $('r-d-wh').innerHTML = w.regime === 'beckham'
    ? [row('Flat withholding', `${w.rate.toFixed(2)}%`, 'b'), row('Withheld a year', fmtEur2(w.annual), 'total b')].join('')
    : w.regime === 'foral' ? [
      row('Pay for withholding', fmtEur2(w.retrib)),
      w.exempt
        ? row('No withholding', `Up to ${fmtEur(w.limit)}`, 'b', `${regionName(s.region)} 2026 table`)
        : row('Withholding rate', `${w.rate.toFixed(2)}%`, 'b', `${regionName(s.region)} 2026 table, by pay and number of children`),
      row('Withheld a year', fmtEur2(w.annual), 'total b'),
    ].join('')
    : [
      row('Pay for withholding', fmtEur2(w.retrib)),
      row('Base after deductions', fmtEur2(w.base), 'ind', w.largeFamilyReduction ? 'Includes −600 € for 3+ children' : 'Same deductions, national rules'),
      row('Personal and family minimum', fmtEur2(w.minimum), 'ind', 'State amounts only'),
      w.exempt
        ? row('No withholding', `Below ${fmtEur(w.limit)}`, 'b', 'Límite excluyente, art. 81 RIRPF')
        : row('Withholding tax', fmtEur2(w.cuota), 'ind', 'Withholding scale 19–47%, capped at 43% of pay above the exempt limit'),
      row('Withholding rate', `${w.rate.toFixed(2)}%`, 'b', 'Truncated to 2 decimals'),
      row('Withheld a year', fmtEur2(w.annual), 'total b'),
    ].join('')

  const er = r.employer
  $('r-d-er').innerHTML = [
    row('Your gross pay and benefits', fmtEur2(r.totalComp + (s.pensionEmployer || 0))),
    row('Common contingencies 23.60%', fmtEur2(er.lines.cc), 'ind'),
    row(`Unemployment ${s.contract === 'temporary' ? '6.70' : '5.50'}%`, fmtEur2(er.lines.unemployment), 'ind'),
    row('FOGASA 0.20%, training 0.60%, MEI 0.75%', fmtEur2(er.lines.fogasa + er.lines.fp + er.lines.mei), 'ind'),
    row(`Accident insurance ${s.atRate}%`, fmtEur2(er.lines.atep), 'ind'),
    er.lines.solidarity > 0 ? row('Solidarity fee, employer share', fmtEur2(er.lines.solidarity), 'ind') : '',
    row('Total cost to your employer', fmtEur2(er.totalCost), 'total b'),
  ].join('')
  renderBrackets(r)
}

function renderBrackets(r) {
  const i = r.irpf
  const head = $('r-d-br-head')
  const body = $('r-d-br')
  if (i.regime === 'beckham') {
    head.innerHTML = ''
    body.innerHTML = '<tr><td>Flat 24% under the Beckham law, no brackets.</td></tr>'
    return
  }
  const rangeLabel = b => `${fmtEur(b.from)} – ${b.to == null ? '…' : fmtEur(b.to)}`
  if (combineBrackets && i.stateBrackets.length) {
    // Merge both scales into one: every boundary of either scale starts a new slice.
    const edges = [...new Set([0, ...i.stateBrackets.map(b => b.to), ...i.regionalBrackets.map(b => b.to)]
      .filter(v => v != null && v < i.baseLiquidable))].sort((a, b) => a - b)
    const rateAt = (brackets, x) => (brackets.find(b => b.to == null || x < b.to) || brackets[brackets.length - 1]).rate
    head.innerHTML = '<tr><th>Taxable base</th><th class="num">Combined rate</th><th class="num">Tax</th></tr>'
    body.innerHTML = edges.map((from, k) => {
      const to = k + 1 < edges.length ? edges[k + 1] : i.baseLiquidable
      const rate = rateAt(i.stateBrackets, from) + rateAt(i.regionalBrackets, from)
      return `<tr><td>${fmtEur(from)} – ${fmtEur(to)}</td><td class="num">${(rate * 100).toFixed(2)}%</td><td class="num">${fmtEur2((to - from) * rate)}</td></tr>`
    }).join('')
    return
  }
  head.innerHTML = '<tr><th>Scale</th><th>Bracket</th><th class="num">Rate</th><th class="num">Tax</th></tr>'
  const rows = (name, list) => list.map((b, k) => `<tr><td>${k === 0 ? name : ''}</td><td>${rangeLabel(b)}</td><td class="num">${(b.rate * 100).toFixed(2)}%</td><td class="num">${fmtEur2(b.taxAmount)}</td></tr>`).join('')
  body.innerHTML = rows('State', i.stateBrackets) + rows(regionName(lastState.region), i.regionalBrackets)
}

function renderRegions(s, r) {
  const rows = compareRegions({ ...s, gross: r.gross })
  const mine = rows.find(x => x.region === s.region)
  $('r-regions-note').textContent = s.regime === 'beckham'
    ? 'Under the Beckham law the region does not change your tax.'
    : 'Net pay after the Renta settles your tax for the year, highest first. Per month is the yearly net ÷ 12.'
  $('r-regions').innerHTML = rows.map(x => {
    const diff = x.annualTaxNet - mine.annualTaxNet
    const cur = x.region === s.region
    const d = cur ? 'Your region' : Math.abs(diff) < 1 ? 'Same' : `${diff > 0 ? '+' : '−'}${fmtEur(Math.abs(diff) / 12)}/mo`
    return `<tr class="${cur ? 'ns-cur' : ''}"><td>${esc(regionName(x.region))}</td><td class="num">${fmtEur(x.annualTaxNet / 12)}</td><td class="num">${fmtEur(x.annualTaxNet)}</td><td class="num ${diff > 0.5 && !cur ? 'ns-up' : diff < -0.5 && !cur ? 'ns-down' : ''}">${d}</td></tr>`
  }).join('')
}

// ── tax brackets by region tab ──────────────────────────────────────────────
const pct = r => `${(r * 100).toFixed(2).replace(/\.?0+$/, '')}%`
const rateAtBase = (slices, x) => slices.find(sl => sl.to == null || x < sl.to).rate

function renderScale(region) {
  const { slices, foral, share } = combinedScale(region)
  const name = regionName(region)
  $('r-scale-note').textContent = foral
    ? `${name} runs its own (foral) IRPF: one scale, no state half.`
    : share < 1
      ? `${name} applies the state scale to both halves, then a 60% deduction: you pay ${share * 100}% of the combined rate shown.`
      : `The state scale is the same everywhere; the regional half is set by ${name}. Applied to the taxable base after your personal minimum.`
  const top = slices.at(-1).rate
  $('r-scale').innerHTML = slices.map(sl => {
    const nb = n => fmtEur(n).replace(/ /g, ' ')
    const range = sl.to == null ? `From ${nb(sl.from)}` : `${nb(sl.from)} – ${nb(sl.to)}`
    const w = r => `${(r / Math.max(top, 0.5)) * 100}%`
    return `<tr><td>${range}</td><td class="num">${foral ? '—' : pct(sl.state)}</td><td class="num">${pct(sl.regional)}</td>`
      + `<td class="num b">${pct(sl.rate * share)}</td>`
      + `<td class="ns-sc-barcol" aria-hidden="true"><div class="ns-sc-bar"><span style="width:${w(sl.state * share)}"></span><span style="width:${w(sl.regional * share)}"></span></div></td></tr>`
  }).join('')
  document.querySelectorAll('#r-scale-all tr').forEach(tr => tr.classList.toggle('ns-cur', tr.dataset.region === region))
}

function initScales() {
  const pick = $('f-scale-region')
  pick.innerHTML = $('f-region').innerHTML
  $('r-scale-all').innerHTML = regionIds().map(id => {
    const { slices, share } = combinedScale(id)
    const at = x => pct(rateAtBase(slices, x) * share)
    const last = slices.at(-1)
    return `<tr data-region="${id}"><td>${esc(regionName(id))}</td><td class="num">${at(0)}</td><td class="num">${at(30000)}</td>`
      + `<td class="num">${at(60000)}</td><td class="num">${pct(last.rate * share)}</td><td class="num">${fmtEur(last.from)}</td></tr>`
  }).join('')
  $('r-scale-all').addEventListener('click', e => {
    const tr = e.target.closest('tr[data-region]')
    if (!tr) return
    pick.value = tr.dataset.region
    renderScale(pick.value)
    pick.scrollIntoView({ behavior: 'smooth', block: 'center' })
  })
  pick.addEventListener('change', () => renderScale(pick.value))

  const tabs = [$('t-calc'), $('t-scales')]
  const select = (tab, focus) => {
    tabs.forEach(t => {
      const on = t === tab
      t.setAttribute('aria-selected', String(on))
      t.tabIndex = on ? 0 : -1
      $(t.getAttribute('aria-controls')).hidden = !on
    })
    if (tab.id === 't-scales') {
      pick.value = $('f-region').value
      renderScale(pick.value)
    }
    if (focus) tab.focus()
  }
  tabs.forEach((t, k) => {
    t.addEventListener('click', () => select(t))
    t.addEventListener('keydown', e => {
      if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return
      e.preventDefault()
      select(tabs[(k + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length], true)
    })
  })
}

function renderSummaries(s) {
  const you = []
  if (s.age !== 'u65') you.push(s.age === '75plus' ? '75+' : '65–74')
  if (s.contract === 'temporary') you.push('temporary')
  if (s.disability !== '0') you.push('disability')
  if (s.joint !== 'none') you.push('joint return')
  if (s.mobility) you.push('moved')
  const kids = s.kids + s.kidsU3
  const fam = []
  if (kids) fam.push(`${kids} ${kids === 1 ? 'child' : 'children'}`)
  const asc = s.asc65 + s.asc75
  if (asc) fam.push(`${asc} ${asc === 1 ? 'parent' : 'parents'}`)
  const flexTotal = s.health + s.meals + s.transport + s.nursery
  const more = []
  if (s.pensionEmployee + s.pensionEmployer > 0) more.push('pension')
  $('s-you').textContent = you.join(', ')
  $('s-family').textContent = fam.join(', ')
  $('s-flex').textContent = flexTotal > 0 ? fmtEur(flexTotal) : ''
  $('s-more').textContent = more.join(', ')
}

let lastState = null

function render(state) {
  const gross = resolveGross(state)
  const r = calculateNetSalary({ ...state, gross })
  lastResult = r
  lastState = state
  const note = state.mode === 'net'
    ? `You need ${fmtEur(gross)} gross a year${state.payments === '14' ? ` (${fmtEur(gross / 14)} × 14)` : ''}.`
    : state.period === 'm' ? `${fmtEur(gross)} a year.` : `${fmtEur(gross / (state.payments === '14' ? 14 : 12))} gross a month${state.payments === '14' ? ', 14 payslips' : ''}.`
  $('f-amount-note').textContent = note
  if (r.flex.total > 0.3 * Math.max(gross, 1)) {
    $('f-amount-note').textContent += ' Benefits in kind above 30% of pay are not allowed (art. 26 ET).'
  }
  applyVisibility(state)
  renderSummaries(state)
  // Foral regions have no Beckham law: render as the standard regime the calculation used.
  const s = isForal(state.region) && state.regime === 'beckham' ? { ...state, regime: 'standard' } : state
  renderPayslip(r, s)
  renderKpis(r, s)
  renderRenta(r, s)
  renderCost(r)
  renderDetails(r, s)
  renderRegions(s, r)
}

function syncShareLinks() {
  const wrap = document.querySelector('.calc-share .share-wrap')
  if (!wrap) return
  const pageUrl = window.location.href
  const text = 'My Spanish net salary, payslip and Renta refund — Spanified calculator'
  const u = encodeURIComponent(pageUrl)
  const t = encodeURIComponent(text)
  const set = (sel, href) => { const a = wrap.querySelector(sel); if (a) a.href = href }
  set('a[href*="x.com/intent"]', `https://x.com/intent/tweet?text=${t}&url=${u}`)
  set('a[href*="facebook.com/sharer"]', `https://www.facebook.com/sharer/sharer.php?u=${u}`)
  set('a[href*="t.me/share"]', `https://t.me/share/url?url=${u}&text=${t}`)
  set('a[href*="wa.me"]', `https://wa.me/?text=${t}%20${u}`)
  set('a[href*="threads"]', `https://www.threads.net/intent/post?text=${t}%20${u}`)
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
        if (label) label.textContent = 'Copy'
        btn.classList.remove('is-copied')
      }, 1500)
    }
    const url = btn.dataset.url || window.location.href
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(url).then(done, () => {})
    }
  })
}

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
    Object.assign(state, structuredClone(DEFAULTS))
    writeForm(state)
    update()
  })
  wireShareCopy()
  initScales()
  render(state)
  syncShareLinks()
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init)
} else {
  init()
}
