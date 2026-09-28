import { calculateBill, compareProviders, getTotalKwh, ELECTRICITY_TAX_RATE, VAT_RATE } from './electricity-calc.js'
import {
  sanitizeState, parseStateFromParams, encodeProviders,
  DEFAULTS, QUERY_KEYS, EMPTY_PROVIDER, MAX_PROVIDERS,
} from './electricity-form.js'

const STORAGE_KEY = 'elec-calculator-state'
const $ = id => document.getElementById(id)

let state = null
const advancedOpen = new Set()

function genId() {
  return 'p' + Math.random().toString(36).slice(2, 9)
}

function escapeHtml(v) {
  return String(v)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;')
}

function fmtEur(n) {
  const num = Number(n)
  if (Number.isNaN(num)) return '—'
  return `${num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} €`
}

function fmtNum(n, decimals = 5) {
  const num = Number(n)
  if (Number.isNaN(num)) return '0'
  return String(Number(num.toFixed(decimals)))
}

// ── State persistence (URL → localStorage → defaults) ────────────────────────
function loadState() {
  try {
    const fromUrl = parseStateFromParams(window.location.search)
    if (fromUrl) return fromUrl
  } catch { /* ignore malformed URL */ }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (raw) return sanitizeState(JSON.parse(raw))
  } catch { /* corrupted storage -> defaults */ }
  return sanitizeState(DEFAULTS)
}

function persist() {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  } catch { /* private mode etc. */ }
  try {
    const url = new URL(window.location.href)
    for (const [key, param] of Object.entries(QUERY_KEYS)) {
      if (key === 'providers') {
        url.searchParams.set(param, encodeProviders(state.providers))
      } else {
        url.searchParams.set(param, String(state.consumption[key]))
      }
    }
    window.history.replaceState({}, '', url.toString())
  } catch { /* ignore */ }
}

// ── Provider cards ───────────────────────────────────────────────────────────
function energyFieldHtml(p, i) {
  if (p.energyType === 'flat') {
    return `<div class="field">
     <label for="f-eflat-${i}">Energy price <span class="tip" title="Price per kWh on a flat (fv) tariff — the same price at any hour of the day.">?</span> <span class="sub">€ / kWh ·</span></label>
     <input id="f-eflat-${i}" type="number" min="0" max="100" step="0.00001" data-field="energiaFlat" value="${fmtNum(p.energiaFlat)}">
    </div>`
  }
  return `<div class="field-row">
    <div class="field">
     <label for="f-epunta-${i}">Punta <span class="tip" title="Peak period energy price (€/kWh). Typically weekdays 10:00–14:00 and 18:00–22:00.">?</span> <span class="sub">€ / kWh ·</span></label>
     <input id="f-epunta-${i}" type="number" min="0" max="100" step="0.00001" data-field="energiaPunta" value="${fmtNum(p.energiaPunta)}">
    </div>
    <div class="field">
     <label for="f-ellano-${i}">Llano <span class="tip" title="Flat/shoulder period energy price (€/kWh). Usually early morning and midday hours.">?</span> <span class="sub">€ / kWh ·</span></label>
     <input id="f-ellano-${i}" type="number" min="0" max="100" step="0.00001" data-field="energiaLlano" value="${fmtNum(p.energiaLlano)}">
    </div>
   </div>
   <div class="field">
    <label for="f-evalle-${i}">Valle <span class="tip" title="Off-peak period energy price (€/kWh). Typically nights and weekends — the cheapest hours.">?</span> <span class="sub">€ / kWh ·</span></label>
    <input id="f-evalle-${i}" type="number" min="0" max="100" step="0.00001" data-field="energiaValle" value="${fmtNum(p.energiaValle)}">
   </div>`
}

function providerCardHtml(p, i, canRemove) {
  const isFlat = p.energyType === 'flat'
  const open = advancedOpen.has(p.id)
  return `<div class="prov" data-i="${i}" data-id="${escapeHtml(p.id)}">
   <div class="prov-head">
    <p class="prov-title">Supplier ${i + 1} <span>${p.name ? escapeHtml(p.name) : '—'}</span></p>
    ${canRemove ? '<button type="button" class="prov-remove" data-act="remove">✕ Remove</button>' : ''}
   </div>
   <div class="field">
    <label for="f-pname-${i}">Supplier name</label>
    <input id="f-pname-${i}" type="text" maxlength="40" data-field="name" value="${escapeHtml(p.name)}" placeholder="Naturgy, Octopus…">
   </div>
   <div class="field-row">
    <div class="field">
     <label for="f-pp1-${i}">Power P1 <span class="tip" title="Peak-period capacity charge: € per kW of contracted power per day (P1 = peak hours).">?</span> <span class="sub">€ / kW/day ·</span></label>
     <input id="f-pp1-${i}" type="number" min="0" max="10" step="0.00001" data-field="potenciaP1" value="${fmtNum(p.potenciaP1)}">
    </div>
    <div class="field">
     <label for="f-pp2-${i}">Power P2 <span class="tip" title="Off-peak capacity charge: € per kW of contracted power per day (P2 = valley hours). Two-period tariffs bill both.">?</span> <span class="sub">€ / kW/day ·</span></label>
     <input id="f-pp2-${i}" type="number" min="0" max="10" step="0.00001" data-field="potenciaP2" value="${fmtNum(p.potenciaP2)}">
    </div>
   </div>
   <div class="field">
    <span class="flabel">Tariff type <span class="tip" title="Flat = one €/kWh all day. Punta/llano/valle = time-of-use pricing with three daily periods. This also switches the consumption fields on the left.">?</span></span>
    <div class="seg" data-seg="energyType">
     <button type="button" data-v="flat" class="${isFlat ? 'on' : ''}">Flat</button>
     <button type="button" data-v="punta_llano_valle" class="${isFlat ? '' : 'on'}">Punta · Llano · Valle</button>
    </div>
   </div>
   ${energyFieldHtml(p, i)}
   <div class="prov-adv">
    <button type="button" class="prov-adv-btn${open ? ' open' : ''}" data-act="advanced" aria-expanded="${open}"><span>Tariff extras (optional)</span><span class="chev" aria-hidden="true">›</span></button>
    <div class="prov-adv-body" ${open ? '' : 'hidden'}>
     <div class="field-row">
      <div class="field">
       <label for="f-bono-${i}">Bono Social <span class="tip" title="Social-bonus discount for vulnerable households, billed as € per day. Leave 0 if it does not apply to you.">?</span> <span class="sub">€ / day ·</span></label>
       <input id="f-bono-${i}" type="number" min="0" max="10" step="0.001" data-field="bonoSocialDaily" value="${fmtNum(p.bonoSocialDaily)}">
      </div>
      <div class="field">
       <label for="f-alq-${i}">Meter rental <span class="tip" title="Alquiler de contador: optional regulated meter-rental fee billed per day (usually €0.016–0.025/day).">?</span> <span class="sub">€ / day ·</span></label>
       <input id="f-alq-${i}" type="number" min="0" max="10" step="0.001" data-field="alquilerContadorDaily" value="${fmtNum(p.alquilerContadorDaily)}">
      </div>
     </div>
    </div>
   </div>
  </div>`
}

function renderProviders() {
  const wrap = $('providers')
  wrap.innerHTML = state.providers
    .map((p, i) => providerCardHtml(p, i, state.providers.length > 1))
    .join('')
  $('add-provider').hidden = state.providers.length >= MAX_PROVIDERS
}

function activeEnergyType() {
  return state.providers[0] && state.providers[0].energyType === 'punta_llano_valle'
    ? 'punta_llano_valle'
    : 'flat'
}

// ── Consumption inputs ───────────────────────────────────────────────────────
function syncConsumptionMode() {
  const flat = activeEnergyType() === 'flat'
  $('wrap-flat').hidden = !flat
  $('wrap-plv').hidden = flat
  // getTotalKwh sums the three periods when kwhFlat is absent (PLV mode)
  $('plv-total').textContent = String(getTotalKwh({
    kwhPunta: state.consumption.kwhPunta,
    kwhLlano: state.consumption.kwhLlano,
    kwhValle: state.consumption.kwhValle,
  }))
}

function syncConsumptionInputs() {
  $('f-days').value = String(state.consumption.days)
  $('f-kw').value = String(state.consumption.contractedKw)
  $('f-kwh').value = String(state.consumption.kwhFlat)
  $('f-punta').value = String(state.consumption.kwhPunta)
  $('f-llano').value = String(state.consumption.kwhLlano)
  $('f-valle').value = String(state.consumption.kwhValle)
  syncConsumptionMode()
}

const NUM_FIELDS = [
  { id: 'f-days', key: 'days', min: 1, max: 366 },
  { id: 'f-kw', key: 'contractedKw', min: 0, max: 100 },
  { id: 'f-kwh', key: 'kwhFlat', min: 0, max: 1000000 },
  { id: 'f-punta', key: 'kwhPunta', min: 0, max: 1000000 },
  { id: 'f-llano', key: 'kwhLlano', min: 0, max: 1000000 },
  { id: 'f-valle', key: 'kwhValle', min: 0, max: 1000000 },
]

function bindNumber(id, key, min, max) {
  const el = $(id)
  el.addEventListener('input', () => {
    const v = el.value
    if (v === '') return
    const num = Number(v)
    if (!Number.isNaN(num)) {
      state.consumption[key] = Math.max(min, Math.min(max === undefined ? Infinity : max, num))
      update()
    }
  })
  el.addEventListener('blur', () => {
    if (el.value === '' || Number.isNaN(Number(el.value))) {
      el.value = String(state.consumption[key])
      return
    }
    const num = Number(el.value)
    const clamped = Math.max(min, Math.min(max === undefined ? Infinity : max, num))
    if (clamped !== num) {
      el.value = String(clamped)
      state.consumption[key] = clamped
      update()
    }
  })
}

// ── Results: ranking table + per-provider breakdown ──────────────────────────
function breakdownRows(p, b) {
  const c = state.consumption
  const rows = [
    {
      label: `Power term P1 (${fmtNum(p.potenciaP1)} €/kW/day × ${fmtNum(c.days, 0)} days × ${fmtNum(c.contractedKw, 2)} kW)`,
      value: b.terminoPotenciaP1,
    },
    {
      label: `Power term P2 (${fmtNum(p.potenciaP2)} €/kW/day × ${fmtNum(c.days, 0)} days × ${fmtNum(c.contractedKw, 2)} kW)`,
      value: b.terminoPotenciaP2,
    },
    p.energyType === 'flat'
      ? {
          label: `Energy term (${fmtNum(c.kwhFlat, 0)} kWh × ${fmtNum(p.energiaFlat)} €/kWh)`,
          value: b.terminoEnergia,
        }
      : {
          label: 'Energy term (time-of-use)',
          value: b.terminoEnergia,
          detail: [
            `Punta: ${fmtNum(c.kwhPunta, 0)} kWh × ${fmtNum(p.energiaPunta)}`,
            `Llano: ${fmtNum(c.kwhLlano, 0)} kWh × ${fmtNum(p.energiaLlano)}`,
            `Valle: ${fmtNum(c.kwhValle, 0)} kWh × ${fmtNum(p.energiaValle)}`,
          ].join(' · '),
        },
    b.bonoSocial > 0 ? { label: 'Bono Social', value: b.bonoSocial } : null,
    { label: 'Subtotal', value: b.subtotal, bold: true },
    { label: `Electricity special tax (${(ELECTRICITY_TAX_RATE * 100).toFixed(6)}%)`, value: b.impuestoElectricidad },
    b.alquilerContador > 0 ? { label: 'Meter rental (alquiler de contador)', value: b.alquilerContador } : null,
    { label: 'Electricity total (before VAT)', value: b.totalElectricidad, bold: true },
    { label: `VAT (IVA ${(VAT_RATE * 100).toFixed(0)}%)`, value: b.iva },
  ].filter(Boolean)
  return rows
}

function breakdownHtml(p, b, i) {
  const rows = breakdownRows(p, b)
  return `<div class="card">
   <p class="calc-kicker">${escapeHtml(p.name || `Supplier ${i + 1}`)} — bill breakdown</p>
   <div class="card sheet">
    <table>
     <tbody>
      ${rows.map(r => `<tr class="${r.bold ? 'row-h' : ''}">
        <td>${escapeHtml(r.label)}${r.detail ? `<span class="bd-detail">${escapeHtml(r.detail)}</span>` : ''}</td>
        <td class="num">${fmtEur(r.value)}</td>
       </tr>`).join('')}
     </tbody>
    </table>
    <div class="total-strip"><span>Total to pay</span><b>${fmtEur(b.total)}</b></div>
   </div>
  </div>`
}

function renderResults() {
  const results = compareProviders(state.providers, state.consumption)
  const cheapest = results[0]
  const dearest = results[results.length - 1]
  const spread = dearest.breakdown.total - cheapest.breakdown.total

  $('r-total').textContent = fmtEur(cheapest.breakdown.total)
  $('r-best').textContent = cheapest.provider.name || 'Supplier 1'
  const saving = $('r-saving')
  saving.hidden = results.length < 2
  if (results.length >= 2) {
    saving.textContent = `— save ${fmtEur(spread)} vs the dearest of ${results.length}`
  }

  $('r-compare').innerHTML = results.map(({ provider, breakdown, rank }) => {
    const isCheapest = rank === 1
    const savings = dearest.breakdown.total - breakdown.total
    return `<tr class="${isCheapest ? 'win' : ''}">
     <td>${isCheapest ? '★ ' : ''}${escapeHtml(provider.name || `Supplier ${rank}`)}</td>
     <td class="num">${fmtEur(breakdown.terminoPotencia)}</td>
     <td class="num">${fmtEur(breakdown.terminoEnergia)}</td>
     <td class="num">${fmtEur(breakdown.subtotal)}</td>
     <td class="num">${fmtEur(breakdown.impuestoElectricidad)}</td>
     <td class="num">${fmtEur(breakdown.iva)}</td>
     <td class="num b">${fmtEur(breakdown.total)}</td>
     <td class="num save">${results.length > 1 ? (isCheapest ? 'Cheapest' : `−${fmtEur(savings)}`) : '—'}</td>
    </tr>`
  }).join('')

  $('r-breakdowns').innerHTML = results
    .map(({ provider, breakdown }, i) => breakdownHtml(provider, breakdown, i))
    .join('')
}

function update() {
  try {
    $('r-error').hidden = true
    renderResults()
  } catch (e) {
    $('r-error').hidden = false
    $('r-error-text').textContent = e.message
  }
  syncConsumptionMode()
  persist()
  syncShareLinks()
}

// ── Share menu ───────────────────────────────────────────────────────────────
function syncShareLinks() {
  const wrap = document.querySelector('.calc-share .share-wrap')
  if (!wrap) return
  const pageUrl = window.location.href
  const text = 'Spain Electricity Bill Calculator — compare electricity tariffs in Spain — Spanified'
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

// ── Init ─────────────────────────────────────────────────────────────────────
function init() {
  state = loadState()
  if (!state.providers || state.providers.length === 0) state = sanitizeState(DEFAULTS)

  syncConsumptionInputs()
  renderProviders()

  NUM_FIELDS.forEach(f => bindNumber(f.id, f.key, f.min, f.max))

  $('add-provider').addEventListener('click', () => {
    if (state.providers.length >= MAX_PROVIDERS) return
    state.providers.push({ ...EMPTY_PROVIDER, id: genId() })
    renderProviders()
    update()
  })

  const wrap = $('providers')
  wrap.addEventListener('input', e => {
    const field = e.target.closest('[data-field]')
    if (!field) return
    const card = field.closest('[data-i]')
    if (!card) return
    const i = Number(card.dataset.i)
    const p = state.providers[i]
    if (!p) return
    const key = field.dataset.field
    if (key === 'name') {
      p.name = field.value.slice(0, 40)
      const title = card.querySelector('.prov-title span')
      if (title) title.textContent = p.name || '—'
    } else if (field.value !== '') {
      const num = Number(field.value)
      if (Number.isFinite(num)) p[key] = Math.max(0, num)
    }
    update()
  })
  wrap.addEventListener('blur', e => {
    const field = e.target.closest && e.target.closest('[data-field]')
    if (!field || field.type !== 'number') return
    if (field.value === '' || Number.isNaN(Number(field.value))) {
      const card = field.closest('[data-i]')
      const p = state.providers[Number(card.dataset.i)]
      if (p) field.value = String(p[field.dataset.field] ?? 0)
    }
  }, true)
  wrap.addEventListener('click', e => {
    const card = e.target.closest('[data-i]')
    if (!card) return
    const i = Number(card.dataset.i)
    const p = state.providers[i]
    if (!p) return

    const remove = e.target.closest('[data-act="remove"]')
    if (remove) {
      if (state.providers.length <= 1) return
      state.providers.splice(i, 1)
      advancedOpen.delete(p.id)
      renderProviders()
      update()
      return
    }

    const adv = e.target.closest('[data-act="advanced"]')
    if (adv) {
      const body = card.querySelector('.prov-adv-body')
      const open = body.hidden
      body.hidden = !open
      adv.classList.toggle('open', open)
      adv.setAttribute('aria-expanded', String(open))
      if (open) advancedOpen.add(p.id)
      else advancedOpen.delete(p.id)
      return
    }

    const seg = e.target.closest('[data-seg] button[data-v]')
    if (seg) {
      const v = seg.dataset.v
      if (p.energyType === v) return
      p.energyType = v
      renderProviders()
      update()
    }
  })

  wireShareMenu()
  update()
  syncShareLinks()
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init)
} else {
  init()
}
