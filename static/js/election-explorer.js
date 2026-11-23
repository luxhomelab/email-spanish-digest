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

  // Links elsewhere in the article: headline promises open their item,
  // "see all <party> promises" filters by party. Both scroll to the target.
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
    openItem(a.dataset.open)
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
