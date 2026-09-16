import { calculateBuyingCost, MIN_PRICE } from './property-buying-cost-calc.js'
import { sanitizeState, parseStateFromParams, DEFAULTS, QUERY_KEYS } from './property-buying-cost-form.js'

const STORAGE_KEY = 'pbc-calculator-state'
const $ = id => document.getElementById(id)

const LABELS = {
  itp: 'ITP (Transfer Tax)',
  iva: 'VAT (IVA)',
  igic: 'IGIC (Canary Islands VAT)',
  ajd: 'Stamp Duty (AJD)',
  notary: 'Notary fees (est.)',
  registry: 'Land registry (est.)',
}

const BAR_COLORS = {
  itp: 'pseg-tax', iva: 'pseg-tax', igic: 'pseg-tax',
  ajd: 'pseg-ajd', notary: 'pseg-fee', registry: 'pseg-fee2',
}

function fmtEur(n) {
  const num = Number(n)
  if (Number.isNaN(num)) return '—'
  return `${num.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })} €`
}

function fmtPct(n) {
  if (typeof n !== 'number' || Number.isNaN(n)) return '—'
  return `${n.toFixed(1)}%`
}

function regionIds() {
  return Array.from($('f-region').options).map(o => o.value)
}

function loadState() {
  const regions = regionIds()
  try {
    const fromUrl = parseStateFromParams(window.location.search, regions)
    if (fromUrl) return fromUrl
  } catch { /* ignore malformed URL */ }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (raw) return sanitizeState(JSON.parse(raw), regions)
  } catch { /* corrupted storage -> defaults */ }
  return { ...DEFAULTS }
}

function persist(state) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  } catch { /* private mode etc. */ }
  try {
    const url = new URL(window.location.href)
    for (const [key, param] of Object.entries(QUERY_KEYS)) {
      let v = state[key]
      if (key === 'isNewBuild') v = v ? '1' : '0'
      url.searchParams.set(param, String(v))
    }
    window.history.replaceState({}, '', url.toString())
  } catch { /* ignore */ }
}

function bindNumber(id, key, state, onChange, min, max) {
  const el = $(id)
  el.addEventListener('input', () => {
    const v = el.value
    if (v === '') return
    const num = Number(v)
    if (!Number.isNaN(num)) {
      state[key] = Math.max(min, Math.min(max === undefined ? Infinity : max, num))
      onChange()
    }
  })
  el.addEventListener('blur', () => {
    if (el.value === '') {
      el.value = String(min)
      state[key] = min
      onChange()
      return
    }
    const num = Number(el.value)
    if (!Number.isNaN(num)) {
      const clamped = Math.max(min, Math.min(max === undefined ? Infinity : max, num))
      if (clamped !== num) {
        el.value = String(clamped)
        state[key] = clamped
        onChange()
      }
    }
  })
}

function bindSeg(id, key, state, onChange) {
  const el = $(id)
  el.addEventListener('click', e => {
    const btn = e.target.closest('button[data-v]')
    if (!btn) return
    const v = btn.dataset.v === 'new'
    if (state[key] === v) return
    state[key] = v
    syncSeg(el, v)
    onChange()
  })
}

function syncSeg(el, isNew) {
  el.querySelectorAll('button[data-v]').forEach(b => {
    const on = (b.dataset.v === 'new') === isNew
    b.classList.toggle('on', on)
  })
}

function syncShareLinks() {
  const wrap = document.querySelector('.calc-share .share-wrap')
  if (!wrap) return
  const pageUrl = window.location.href
  const text = 'Spain Property Buying Cost Calculator — ITP, IVA/IGIC & AJD by region — Spanified'
  const u = encodeURIComponent(pageUrl)
  const t = encodeURIComponent(text)
  const set = (sel, href) => {
    const a = wrap.querySelector(sel)
    if (a) a.href = href
  }
  set('a[href*="x.com/intent"]', `https://x.com/intent/tweet?text=${t}&url=${u}`)
  set('a[href*="facebook.com/sharer"]', `https://www.facebook.com/sharer/sharer.php?u=${u}`)
  set('a[href*="t.me/share"]', `https://t.me/share/url?url=${u}&text=${t}`)
  set('a[href*="wa.me"]', `https://wa.me/?text=${t}%20${u}`)
  const copy = wrap.querySelector('.share-copy')
  if (copy) copy.dataset.url = pageUrl
}

function wireShareMenu() {
  const wrap = document.querySelector('.calc-share .share-wrap')
  if (!wrap) return
  const toggleBtn = wrap.querySelector('.share-toggle')
  const menu = wrap.querySelector('.share-menu')
  if (!toggleBtn || !menu) return
  const close = () => {
    menu.hidden = true
    toggleBtn.setAttribute('aria-expanded', 'false')
  }
  toggleBtn.addEventListener('click', e => {
    e.stopPropagation()
    const willOpen = menu.hidden
    close()
    if (willOpen) {
      menu.hidden = false
      toggleBtn.setAttribute('aria-expanded', 'true')
    }
  })
  document.addEventListener('click', e => {
    if (!e.target.closest('.calc-share .share-wrap')) close()
  })
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') close()
  })
  wrap.addEventListener('click', e => {
    const btn = e.target.closest('.share-copy')
    if (!btn) return
    const label = btn.querySelector('span')
    const done = () => {
      label.textContent = 'Copied!'
      setTimeout(() => { label.textContent = 'Copy link' }, 1500)
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(btn.dataset.url).then(done, done)
    } else {
      const inp = document.createElement('input')
      inp.value = btn.dataset.url
      document.body.appendChild(inp)
      inp.select()
      try { document.execCommand('copy') } catch (err) {}
      document.body.removeChild(inp)
      done()
    }
  })
}

function showError(msg) {
  $('r-error').hidden = false
  $('r-error-text').textContent = msg
  $('r-results').hidden = true
}

function render(state) {
  const price = Number(state.price)
  if (!Number.isFinite(price) || price < MIN_PRICE) {
    showError(`Please enter a valid property price (minimum ${MIN_PRICE.toLocaleString('en-US')} €).`)
    return
  }
  let result
  try {
    result = calculateBuyingCost({ price, isNewBuild: state.isNewBuild, regionId: state.regionId })
  } catch (e) {
    showError(e.message)
    return
  }
  if (!result) {
    showError('Unable to calculate. Please check your inputs.')
    return
  }
  $('r-error').hidden = true
  $('r-results').hidden = false

  $('r-total').textContent = fmtEur(result.totalCosts)
  $('r-total-pct').textContent = `${fmtPct(result.totalPct)} of property price`
  $('r-tax').textContent = fmtEur(result.totalTax)
  $('r-tax-pct').textContent = `${fmtPct((result.totalTax / result.totalCosts) * 100)} of total costs`
  const fees = result.notaryFee + result.registryFee
  $('r-fees').textContent = fmtEur(fees)
  $('r-fees-pct').textContent = `${fmtPct((fees / result.totalCosts) * 100)} of total costs`
  $('r-taxtype').textContent = result.taxType

  const bar = $('r-bar')
  bar.innerHTML = ''
  for (const item of result.breakdown) {
    const pct = (item.amount / result.totalCosts) * 100
    const div = document.createElement('div')
    div.className = BAR_COLORS[item.key] || 'pseg-fee2'
    div.style.width = `${pct}%`
    div.title = `${LABELS[item.key]}: ${fmtEur(item.amount)}`
    bar.appendChild(div)
  }

  const body = $('r-breakdown')
  body.innerHTML = ''
  for (const item of result.breakdown) {
    const tr = document.createElement('tr')
    const tdLabel = document.createElement('td')
    tdLabel.className = 'row-l'
    tdLabel.textContent = LABELS[item.key] || item.key
    if (item.rate != null) {
      const span = document.createElement('span')
      span.className = 'rate'
      span.textContent = ` (${Number(item.rate).toFixed(2)}%)`
      tdLabel.appendChild(span)
    }
    const tdAmount = document.createElement('td')
    tdAmount.className = 'num'
    tdAmount.textContent = fmtEur(item.amount)
    tr.appendChild(tdLabel)
    tr.appendChild(tdAmount)
    body.appendChild(tr)
  }
}

function init() {
  const state = loadState()

  $('f-price').value = String(state.price)
  $('f-region').value = state.regionId
  syncSeg($('f-type'), state.isNewBuild)

  const update = () => {
    render(state)
    persist(state)
    syncShareLinks()
  }

  bindNumber('f-price', 'price', state, update, MIN_PRICE)
  $('f-region').addEventListener('change', e => { state.regionId = e.target.value; update() })
  bindSeg('f-type', 'isNewBuild', state, update)
  $('r-calc').addEventListener('click', update)

  wireShareMenu()

  render(state)
  syncShareLinks()
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init)
} else {
  init()
}
