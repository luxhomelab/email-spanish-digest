// Pure quiz logic (no DOM) — testable with node:test.
// The question pool comes from data/quizzes/<slug>.json, embedded into
// templates/quiz.html at build time as <script id="quiz-data" type="application/json">.

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
// double opt-in click. A saved quiz score alone must never unlock the result
// — score ≠ consent.
export function markQuizSubscribed(storage, slug, email = '') {
  try {
    storage.setItem(subscribeKey(slug), JSON.stringify({ subscribed: true, email, at: new Date().toISOString() }))
    return true
  } catch {
    return false
  }
}

export function isQuizSubscribed(storage, slug) {
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
// "I got 3-4/10 on AI or Real? — ..." → "I scored 4/10 on AI or Real? — ..."
export function personalShareText(result, score, total = 10) {
  const base = result && result.shareText
    ? result.shareText
    : 'I took the AI or Real? quiz — telling real Spanish news from AI fakes — Spanified'
  return base.replace(/I got \d+-\d+\/\d+/, `I scored ${score}/${total}`)
}

// Longer share text for networks without X's 280-char limit
// (Facebook, WhatsApp, Telegram): exact-score line + first paragraph
// of the persona roast. X keeps personalShareText().
export function personalLongShareText(result, score, total = 10) {
  const short = personalShareText(result, score, total)
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
