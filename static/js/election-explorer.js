// Wires the election promise explorer (article spain-election-2026-promises)
// to the pure filter logic in election-filter.js. Without JS every promise
// stays listed and the controls stay hidden.
import {
  emptyFilters,
  filterIds,
  toggleRating,
  filtersFromQuery,
  filtersToQuery,
  isEmpty
} from './election-filter.js'

const app = document.getElementById('explorer-app')
if (app) init(app)

function init (app) {
  const controls = app.querySelector('.el-controls')
  const q = app.querySelector('#el-q')
  const partySel = app.querySelector('#el-party')
  const topicSel = app.querySelector('#el-topic')
  const rateBtns = [...app.querySelectorAll('.el-rate')]
  const count = app.querySelector('#el-count')
  const clearBtn = app.querySelector('#el-clear')
  const empty = app.querySelector('#el-empty')
  const sections = [...app.querySelectorAll('.el-topic')]
  const nodes = [...app.querySelectorAll('.el-item')]
  const items = nodes.map(el => ({
    id: el.id,
    party: el.dataset.party,
    topic: el.dataset.topic,
    f: el.dataset.f,
    text: el.textContent
  }))
  const parties = [...partySel.options].map(o => o.value).filter(Boolean)
  const topics = [...topicSel.options].map(o => o.value).filter(Boolean)
  let filters = filtersFromQuery(location.search, parties, topics)

  function render (updateUrl) {
    q.value = filters.q
    partySel.value = filters.party
    topicSel.value = filters.topic
    rateBtns.forEach(b => b.setAttribute('aria-pressed', String(filters.ratings.includes(b.dataset.rating))))
    const shown = new Set(filterIds(items, filters))
    nodes.forEach(el => { el.hidden = !shown.has(el.id) })
    sections.forEach(s => {
      const n = s.querySelectorAll('.el-item:not([hidden])').length
      s.hidden = n === 0
      s.querySelector('.el-topic-n').textContent = n
    })
    count.textContent = isEmpty(filters)
      ? `Showing all ${items.length} promises`
      : `Showing ${shown.size} of ${items.length} promises`
    clearBtn.hidden = isEmpty(filters)
    empty.hidden = shown.size > 0
    if (updateUrl) {
      history.replaceState(null, '', location.pathname + filtersToQuery(filters) + location.hash)
    }
  }

  function set (patch) {
    filters = { ...filters, ...patch }
    render(true)
  }

  let typing
  q.addEventListener('input', () => {
    clearTimeout(typing)
    typing = setTimeout(() => set({ q: q.value }), 150)
  })
  partySel.addEventListener('change', () => set({ party: partySel.value }))
  topicSel.addEventListener('change', () => set({ topic: topicSel.value }))
  rateBtns.forEach(b => b.addEventListener('click', () => set({ ratings: toggleRating(filters.ratings, b.dataset.rating) })))
  app.querySelectorAll('.el-clear').forEach(b => b.addEventListener('click', () => {
    filters = emptyFilters()
    render(true)
    q.focus()
  }))

  // Links elsewhere in the article: comparison chips and headline promises
  // show their item in the sheet (or, without <dialog> support, open it in
  // the explorer); "see all <party> promises" filters by party and scrolls.
  const sheet = initSheet(document.getElementById('el-sheet'))
  document.addEventListener('click', e => {
    const a = e.target.closest('a[data-open], a[data-filter-party]')
    if (!a) return
    e.preventDefault()
    if (a.dataset.filterParty) {
      filters = { ...emptyFilters(), party: a.dataset.filterParty }
      render(true)
      document.getElementById('explorer-app').scrollIntoView({ behavior: 'smooth', block: 'start' })
      return
    }
    if (sheet) sheet.open(a)
    else openItem(a.dataset.open)
  })

  function openItem (id) {
    const el = document.getElementById(id)
    if (!el || !el.classList.contains('el-item')) return
    if (el.hidden) {
      filters = emptyFilters()
      render(true)
    }
    el.open = true
    history.replaceState(null, '', location.pathname + filtersToQuery(filters) + '#' + id)
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    el.querySelector('summary').focus({ preventScroll: true })
  }

  controls.hidden = false
  render(false)
  if (location.hash.startsWith('#p-')) openItem(location.hash.slice(1))
}

// The promise sheet. open(link) shows the link's promise; the arrows step
// through the other visible links in the same board or headline list, and
// closing puts focus (and the scroll position) back on the current link.
function initSheet (dlg) {
  if (!dlg || typeof dlg.showModal !== 'function') return null
  const scroll = dlg.querySelector('.el-sheet-scroll')
  const context = dlg.querySelector('.el-sheet-context')
  const badge = dlg.querySelector('.el-sheet-head .el-badge')
  const title = dlg.querySelector('.el-sheet-title')
  const meta = dlg.querySelector('.el-sheet-head .el-item-meta')
  const body = dlg.querySelector('.el-sheet-body')
  const nav = dlg.querySelector('.el-sheet-nav')
  const posText = dlg.querySelector('.el-sheet-pos')
  const [prev, next] = dlg.querySelectorAll('.el-sheet-step')
  let list = []
  let pos = 0
  let hashBefore = ''

  function show () {
    const link = list[pos]
    list.forEach(a => a.classList.toggle('is-current', a === link))
    const item = document.getElementById(link.dataset.open)
    const f = item.dataset.f
    const row = link.closest('.el-board-row')
    const approach = row && row.querySelector('.el-board-approach')
    context.textContent = approach ? approach.textContent : ''
    context.hidden = !approach
    dlg.className = `el-sheet el-r-${f}`
    dlg.style.setProperty('--pc', item.style.getPropertyValue('--pc'))
    badge.textContent = f
    title.innerHTML = item.querySelector('.el-item-title').innerHTML
    meta.innerHTML = item.querySelector('.el-item-meta').innerHTML
    body.replaceChildren(item.querySelector('.el-item-body').cloneNode(true))
    nav.hidden = list.length < 2
    posText.textContent = `${pos + 1} of ${list.length}`
    prev.disabled = pos === 0
    next.disabled = pos === list.length - 1
    scroll.scrollTop = 0
    history.replaceState(null, '', location.pathname + location.search + '#' + item.id)
  }

  function step (d) {
    const to = pos + d
    if (to < 0 || to >= list.length) return
    pos = to
    show()
  }

  prev.addEventListener('click', () => step(-1))
  next.addEventListener('click', () => step(1))
  dlg.querySelector('[data-sheet-close]').addEventListener('click', () => dlg.close())
  // A click on the backdrop lands on the <dialog> itself.
  dlg.addEventListener('click', e => { if (e.target === dlg) dlg.close() })
  dlg.addEventListener('keydown', e => {
    const d = { ArrowLeft: -1, ArrowRight: 1 }[e.key]
    if (d && !e.altKey && !e.metaKey) { e.preventDefault(); step(d) }
  })
  dlg.addEventListener('close', () => {
    history.replaceState(null, '', location.pathname + location.search + hashBefore)
    const link = list[pos]
    list.forEach(a => a.classList.remove('is-current'))
    if (link) {
      link.focus({ preventScroll: true })
      link.scrollIntoView({ block: 'nearest' })
    }
  })

  return {
    open (link) {
      const group = link.closest('.el-board, .el-heads')
      list = group
        ? [...group.querySelectorAll('a[data-open]')].filter(a => !a.hidden && a.offsetParent !== null)
        : [link]
      if (!list.includes(link)) list = [link]
      pos = list.indexOf(link)
      hashBefore = location.hash.startsWith('#p-') ? '' : location.hash
      show()
      if (!dlg.open) dlg.showModal()
      dlg.querySelector('[data-sheet-close]').focus()
    }
  }
}
