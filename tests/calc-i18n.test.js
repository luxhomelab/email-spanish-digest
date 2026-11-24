import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createI18n, pageLang, loadDict } from '../static/js/calc-i18n.js'
import { personalMinimumText } from '../static/js/autonomo-form.js'

const NBSP = String.fromCharCode(0xa0)

describe('createI18n English', () => {
  const I = createI18n('en')
  it('formats numbers like toLocaleString en-US did', () => {
    assert.equal(I.num(30000), '30,000')
    assert.equal(I.num(1234.5, 2), '1,234.50')
    assert.equal(I.num(5956.65, 0, 3), (5956.65).toLocaleString('en-US'))
  })
  it('formats percents like toFixed() + % did', () => {
    assert.equal(I.pct(0.077, 1), '7.7%')
    assert.equal(I.pctOf(5.112696, 6), '5.112696%')
    assert.equal(I.pct(NaN), '—')
    assert.equal(I.fixed(1.25, 1), (1.25).toFixed(1))
  })
  it('returns the key, filled', () => {
    assert.equal(I.t('Supplier {n}', { n: 2 }), 'Supplier 2')
    assert.equal(I.t('Plain'), 'Plain')
  })
})

describe('createI18n Spanish', () => {
  const I = createI18n('es', { 'Supplier {n}': 'Comercializadora {n}' })
  it('groups thousands with a point, from 1.000', () => {
    assert.equal(I.num(40000), '40.000')
    assert.equal(I.num(1500), '1.500')
    assert.equal(I.num(950), '950')
    assert.equal(I.num(1234.5, 2), '1.234,50')
  })
  it('uses a decimal comma and a no-break space before %', () => {
    assert.equal(I.pct(0.077, 1), `7,7${NBSP}%`)
    assert.equal(I.pctOf(21, 0), `21${NBSP}%`)
    assert.equal(I.fixed(1.25, 1), '1,3')
  })
  it('translates and falls back to the English key', () => {
    assert.equal(I.t('Supplier {n}', { n: 3 }), 'Comercializadora 3')
    assert.equal(I.t('Not in the dictionary {x}', { x: 1 }), 'Not in the dictionary 1')
  })
  it('leaves unknown placeholders alone', () => {
    assert.equal(I.t('{a} and {b}', { a: 1 }), '1 and {b}')
  })
})

describe('pageLang / loadDict', () => {
  it('reads <html lang>', () => {
    assert.equal(pageLang({ documentElement: { lang: 'es' } }), 'es')
    assert.equal(pageLang({ documentElement: { lang: 'es-ES' } }), 'es')
    assert.equal(pageLang({ documentElement: { lang: 'en' } }), 'en')
    assert.equal(pageLang(undefined), 'en')
  })
  it('loads the dictionary only on Spanish pages', async () => {
    let calls = 0
    const loader = async () => { calls += 1; return { default: { a: 'b' } } }
    assert.deepEqual(await loadDict('en', loader), {})
    assert.deepEqual(await loadDict('es', loader), { a: 'b' })
    assert.equal(calls, 1)
  })
})

describe('personalMinimumText in Spanish', () => {
  it('uses the Spanish dictionary and number format', async () => {
    const dict = (await import('../static/js/autonomo-es.js')).default
    const I = createI18n('es', dict)
    const s = personalMinimumText({ personalMinimum: 5550, regionalPersonalMinimum: 5956.65 }, I)
    assert.equal(s, `Tu mínimo personal: 5.550${NBSP}€ (te ahorra entre 1.055 y 2.054${NBSP}€ de impuestos, según tu tramo)`
      + `; el mínimo propio de tu comunidad para la mitad autonómica: 5.956,65${NBSP}€.`)
  })
})

// Every literal t('...') key in a calculator's DOM file has a Spanish entry,
// and the Spanish copy keeps to the house style (no em dashes).
const CALCS = [
  ['electricity.js', 'electricity-es.js'],
  ['net-salary.js', 'net-salary-es.js'],
  ['autonomo.js', 'autonomo-es.js'],
  ['autonomo-form.js', 'autonomo-es.js'],
  ['property-buying-cost.js', 'property-buying-cost-es.js'],
  ['rental-yield.js', 'rental-yield-es.js'],
]
const KEY_RE = /\bt\(\s*(['"])((?:\\.|(?!\1).)*)\1/g

function literalKeys(file) {
  const src = readFileSync(new URL(`../static/js/${file}`, import.meta.url), 'utf8')
  return [...src.matchAll(KEY_RE)].map(m => m[2].replace(/\\(['"])/g, '$1'))
}

describe('Spanish calculator dictionaries', () => {
  for (const [file, dictFile] of CALCS) {
    it(`${dictFile} covers every t() key in ${file}`, async () => {
      const dict = (await import(`../static/js/${dictFile}`)).default
      const keys = literalKeys(file)
      assert.ok(keys.length > 0, file)
      const missing = keys.filter(k => !Object.prototype.hasOwnProperty.call(dict, k))
      assert.deepEqual(missing, [])
    })
    it(`${dictFile} has no em dashes and keeps every placeholder`, async () => {
      const dict = (await import(`../static/js/${dictFile}`)).default
      for (const [en, es] of Object.entries(dict)) {
        assert.ok(!es.includes('—'), `${dictFile}: ${es}`)
        const vars = s => (s.match(/\{\w+\}/g) || []).sort()
        assert.deepEqual(vars(es), vars(en), `${dictFile}: ${en}`)
      }
    })
  }
  it('covers the foral detail lines net-salary.js translates at render time', async () => {
    const dict = (await import('../static/js/net-salary-es.js')).default
    const src = readFileSync(new URL('../static/js/net-salary-foral.js', import.meta.url), 'utf8')
    // Labels and notes are the string literals inside the `lines: [...]` arrays
    // (state values such as 'married' are single lowercase words and are skipped).
    const blocks = [...src.matchAll(/lines: \[([\s\S]*?)\n {4}\],/g)].map(m => m[1])
    assert.ok(blocks.length >= 2, 'foral lines blocks')
    const strings = blocks.flatMap(b => [...b.matchAll(/'([^'\r\n]*)'/g)].map(m => m[1])).filter(s => /\s/.test(s))
    assert.ok(strings.length > 15, String(strings.length))
    const missing = strings.filter(s => !Object.prototype.hasOwnProperty.call(dict, s))
    assert.deepEqual(missing, [])
  })
})
