import { calculateAutonomo } from './autonomo-calc.js'
import { sanitizeState, parseStateFromParams, DEFAULTS, QUERY_KEYS } from './autonomo-form.js'

const STORAGE_KEY = 'aut-calculator-state'
const $ = id => document.getElementById(id)

function fmtEur(n) {
  const num = Number(n)
  if (Number.isNaN(num)) return '—'
  return `${num.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })} €`
}

function fmtPct(n) {
  if (typeof n !== 'number' || Number.isNaN(n)) return '—'
  return `${(n * 100).toFixed(1)}%`
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
      url.searchParams.set(param, String(state[key]))
    }
    window.history.replaceState({}, '', url.toString())
  } catch { /* ignore */ }
}

// Number input with edit-friendly behaviour: empty allowed while typing,
// clamped to [min,max] on valid entry, reset to min on blur-if-empty.
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

function bindSeg(id, key, state, onChange, numeric) {
  const el = $(id)
  el.addEventListener('click', e => {
    const btn = e.target.closest('button[data-v]')
    if (!btn) return
    const v = numeric ? Number(btn.dataset.v) : btn.dataset.v
    if (state[key] === v) return
    state[key] = v
    syncSeg(el, v)
    onChange()
  })
}

function syncSeg(el, value) {
  el.querySelectorAll('button[data-v]').forEach(b => {
    b.classList.toggle('on', b.dataset.v === String(value))
  })
}

function syncChildrenOptions(state) {
  const chu3 = $('f-chu3')
  const max = Math.min(state.numChildren, 10)
  const cur = Math.min(state.childrenUnder3, max)
  chu3.innerHTML = ''
  for (let i = 0; i <= max; i++) {
    const o = document.createElement('option')
    o.value = String(i)
    o.textContent = String(i)
    chu3.appendChild(o)
  }
  chu3.value = String(cur)
  state.childrenUnder3 = cur
}

function syncParentsOptions(state) {
  const par75 = $('f-par75')
  const max = Math.min(state.numParents65, 4)
  const cur = Math.min(state.numParents75, max)
  par75.innerHTML = ''
  for (let i = 0; i <= max; i++) {
    const o = document.createElement('option')
    o.value = String(i)
    o.textContent = String(i)
    par75.appendChild(o)
  }
  par75.value = String(cur)
  state.numParents75 = cur
}

function syncMobVisibility(state) {
  const wrap = $('f-mob-field')
  const active = Number(state.disabilityLevel) > 0
  wrap.hidden = !active
  if (!active && state.reducedMobility) {
    state.reducedMobility = false
    $('f-mob').checked = false
  }
}

function toggle(btnId, bodyId) {
  const btn = $(btnId)
  const body = $(bodyId)
  btn.addEventListener('click', () => {
    const open = body.hidden
    body.hidden = !open
    btn.setAttribute('aria-expanded', String(open))
    btn.classList.toggle('open', open)
  })
}

function render(state) {
  let result
  try {
    result = calculateAutonomo(state)
  } catch (e) {
    $('r-error').hidden = false
    $('r-error-text').textContent = e.message
    return
  }
  $('r-error').hidden = true

  const revenue = state.annualNetRevenue || 0
  $('r-tarifa').hidden = !result.isTarifaPlana
  $('r-ceuta').hidden = !(state.region === 'ceuta' || state.region === 'melilla')

  $('r-net').textContent = fmtEur(result.netTakeHome)
  $('r-net-mo').textContent = fmtEur(result.netTakeHomeMonthly)
  $('r-ss-mo').textContent = fmtEur(result.monthlySSQuota)
  $('r-ss-yr').textContent = fmtEur(result.annualSSTotal)
  $('r-bracket').textContent = result.ssBracketId
  $('r-irpf').textContent = fmtEur(result.irpfTotal)
  $('r-irpf-rate').textContent = fmtPct(result.effectiveIrpfRate)

  const ssRate = revenue > 0 ? result.annualSSTotal / revenue : 0
  const burden = $('r-burden')
  burden.hidden = revenue <= 0
  if (revenue > 0) {
    const ssP = (result.annualSSTotal / revenue) * 100
    const irpfP = (result.irpfTotal / revenue) * 100
    const netP = (result.netTakeHome / revenue) * 100
    const total = ssP + irpfP + netP
    const scale = total > 100 ? 100 / total : 1
    const setBar = (id, pct) => {
      const el = $(id)
      el.style.width = `${pct * scale}%`
      el.querySelector('span').style.display = pct * scale > 10 ? '' : 'none'
    }
    setBar('bar-ss', ssP)
    setBar('bar-irpf', irpfP)
    setBar('bar-net', netP)
    $('l-ss').textContent = fmtPct(ssRate)
    $('l-irpf').textContent = fmtPct(result.effectiveIrpfRate)
    $('l-net').textContent = fmtPct(result.netTakeHome / revenue)
  }

  $('b-gross').textContent = fmtEur(revenue)
  $('b-exp-p').textContent = revenue > 0 ? fmtPct(result.irpfDeduction / revenue) : ''
  $('b-exp').textContent = fmtEur(result.irpfDeduction)
  $('b-ss-p').textContent = revenue > 0 ? fmtPct(ssRate) : ''
  $('b-ss').textContent = fmtEur(result.annualSSTotal)
  $('b-ssd-p').textContent = revenue > 0 ? fmtPct(result.ssDeduction / revenue) : ''
  $('b-ssd').textContent = fmtEur(result.ssDeduction)
  $('b-taxable').textContent = fmtEur(result.irpfBase)
  $('b-st-p').textContent = result.irpfBase > 0 ? fmtPct(result.irpfState / result.irpfBase) : ''
  $('b-st').textContent = fmtEur(result.irpfState)
  $('b-reg-p').textContent = result.irpfBase > 0 ? fmtPct(result.irpfRegional / result.irpfBase) : ''
  $('b-reg').textContent = fmtEur(result.irpfRegional)
  $('b-net').textContent = fmtEur(result.netTakeHome)

  const saving = $('irpf-saving')
  if (result.personalMinimum > 0) {
    const lo = Math.round(result.personalMinimum * 0.19).toLocaleString('en-US')
    const hi = Math.round(result.personalMinimum * 0.37).toLocaleString('en-US')
    saving.textContent = `Your personal minimum: ${result.personalMinimum.toLocaleString('en-US')} € (saving you roughly ${lo}–${hi} € in taxes depending on your bracket).`
    saving.hidden = false
  } else {
    saving.hidden = true
  }
  const base = $('irpf-base')
  if (result.irpfBase > 0) {
    base.textContent = `Your current taxable base: ${result.irpfBase.toLocaleString('en-US', { maximumFractionDigits: 0 })} €`
    base.hidden = false
  } else {
    base.hidden = true
  }

  $('p-ss').textContent = fmtPct(ssRate)
  $('p-irpf').textContent = fmtPct(result.effectiveIrpfRate)
  $('p-total').textContent = fmtPct(result.effectiveTotalRate)
}

function init() {
  const state = loadState()

  $('f-revenue').value = String(state.annualNetRevenue)
  $('f-region').value = state.region
  syncSeg($('f-type'), state.autonomoType)
  syncSeg($('f-time'), state.timeAsAutonomo)
  $('f-age').value = String(state.age)
  $('f-children').value = String(state.numChildren)
  syncChildrenOptions(state)
  syncSeg($('f-dis'), state.disabilityLevel)
  $('f-mob').checked = !!state.reducedMobility
  syncMobVisibility(state)
  $('f-par65').value = String(state.numParents65)
  syncParentsOptions(state)

  const update = () => {
    syncChildrenOptions(state)
    syncParentsOptions(state)
    syncMobVisibility(state)
    render(state)
    persist(state)
  }

  bindNumber('f-revenue', 'annualNetRevenue', state, update, 0)
  $('f-region').addEventListener('change', e => { state.region = e.target.value; update() })
  bindSeg('f-type', 'autonomoType', state, update, false)
  bindSeg('f-time', 'timeAsAutonomo', state, update, false)
  bindNumber('f-age', 'age', state, update, 18, 100)
  $('f-children').addEventListener('change', e => {
    state.numChildren = Number(e.target.value)
    update()
  })
  $('f-chu3').addEventListener('change', e => {
    state.childrenUnder3 = Math.min(Number(e.target.value), state.numChildren)
    update()
  })
  bindSeg('f-dis', 'disabilityLevel', state, update, true)
  $('f-mob').addEventListener('change', e => {
    state.reducedMobility = e.target.checked
    update()
  })
  $('f-par65').addEventListener('change', e => {
    state.numParents65 = Number(e.target.value)
    update()
  })
  $('f-par75').addEventListener('change', e => {
    state.numParents75 = Math.min(Number(e.target.value), state.numParents65)
    update()
  })

  toggle('personal-toggle', 'personal-body')
  toggle('irpf-toggle', 'irpf-body')

  render(state)
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init)
} else {
  init()
}
