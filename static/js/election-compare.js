// Topic comparison boards (article spain-election-2026-promises): turns the
// stacked boards into tabs and dims every party except the highlighted one.
// Chips open their promise through the data-open handler in election-explorer.js.
const app = document.getElementById('compare-app')
if (app) init(app)

function init (app) {
  const controls = app.querySelector('.el-cmp-controls')
  const tabs = [...app.querySelectorAll('.el-cmp-tab')]
  const boards = [...app.querySelectorAll('.el-board')]
  const party = app.querySelector('#cmp-party')

  function show (key, focus) {
    tabs.forEach(t => {
      const on = t.dataset.topic === key
      t.setAttribute('aria-selected', String(on))
      t.tabIndex = on ? 0 : -1
      if (on && focus) t.focus()
    })
    boards.forEach(b => { b.hidden = b.id !== `cmp-${key}` })
  }

  tabs.forEach((t, i) => {
    t.addEventListener('click', () => show(t.dataset.topic))
    t.addEventListener('keydown', e => {
      const step = { ArrowRight: 1, ArrowLeft: -1 }[e.key]
      if (!step) return
      e.preventDefault()
      show(tabs[(i + step + tabs.length) % tabs.length].dataset.topic, true)
    })
  })

  party.addEventListener('change', () => {
    app.dataset.highlight = party.value
    app.querySelectorAll('.el-chip').forEach(c => {
      c.classList.toggle('is-dim', Boolean(party.value) && c.dataset.party !== party.value)
    })
  })

  app.classList.add('is-tabbed')
  controls.hidden = false
  show(tabs[0].dataset.topic)
}
