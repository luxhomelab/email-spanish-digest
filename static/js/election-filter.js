// Pure filter logic for the election promise explorer
// (templates/partials/article-graphics/spain-election-2026-promises/explorer.html).
// No DOM access, so tests/election-filter.test.js can import it directly;
// static/js/election-explorer.js wires it to the page.

export const RATINGS = ['A', 'B', 'C', 'D', 'V']

/** Lower-case and strip accents, so "autonomo" finds "autónomo". */
export function normalise (s) {
  return String(s || '')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim()
}

export function emptyFilters () {
  return { party: '', topic: '', ratings: [], q: '' }
}

/**
 * Does one item pass the filters?
 * item: { party, topic, f, text } where text is the searchable copy.
 * filters: { party, topic, ratings: string[], q }; empty values match all.
 * Every search word must appear somewhere in the item's text.
 */
export function matches (item, filters) {
  if (filters.party && item.party !== filters.party) return false
  if (filters.topic && item.topic !== filters.topic) return false
  if (filters.ratings.length && !filters.ratings.includes(item.f)) return false
  const words = normalise(filters.q).split(' ').filter(Boolean)
  if (!words.length) return true
  const text = normalise(item.text)
  return words.every(w => text.includes(w))
}

/** Ids of the items that pass, in their original order. */
export function filterIds (items, filters) {
  return items.filter(it => matches(it, filters)).map(it => it.id)
}

/** Add or remove `key` from a selection, keeping the order of `order`. */
export function toggleIn (selected, key, order) {
  const set = new Set(selected)
  if (set.has(key)) set.delete(key)
  else set.add(key)
  return order.filter(k => set.has(k))
}

/** Add or remove one rating from the selection, keeping scale order. */
export function toggleRating (ratings, key) {
  return toggleIn(ratings, key, RATINGS)
}

/** Is a party shown? An empty selection means every party is. */
export function partyShown (party, selected) {
  return !selected.length || selected.includes(party)
}

/**
 * Read filters from a query string such as "?party=pp&topic=housing&rating=A,B&q=rent".
 * Unknown parties, topics and ratings are dropped.
 */
export function filtersFromQuery (search, parties, topics) {
  const p = new URLSearchParams(search || '')
  const party = p.get('party') || ''
  const topic = p.get('topic') || ''
  return {
    party: parties.includes(party) ? party : '',
    topic: topics.includes(topic) ? topic : '',
    ratings: RATINGS.filter(r => (p.get('rating') || '').toUpperCase().split(',').includes(r)),
    q: (p.get('q') || '').slice(0, 80)
  }
}

/** Query string for the filters ("" when nothing is set), for shareable links. */
export function filtersToQuery (filters) {
  const p = new URLSearchParams()
  if (filters.party) p.set('party', filters.party)
  if (filters.topic) p.set('topic', filters.topic)
  if (filters.ratings.length) p.set('rating', filters.ratings.join(','))
  if (filters.q.trim()) p.set('q', filters.q.trim())
  const s = p.toString()
  return s ? `?${s}` : ''
}

export function isEmpty (filters) {
  return !filters.party && !filters.topic && !filters.ratings.length && !filters.q.trim()
}

// Fill a UI string template from the page ("{shown} of {total} promises")
// with values; the partials carry the wording so each language page has its own.
export function fill (template, values) {
  return template.replace(/\{(\w+)\}/g, (m, key) => (key in values ? String(values[key]) : m))
}
