// Pure quiz logic (no DOM) — testable with node:test.
// The question pool comes from data/quizzes/<slug>.json, embedded into
// templates/quiz.html at build time as <script id="quiz-data" type="application/json">.

import { markSubscribed, isSubscribed } from './subscription-store.js'

// UI strings the quiz scripts build at runtime, per page language
// (<html lang>: "en" on /quiz/, "es" on /es/quiz/). Quiz content (questions,
// personas, share lines, button labels) comes from the quiz JSON instead.
// {name} placeholders are filled by fillText().
export const QUIZ_STRINGS = {
  en: {
    realLabel: 'Real — this happened',
    fakeLabel: 'Fake — AI slop',
    lastTime: 'Last time: <strong>{score}/{total}</strong> — {title}',
    playAgain: 'Play again',
    hint: 'Make your call. The verdict and the source land here.',
    stampReal: 'Real',
    stampFake: 'Fake',
    right: 'You got it.',
    wrongReal: 'Not quite. This one is real.',
    wrongFake: 'Not quite. This one is fake.',
    source: 'Source: ',
    invented: 'Invented by Spanified. No source, just vibes.',
    next: 'Next question',
    seeResult: 'See my result',
    step: 'Story {n} of {total}',
    scoreLine: 'You scored {score} out of {total}',
    copied: 'Copied!',
    pageShare: '{title} — Spanified',
    defaultShare: 'I took the Real or AI? quiz — telling real Spanish news from AI fakes — Spanified',
  },
  es: {
    realLabel: 'Real: pasó de verdad',
    fakeLabel: 'Falso: invento de IA',
    lastTime: 'La última vez: <strong>{score}/{total}</strong>, {title}',
    playAgain: 'Jugar otra vez',
    hint: 'Elige una opción. Aquí aparecerán la respuesta y la fuente.',
    stampReal: 'Real',
    stampFake: 'Falso',
    right: '¡Acertaste!',
    wrongReal: 'Pues no. Esta es real.',
    wrongFake: 'Pues no. Esta es falsa.',
    source: 'Fuente: ',
    invented: 'Inventado por Spanified. Sin fuente, solo imaginación.',
    next: 'Siguiente pregunta',
    seeResult: 'Ver mi resultado',
    step: 'Pregunta {n} de {total}',
    scoreLine: 'Has sacado {score} de {total}',
    copied: '¡Copiado!',
    pageShare: '{title} | Spanified',
    defaultShare: 'He hecho el test ¿Real o IA? de Spanified, para distinguir noticias reales de España de bulos de IA',
  },
}

// Strings for a page language ("es", "es-ES", "en"...): unknown languages
// and missing keys fall back to English.
export function quizStrings(lang) {
  const base = String(lang || 'en').toLowerCase().split('-')[0]
  return { ...QUIZ_STRINGS.en, ...(QUIZ_STRINGS[base] || {}) }
}

// fillText('Story {n} of {total}', { n: 3, total: 10 }) -> 'Story 3 of 10'.
// Unknown placeholders stay as they are.
export function fillText(template, vars = {}) {
  return String(template).replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m))
}

export function storageKey(slug) {
  return `spanified_quiz_${slug}`
}

function shuffled(arr, rand = Math.random) {
  const a = arr.slice()
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1))
    ;[a[i], a[j]] = [a[j], a[i]]
  }
  return a
}

// Pick n questions, balanced real/fake so the quiz can't be gamed
// (half of each; falls back to whatever exists if a pool is short).
export function pickQuestions(pool, n = 10, rand = Math.random) {
  const reals = shuffled(pool.filter(q => q.isReal), rand)
  const fakes = shuffled(pool.filter(q => !q.isReal), rand)
  const half = Math.floor(n / 2)
  const picked = [...reals.slice(0, half), ...fakes.slice(0, n - half)]
  // Top up from leftovers if one side was short.
  if (picked.length < n) {
    const rest = shuffled(
      pool.filter(q => !picked.includes(q)),
      rand,
    )
    picked.push(...rest.slice(0, n - picked.length))
  }
  return shuffled(picked, rand)
}

// answers: array of booleans — true = user guessed "real".
export function scoreAnswers(questions, answers) {
  let score = 0
  for (let i = 0; i < questions.length; i++) {
    if (answers[i] === questions[i].isReal) score++
  }
  return score
}

export function resultForScore(results, score) {
  for (const r of results) {
    if (score >= r.min && score <= r.max) return r
  }
  return results[results.length - 1]
}

export function saveQuizResult(storage, slug, data) {
  try {
    storage.setItem(storageKey(slug), JSON.stringify(data))
    return true
  } catch {
    return false
  }
}

export function loadQuizResult(storage, slug) {
  try {
    const raw = storage.getItem(storageKey(slug))
    if (!raw) return null
    return JSON.parse(raw)
  } catch {
    return null
  }
}

export function subscribeKey(slug) {
  return `spanified_subscribed_${slug}`
}

// Separate opt-in record, written ONLY by the quiz-success page after the
// double opt-in click (and now also by any successful subscribe form,
// via the shared subscription store below). A saved quiz score alone must
// never unlock the result — score ≠ consent.
export function markQuizSubscribed(storage, slug, email = '') {
  void slug
  return markSubscribed(storage, email)
}

export function isQuizSubscribed(storage, slug) {
  if (isSubscribed(storage)) return true
  // Legacy per-quiz record (pre-site-wide-flag).
  try {
    const raw = storage.getItem(subscribeKey(slug))
    if (!raw) return false
    const data = JSON.parse(raw)
    return !!(data && data.subscribed)
  } catch {
    return false
  }
}

export function resultBySlug(results, slug) {
  return (results || []).find(r => r.slug === slug) || null
}

// Personalize the share text with the exact score:
// "I got 3-4/10 on Real or AI? — ..." → "I scored 4/10 on Real or AI? — ..."
// Any other language just swaps the band for the score:
// "He sacado 3-4/10 ..." → "He sacado 4/10 ...". `strings` (quizStrings())
// supplies the fallback line when the result has no shareText.
export function personalShareText(result, score, total = 10, strings = QUIZ_STRINGS.en) {
  const base = result && result.shareText ? result.shareText : strings.defaultShare
  const exact = `${score}/${total}`
  return /I got \d+-\d+\/\d+/.test(base)
    ? base.replace(/I got \d+-\d+\/\d+/, `I scored ${exact}`)
    : base.replace(/\b\d+-\d+\/\d+/, exact)
}

// Longer share text for networks without X's 280-char limit
// (Facebook, WhatsApp, Telegram): exact-score line + first paragraph
// of the persona roast. X keeps personalShareText().
export function personalLongShareText(result, score, total = 10, strings = QUIZ_STRINGS.en) {
  const short = personalShareText(result, score, total, strings)
  const first = String((result && result.text) || '').split(/\n\n+/)[0].trim()
  return first ? `${short}\n\n${first}` : short
}
// Shareable URL that points to the per-persona static result page.
// ?score=<n> is appended so the result page can show "Your friend scored X".
// Keeps a trailing ".html" (local file serving) or clean URLs (production).
export function quizResultUrl(baseUrl, resultSlug, score) {
  const clean = String(baseUrl).split('#')[0].split('?')[0].replace(/\/$/, '')
  const pageUrl = /\.html$/i.test(clean)
    ? clean.replace(/\.html$/i, `-result-${resultSlug}.html`)
    : `${clean}-result-${resultSlug}`
  return score != null ? `${pageUrl}?score=${encodeURIComponent(score)}` : pageUrl
}
