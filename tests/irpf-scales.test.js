import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import { calcIrpfRegional, calcIrpfState, IRPF_REGIONAL_BRACKETS } from '../static/js/autonomo-calc.js'

const near = (a, b, eps = 0.02) => assert.ok(Math.abs(a - b) <= eps, `${a} != ${b}`)

// Oracle: "Cuota íntegra" column of each regional scale in the AEAT Manual práctico
// Renta 2025, cap. 15 "Gravamen autonómico" (pages updated 17/03/2026). The tax on a
// base equal to a bracket's lower bound must equal the printed accumulated cuota.
// Valencia is excluded: it runs the 2026 deflated scale (Ley 5/2026), not the 2025 one.
const AEAT_CUOTAS = {
  andalucia: [[13000, 1235], [21100, 2207], [35200, 4322], [60000, 8910]],
  aragon: [[13072.5, 1241.89], [21210, 2218.39], [36960, 4580.89], [52500, 7455.79],
    [60000, 8993.29], [80000, 13593.29], [90000, 15993.29], [130000, 25993.29]],
  asturias: [[12450, 1120.5], [17707.2, 1751.36], [33007.2, 3893.36], [53407.2, 7810.16],
    [70000, 11377.62], [90000, 15877.62], [175000, 37127.62]],
  baleares: [[10000, 900], [18000, 1800], [30000, 3510], [48000, 6660], [70000, 10840],
    [90000, 15190], [120000, 22015], [175000, 35077.5]],
  canarias: [[13748, 1237.32], [19422, 1889.83], [35924, 4200.11], [57566, 8203.88],
    [93268, 16593.85], [123745, 24213.1]],
  cantabria: [[13000, 1105], [21000, 1985], [35200, 4044], [60000, 8508], [90000, 15258]],
  castilla_la_mancha: [[12450, 1182.75], [20200, 2112.75], [35200, 4362.75], [60000, 8950.75]],
  castilla_leon: [[12450, 1120.5], [20200, 2050.5], [35200, 4150.5], [53407.2, 7518.83]],
  catalunya: [[12500, 1187.5], [22000, 2375], [33000, 4135], [53000, 7935], [90000, 15890],
    [120000, 22940], [175000, 36415]],
  extremadura: [[12450, 996], [20200, 1771], [24200, 2411], [35200, 4336], [60000, 9544],
    [80200, 14291], [99200, 18851], [120200, 23996]],
  galicia: [[12985.35, 1168.68], [21068.6, 2110.38], [35200, 4215.96], [60000, 8779.16]],
  madrid: [[13362.22, 1135.79], [19004.63, 1739.53], [35425.68, 3841.42], [57320.4, 7651.1]],
  murcia: [[12450, 1182.75], [20200, 2050.75], [34000, 3886.15], [60000, 8540.15]],
  la_rioja: [[12450, 996], [20200, 1817.5], [35200, 3857.5], [40000, 4711.9], [50000, 6541.9],
    [60000, 8441.9], [120000, 23141.9]],
}

describe('regional IRPF scales match the AEAT Manual Renta 2025 tables', () => {
  for (const [region, rows] of Object.entries(AEAT_CUOTAS)) {
    it(region, () => {
      for (const [base, cuota] of rows) near(calcIrpfRegional(base, region), cuota)
    })
  }

  it('Ceuta and Melilla use the art. 65 LIRPF scale (same as Castilla-La Mancha)', () => {
    for (const r of ['ceuta', 'melilla']) {
      for (const [base, cuota] of AEAT_CUOTAS.castilla_la_mancha) near(calcIrpfRegional(base, r), cuota)
    }
  })

  it('exports the regional table', () => {
    assert.ok(Array.isArray(IRPF_REGIONAL_BRACKETS.madrid))
  })

  it('state scale: 20.440 base gives 2.148,75 (tecalculo 24k Madrid oracle)', () => {
    near(calcIrpfState(20440), 2148.75)
  })
})
