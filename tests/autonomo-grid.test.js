import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { buildGrid, figuresFor, requiredRevenue, REGIONS, STEP } from '../scripts/autonomo-grid.mjs'
import { calculateAutonomo } from '../static/js/autonomo-calc.js'
import { DEFAULTS } from '../static/js/autonomo-form.js'

const config = JSON.parse(readFileSync(new URL('../data/autonomo-pages.json', import.meta.url), 'utf8'))
const grid = buildGrid(config)

const finiteDeep = (v, path = '') => {
  if (typeof v === 'number') assert.ok(Number.isFinite(v), `${path} is not finite`)
  else if (v && typeof v === 'object') for (const [k, x] of Object.entries(v)) finiteDeep(x, `${path}.${k}`)
}

describe('autonomo page grid', () => {
  it('30000 matches calculateAutonomo with the default profile', () => {
    const calc = calculateAutonomo({ ...DEFAULTS, annualNetRevenue: 30000 })
    const e = grid.revenue.find(a => a.amount === 30000).established
    assert.equal(e.netYear, calc.netTakeHome)
    assert.equal(e.netMonth, calc.netTakeHomeMonthly)
    assert.equal(e.annualSS, calc.annualSSTotal)
    assert.equal(e.irpfTotal, calc.irpfTotal)
  })

  it('tarifa plana pays 88.65 a month (€80 + MEI) and keeps more', () => {
    const e = grid.revenue.find(a => a.amount === 30000)
    assert.equal(e.tarifaPlana.monthlyQuota, 88.65)
    assert.equal(e.tarifaPlana.isTarifaPlana, true)
    assert.ok(e.tarifaPlana.netYear > e.established.netYear)
  })

  it('compares the 17 supported regions, best first, Madrid included, no foral regions', () => {
    const { regions } = grid.revenue.find(a => a.amount === 30000)
    assert.equal(regions.length, 17)
    assert.equal(REGIONS.length, 17)
    assert.ok(regions.some(r => r.region === 'madrid'))
    assert.ok(!regions.some(r => r.region === 'navarra' || r.region === 'pais_vasco'))
    for (let i = 1; i < regions.length; i++) assert.ok(regions[i - 1].netYear >= regions[i].netYear)
  })

  it('required revenue reaches the target and the same revenue minus one step does not', () => {
    for (const m of grid.monthly) {
      assert.ok(figuresFor(m.needed).netMonth >= m.amount, `${m.amount} not reached`)
      assert.ok(figuresFor(m.needed - STEP).netMonth < m.amount, `${m.amount} not minimal`)
      assert.equal(m.amount <= m.established.netMonth, true)
    }
  })

  it('required revenue is safe: every higher revenue also keeps the target', () => {
    const needed = requiredRevenue(2000)
    for (let rev = needed; rev <= needed + 20000; rev += STEP) assert.ok(figuresFor(rev).netMonth >= 2000, `dips at ${rev}`)
  })

  it('tarifa plana needs less revenue than an established autonomo', () => {
    for (const m of grid.monthly) assert.ok(m.neededTarifaPlana < m.needed)
  })

  it('every amount produces finite numbers', () => {
    assert.equal(grid.revenue.length, config.revenue.length)
    assert.equal(grid.monthly.length, config.monthly.length)
    finiteDeep(grid)
  })
})
