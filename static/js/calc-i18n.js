// Calculator UI language: strings and number formats for the DOM wiring files.
//
// The page language comes from <html lang> (build.py renders the /es/
// calculator pages with page_lang="es"). Strings are gettext-style: the
// English text is the key, and a per-calculator Spanish dictionary
// (static/js/<calc>-es.js, loaded only on Spanish pages) maps it. A missing
// key falls back to English. Pure module: no DOM access unless pageLang()
// is called, so node tests can import it.

const NBSP = String.fromCharCode(0xa0) // no-break space

/** 'es' when the document is Spanish, else 'en'. */
export function pageLang(doc = globalThis.document) {
  const lang = (doc && doc.documentElement && doc.documentElement.lang) || 'en'
  return lang.toLowerCase().startsWith('es') ? 'es' : 'en'
}

/** The Spanish dictionary module for this page, or {} on English pages. */
export async function loadDict(lang, loader) {
  if (lang !== 'es') return {}
  const mod = await loader()
  return mod.default || {}
}

/**
 * t(key, vars), number and currency formatting for one language.
 * English output matches what the calculators printed before i18n
 * (en-US grouping); Spanish uses es-ES with grouping from 1.000, a decimal
 * comma and a non-breaking space before € and %.
 */
export function createI18n(lang = 'en', dict = {}) {
  const es = lang === 'es'
  const locale = es ? 'es-ES' : 'en-US'
  const formatters = new Map()

  function t(key, vars) {
    let s = es && Object.prototype.hasOwnProperty.call(dict, key) ? dict[key] : key
    if (vars) s = s.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m))
    return s
  }

  /** Plain number with fixed decimals: 1234.5 -> "1,234.50" / "1.234,50". */
  function num(n, minDigits = 0, maxDigits = minDigits) {
    const key = `${minDigits}:${maxDigits}`
    let f = formatters.get(key)
    if (!f) {
      f = new Intl.NumberFormat(locale, {
        minimumFractionDigits: minDigits,
        maximumFractionDigits: maxDigits,
        useGrouping: es ? 'always' : true,
      })
      formatters.set(key, f)
    }
    return f.format(n)
  }

  /** Percent of a fraction: 0.077 -> "7.7%" / "7,7 %". */
  function pct(fraction, digits = 1) {
    if (!Number.isFinite(fraction)) return '—'
    return pctOf(fraction * 100, digits)
  }

  /** Percent of a number already in percent: 7.7 -> "7.7%" / "7,7 %". */
  function pctOf(value, digits = 1) {
    if (!Number.isFinite(value)) return '—'
    return es ? `${num(value, digits)}${NBSP}%` : `${value.toFixed(digits)}%`
  }

  /** Decimal with a fixed number of digits, as toFixed() but localised. */
  function fixed(n, digits) {
    return es ? num(n, digits) : Number(n).toFixed(digits)
  }

  return { lang, locale, es, t, num, pct, pctOf, fixed, NBSP }
}
