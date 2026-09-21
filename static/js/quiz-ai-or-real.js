import {
  pickQuestions,
  scoreAnswers,
  resultForScore,
  resultBySlug,
  personalShareText,
  personalLongShareText,
  quizResultUrl,
  saveQuizResult,
  loadQuizResult,
} from './quiz-logic.js'

const $ = id => document.getElementById(id)
const TOTAL = 10

function track(name, params = {}) {
  try {
    if (typeof window.gtag === 'function') window.gtag('event', name, params)
  } catch { /* analytics optional */ }
}

function syncShareLinks(text, url, longText) {
  const wrap = document.querySelector('.quiz-share .share-wrap')
  if (!wrap) return
  const pageUrl = url || window.location.href
  const u = encodeURIComponent(pageUrl)
  const t = encodeURIComponent(text)
  // Networks without X's 280-char limit get the longer roast text.
  const tl = encodeURIComponent(longText || text)
  const set = (sel, href) => {
    const a = wrap.querySelector(sel)
    if (a) a.href = href
  }
  set('a[href*="x.com/intent"]', `https://x.com/intent/tweet?text=${t}&url=${u}`)
  // Facebook ignores pre-filled text — it scrapes the link's OG tags instead.
  set('a[href*="facebook.com/sharer"]', `https://www.facebook.com/sharer/sharer.php?u=${u}`)
  set('a[href*="t.me/share"]', `https://t.me/share/url?url=${u}&text=${tl}`)
  set('a[href*="wa.me"]', `https://wa.me/?text=${tl}%20${u}`)
  const copy = wrap.querySelector('.share-copy')
  if (copy) copy.dataset.url = pageUrl
}

function wireShareMenu() {
  const wrap = document.querySelector('.quiz-share .share-wrap')
  if (!wrap) return
  const toggleBtn = wrap.querySelector('.share-toggle')
  const menu = wrap.querySelector('.share-menu')
  if (!toggleBtn || !menu) return
  const close = () => {
    menu.hidden = true
    toggleBtn.setAttribute('aria-expanded', 'false')
  }
  toggleBtn.addEventListener('click', e => {
    e.stopPropagation()
    const willOpen = menu.hidden
    close()
    if (willOpen) {
      menu.hidden = false
      toggleBtn.setAttribute('aria-expanded', 'true')
    }
  })
  document.addEventListener('click', e => {
    if (!e.target.closest('.quiz-share .share-wrap')) close()
  })
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') close()
  })
  wrap.addEventListener('click', e => {
    const btn = e.target.closest('.share-copy')
    if (!btn) return
    const label = btn.querySelector('span')
    const done = () => {
      label.textContent = 'Copied!'
      setTimeout(() => { label.textContent = 'Copy link' }, 1500)
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(btn.dataset.url).then(done, done)
    } else {
      done()
    }
  })
}

function init() {
  const dataEl = $('quiz-data')
  if (!dataEl) return
  const { slug, questions: pool, results } = JSON.parse(dataEl.textContent)
  const questions = pickQuestions(pool, TOTAL)
  const answers = []
  let step = 0
  let unlocked = false

  // Hook screen: show questions only after Start.
  const startBtn = $('quiz-start')
  const hook = $('quiz-hook')
  const progressTrack = document.querySelector('.quiz-progress-track')
  if (startBtn && hook) {
    // Returning player? Show their last score and offer a rematch.
    try {
      const prev = loadQuizResult(window.localStorage, slug)
      const persona = prev && prev.resultSlug ? resultBySlug(results, prev.resultSlug) : null
      if (prev && Number.isInteger(prev.score) && persona) {
        const last = $('quiz-last')
        if (last) {
          last.textContent = `Last time: ${prev.score}/${TOTAL} — ${persona.title}`
          last.hidden = false
        }
        startBtn.textContent = 'Play again'
      }
    } catch { /* first visit: keep default hook copy */ }
    startBtn.addEventListener('click', () => {
      hook.hidden = true
      $('quiz-play').hidden = false
      if (progressTrack) progressTrack.hidden = false
      track('quiz_start', { quiz: slug })
      renderStep()
    })
  } else {
    // No hook (fallback): start immediately.
    $('quiz-play').hidden = false
    if (progressTrack) progressTrack.hidden = false
    track('quiz_start', { quiz: slug })
    renderStep()
  }

  $('quiz-real').addEventListener('click', () => answer(true))
  $('quiz-fake').addEventListener('click', () => answer(false))
  $('quiz-next').addEventListener('click', next)

  const skip = $('quiz-skip')
  if (skip) skip.addEventListener('click', () => {
    track('quiz_skip', { quiz: slug })
    unlock(true)
  })

  window.addEventListener('message', e => {
    if (e.data === 'quiz_subscribed') unlock(false)
  })

  // Fallback path: the subscribed-snippet "Reveal my result" button links
  // here with #result when postMessage is blocked. finish() already saved
  // the score pre-gate, so reveal the full result without replaying.
  try {
    if (window.location.hash === '#result') {
      const saved = loadQuizResult(window.localStorage, slug)
      if (saved && Number.isInteger(saved.score) && saved.score >= 0 && saved.score <= TOTAL
          && resultForScore(results, saved.score)) {
        if (hook) hook.hidden = true
        $('quiz-play').hidden = true
        if (progressTrack) progressTrack.hidden = false
        $('quiz-gate').hidden = false
        $('quiz-score-num').textContent = saved.score
        $('quiz-score-line').textContent = `You scored ${saved.score}/${TOTAL}`
        unlock(false)
      }
    }
  } catch { /* corrupted storage — fall through to the normal hook flow */ }

  function renderStep() {
    const q = questions[step]
    $('quiz-step').textContent = `Story ${step + 1} of ${TOTAL}`
    $('quiz-progress').style.width = `${(step / TOTAL) * 100}%`
    $('quiz-headline').textContent = q.headline
    $('quiz-summary').textContent = q.summary
    const fb = $('quiz-feedback')
    fb.hidden = true
    fb.classList.remove('quiz-fb-bad')
    for (const id of ['quiz-real', 'quiz-fake']) {
      const btn = $(id)
      btn.disabled = false
      btn.classList.remove('quiz-picked', 'quiz-correct', 'quiz-wrong')
    }
    $('quiz-choices').hidden = false
    $('quiz-next-wrap').hidden = true
  }

  function answer(guessIsReal) {
    const q = questions[step]
    const correct = guessIsReal === q.isReal
    answers[step] = guessIsReal
    track('quiz_step', { quiz: slug, step: step + 1, correct })
    const fb = $('quiz-feedback')
    fb.hidden = false
    fb.classList.toggle('quiz-fb-bad', !correct)
    const verdict = fb.querySelector('.quiz-verdict')
    verdict.textContent = correct
      ? 'Correct!'
      : (q.isReal ? 'Wrong — that one is REAL.' : 'Wrong — that one is FAKE.')
    verdict.classList.toggle('quiz-bad', !correct)
    fb.querySelector('.quiz-explain').textContent = q.explanation
    const src = fb.querySelector('.quiz-source')
    if (q.isReal && q.source) {
      src.hidden = false
      src.textContent = 'Source: '
      if (q.source_url) {
        const a = document.createElement('a')
        a.href = q.source_url
        a.target = '_blank'
        a.rel = 'noopener'
        a.textContent = q.source
        src.appendChild(a)
      } else {
        src.appendChild(document.createTextNode(q.source))
      }
    } else if (!q.isReal) {
      src.hidden = false
      src.textContent = 'Invented by Spanified — no source, just vibes.'
    } else {
      src.hidden = true
    }
    // Highlight: user's pick + the right answer; lock both buttons.
    const realBtn = $('quiz-real')
    const fakeBtn = $('quiz-fake')
    realBtn.disabled = true
    fakeBtn.disabled = true
    const picked = guessIsReal ? realBtn : fakeBtn
    const right = q.isReal ? realBtn : fakeBtn
    picked.classList.add('quiz-picked')
    right.classList.add('quiz-correct')
    if (!correct) picked.classList.add('quiz-wrong')
    $('quiz-choices').hidden = false
    $('quiz-next-wrap').hidden = false
    $('quiz-next').textContent = step === TOTAL - 1 ? 'See my result' : 'Next story'
  }

  function next() {
    if (step < TOTAL - 1) {
      step++
      renderStep()
    } else {
      finish()
    }
  }

  function finish() {
    const score = scoreAnswers(questions, answers)
    const result = resultForScore(results, score)
    track('quiz_finish', { quiz: slug, score })
    // Preserve a previous subscription: an already-subscribed player
    // retaking the quiz must never see the gate form (or the skip) again.
    const prev = loadQuizResult(window.localStorage, slug)
    const subscribed = !!(prev && prev.subscribed)
    try {
      saveQuizResult(window.localStorage, slug, { score, slug, resultSlug: result.slug, ...(subscribed ? { subscribed: true } : {}) })
    } catch { /* private mode — result page will show same-device hint */ }
    $('quiz-play').hidden = true
    $('quiz-gate').hidden = false
    $('quiz-progress').style.width = '100%'
    // Persona title stays hidden behind the blur — only the score shows yet.
    $('quiz-score-num').textContent = score
    $('quiz-score-line').textContent = `You scored ${score}/${TOTAL}`
    if (subscribed) {
      // No gate, no skip, no subscribe event — straight to the full result.
      unlock(true)
      return
    }
    // Lazy-load Brevo form only at the gate (keeps landing fast).
    const frame = $('quiz-brevo-frame')
    if (frame && !frame.src && frame.dataset.src) frame.src = frame.dataset.src
  }

  function unlock(skipped) {
    if (unlocked) return
    unlocked = true
    // Re-read score/result (source of truth = localStorage).
    const saved = loadQuizResult(window.localStorage, slug)
    const score = saved ? saved.score : scoreAnswers(questions, answers)
    const result = resultForScore(results, score)
    if (!skipped) {
      try {
        saveQuizResult(window.localStorage, slug, { score, slug, resultSlug: result.slug, subscribed: true })
      } catch { /* ignore */ }
      track('quiz_subscribe', { quiz: slug, score })
    }
    // Gate resolved (subscribed or skipped) — the teaser box is pointless now.
    $('quiz-blur').hidden = true
    $('quiz-gate-form').hidden = true
    $('quiz-result-full').hidden = false
    $('quiz-result-title').textContent = result.title
    const rt = $('quiz-result-text')
    rt.innerHTML = ''
    String(result.text).split(/\n\n+/).forEach(p => {
      const pe = document.createElement('p')
      pe.textContent = p
      rt.appendChild(pe)
    })
    $('quiz-progress').style.width = '100%'
    // Personal share: exact score in text + result encoded in the URL.
    // X gets the short line; FB/TG/WA get the longer roast text.
    const base = `${window.location.origin}${window.location.pathname}`
    syncShareLinks(
      personalShareText(result, score, TOTAL),
      quizResultUrl(base, result.slug, score),
      personalLongShareText(result, score, TOTAL),
    )
  }

  wireShareMenu()
  syncShareLinks('AI or Real? — Can you spot fake Spain news? — Spanified')
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init)
} else {
  init()
}
