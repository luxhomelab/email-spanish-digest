import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import {
  normalise,
  emptyFilters,
  matches,
  filterIds,
  toggleRating,
  filtersFromQuery,
  filtersToQuery,
  isEmpty
} from '../static/js/election-filter.js'

const items = [
  { id: 'pp-1', party: 'pp', topic: 'housing', f: 'A', text: 'Repeal the Housing Law (Ley de Vivienda)' },
  { id: 'podemos-21', party: 'podemos', topic: 'taxes', f: 'A', text: 'Abolish the Beckham law' },
  { id: 'vox-29', party: 'vox', topic: 'immigration', f: 'B', text: 'Abolish arraigo' },
  { id: 'sumar-1', party: 'sumar', topic: 'housing', f: 'D', text: 'Expropriate homes from large landlords' },
  { id: 'pp-26', party: 'pp', topic: 'labour', f: 'B', text: 'No fees for new autónomos' }
]

describe('normalise', () => {
  it('strips accents, lower-cases and squeezes spaces', () => {
    assert.equal(normalise('  Autónomos   ÁRRAIGO '), 'autonomos arraigo')
  })
  it('treats null as empty', () => {
    assert.equal(normalise(null), '')
  })
})

describe('matches / filterIds', () => {
  it('empty filters keep everything in order', () => {
    assert.deepEqual(filterIds(items, emptyFilters()), items.map(i => i.id))
  })
  it('filters by party, topic and ratings together', () => {
    const f = { ...emptyFilters(), party: 'pp', ratings: ['B'] }
    assert.deepEqual(filterIds(items, f), ['pp-26'])
    assert.deepEqual(filterIds(items, { ...emptyFilters(), topic: 'housing' }), ['pp-1', 'sumar-1'])
  })
  it('search ignores accents and needs every word', () => {
    assert.ok(matches(items[4], { ...emptyFilters(), q: 'AUTONOMOS fees' }))
    assert.ok(!matches(items[4], { ...emptyFilters(), q: 'autonomos pension' }))
    assert.deepEqual(filterIds(items, { ...emptyFilters(), q: 'abolish' }), ['podemos-21', 'vox-29'])
  })
  it('returns nothing when no item matches', () => {
    assert.deepEqual(filterIds(items, { ...emptyFilters(), party: 'bng' }), [])
  })
})

describe('toggleRating', () => {
  it('adds in scale order and removes', () => {
    assert.deepEqual(toggleRating(['C'], 'A'), ['A', 'C'])
    assert.deepEqual(toggleRating(['A', 'C'], 'A'), ['C'])
  })
})

describe('query string round trip', () => {
  const parties = ['pp', 'psoe']
  const topics = ['housing', 'taxes']
  it('reads known values and drops unknown ones', () => {
    assert.deepEqual(
      filtersFromQuery('?party=pp&topic=nope&rating=b,a,x&q=rent', parties, topics),
      { party: 'pp', topic: '', ratings: ['A', 'B'], q: 'rent' }
    )
  })
  it('writes only what is set', () => {
    assert.equal(filtersToQuery(emptyFilters()), '')
    const f = { party: 'psoe', topic: 'taxes', ratings: ['A', 'B'], q: ' tax ' }
    assert.equal(filtersToQuery(f), '?party=psoe&topic=taxes&rating=A%2CB&q=tax')
    assert.deepEqual(filtersFromQuery(filtersToQuery(f), parties, topics), { ...f, q: 'tax' })
  })
  it('isEmpty ignores whitespace-only search', () => {
    assert.ok(isEmpty({ ...emptyFilters(), q: '  ' }))
    assert.ok(!isEmpty({ ...emptyFilters(), topic: 'taxes' }))
  })
})

describe('party selection', () => {
  it('toggleIn keeps the given order', async () => {
    const { toggleIn } = await import('../static/js/election-filter.js')
    const order = ['pp', 'psoe', 'vox']
    assert.deepEqual(toggleIn(['vox'], 'pp', order), ['pp', 'vox'])
    assert.deepEqual(toggleIn(['pp', 'vox'], 'vox', order), ['pp'])
  })
  it('partyShown: empty selection shows every party', async () => {
    const { partyShown } = await import('../static/js/election-filter.js')
    assert.ok(partyShown('bng', []))
    assert.ok(partyShown('pp', ['pp', 'psoe']))
    assert.ok(!partyShown('vox', ['pp', 'psoe']))
  })
})
