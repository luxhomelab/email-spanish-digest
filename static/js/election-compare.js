// Topic comparison boards (article spain-election-2026-promises): turns the
// stacked boards into tabs and narrows them to the parties the reader picks
// (any number; none picked means all). Chips open their promise through the
// data-open handler in election-explorer.js.
import { toggleIn, partyShown } from './election-filter.js'

const app = document.getElementById('compare-app')
if (app) init(app)

function init (app) {
  const controls = app.querySelector('.el-cmp-controls')
  const tabs = [...app.querySelectorAll('.el-cmp-tab')]
  const boards = [...app.querySelectorAll('.el-board')]
  const partyBtns = [...app.querySelectorAll('.el-pty')]
  const allBtn = app.querySelector('.el-pty-all')
  const order = partyBtns.map(b => b.dataset.party)
  let selected = []

  function show (key, focus) {
    tabs.forEach(t => {
      const on = t.dataset.topic === key
      t.setAttribute('aria-selected', String(on))
      t.tabIndex = on ? 0 : -1
      if (on && focus) t.focus()
    })
    boards.forEach(b => { b.hidden = b.id !== `cmp-${key}` })
  }

  function applyParties () {
    partyBtns.forEach(b => b.setAttribute('aria-pressed', String(selected.includes(b.dataset.party))))
    allBtn.hidden = !selected.length
    boards.forEach(board => {
      let shown = 0
      board.querySelectorAll('.el-chip').forEach(c => {
        c.hidden = !partyShown(c.dataset.party, selected)
        if (!c.hidden) shown++
      })
      board.querySelectorAll('.el-board-cell').forEach(cell => {
        cell.classList.toggle('is-empty', !cell.querySelector('.el-chip:not([hidden])'))
      })
      board.querySelectorAll('.el-board-row:not(.el-board-head)').forEach(row => {
        row.hidden = !row.querySelector('.el-chip:not([hidden])')
      })
      const total = Number(board.dataset.count)
      board.querySelector('.el-board-sub').textContent = selected.length
        ? `${shown} of ${total} promises from the chosen parties. Each row runs from the most to the least realistic.`
        : board.dataset.sub
      board.querySelector('.el-board-none').hidden = shown > 0
    })
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
  partyBtns.forEach(b => b.addEventListener('click', () => {
    selected = toggleIn(selected, b.dataset.party, order)
    applyParties()
  }))
  allBtn.addEventListener('click', () => {
    selected = []
    applyParties()
    partyBtns[0].focus()
  })

  boards.forEach(b => { b.dataset.sub = b.querySelector('.el-board-sub').textContent })
  app.classList.add('is-tabbed')
  controls.hidden = false
  show(tabs[0].dataset.topic)
  applyParties()
}
