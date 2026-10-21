import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { buildGrid, figuresFor } from '../scripts/net-salary-grid.mjs'
import { calculateNetSalary } from '../static/js/net-salary-calc.js'
import { DEFAULTS } from '../static/js/net-salary-form.js'

const config = JSON.parse(readFileSync(new URL('../data/net-salary-pages.json', import.meta.url), 'utf8'))
const grid = buildGrid(config)

const finiteDeep = (v, path = '') => {
  if (typeof v === 'number') assert.ok(Number.isFinite(v), `${path} is not finite`)
  else if (v && typeof v === 'object') for (const [k, x] of Object.entries(v)) finiteDeep(x, `${path}.${k}`)
}

describe('net salary page grid', () => {
  it('30000 matches calculateNetSalary with the default profile', () => {
    const calc = calculateNetSalary({ ...DEFAULTS, gross: 30000 })
    const e = grid.annual.find(a => a.amount === 30000)
    assert.equal(e.p12.netAnnual, calc.netAnnual)
    assert.equal(e.p12.annualTaxNet, calc.annualTaxNet)
    assert.equal(e.p12.payslipRegular, calc.payslip.regular)
    assert.equal(e.p12.ssTotal, calc.ss.total)
    assert.equal(e.p12.irpfTotal, calc.irpf.total)
    assert.equal(e.p12.employerCost, calc.employer.totalCost)
  })

  it('compares all 19 regions, best first, Madrid included', () => {
    const { regions } = grid.annual.find(a => a.amount === 30000)
    assert.equal(regions.length, 19)
    assert.ok(regions.some(r => r.region === 'madrid'))
    for (let i = 1; i < regions.length; i++) assert.ok(regions[i - 1].annualTaxNet >= regions[i].annualTaxNet)
  })

  it('monthly 2000 means 24000 gross a year (12 payments) and 28000 on 14', () => {
    const m = grid.monthly.find(x => x.amount === 2000)
    assert.equal(m.x12.gross, 24000)
    assert.equal(m.x12.p12.gross, 24000)
    assert.equal(m.x14.gross, 28000)
    assert.equal(m.x14.p14.payments, '14')
    assert.match(m.query, /ns_p=m/)
  })

  it('14 payments keep the yearly net and add extra payslips', () => {
    const e = figuresFor(30000, '14')
    assert.equal(e.netAnnual, figuresFor(30000, '12').netAnnual)
    assert.ok(e.payslipExtra > e.payslipRegular)
  })

  it('every amount produces finite numbers', () => {
    assert.equal(grid.annual.length, config.annual.length)
    assert.equal(grid.monthly.length, config.monthly.length)
    finiteDeep(grid)
  })
})
