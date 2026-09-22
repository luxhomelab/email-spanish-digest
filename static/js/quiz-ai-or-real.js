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
  // Facebook scrapes the link's OG tags; quote sometimes surfaces as pre-filled text.
  set('a[href*="facebook.com/sharer"]', `https://www.facebook.com/sharer/sharer.php?u=${u}&quote=${tl}`)
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
  let questions = pickQuestions(pool, TOTAL)
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
          last.innerHTML = `Last time: <strong>${prev.score}/${TOTAL}</strong> — ${persona.title}`
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

  // Start over (mid-quiz) + retake (from the result screen).
  const restartBtn = $('quiz-restart')
  if (restartBtn) restartBtn.addEventListener('click', () => {
    track('quiz_restart', { quiz: slug, step: step + 1 })
    resetQuiz(false)
  })
  const retakeBtn = $('quiz-retake')
  if (retakeBtn) retakeBtn.addEventListener('click', () => {
    track('quiz_retake', { quiz: slug })
    resetQuiz(true)
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
      btn.classList.remove('quiz-correct', 'quiz-wrong')
    }
    $('quiz-next').classList.remove('quiz-next-final')
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
    // Highlight only the user's pick — one button, always.
    // (The verdict line above already names the right answer.)
    const realBtn = $('quiz-real')
    const fakeBtn = $('quiz-fake')
    realBtn.disabled = true
    fakeBtn.disabled = true
    const picked = guessIsReal ? realBtn : fakeBtn
    picked.classList.add(correct ? 'quiz-correct' : 'quiz-wrong')
    $('quiz-choices').hidden = false
    $('quiz-next-wrap').hidden = false
    const nx = $('quiz-next')
    const isLast = step === TOTAL - 1
    nx.textContent = isLast ? 'See my result' : 'Next story'
    nx.classList.toggle('quiz-next-final', isLast)
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

  function resetQuiz(autostart) {
    step = 0
    answers.length = 0
    unlocked = false
    questions = pickQuestions(pool, TOTAL)
    // Restore the gate UI for a fresh run (blur + form back, result away).
    $('quiz-blur').hidden = false
    $('quiz-gate-form').hidden = false
    $('quiz-result-full').hidden = true
    $('quiz-gate').hidden = true
    $('quiz-play').hidden = true
    const rimg = $('quiz-result-img')
    if (rimg) rimg.hidden = true
    // Refresh the hook's returning-player card from the saved score.
    try {
      const prev = loadQuizResult(window.localStorage, slug)
      const persona = prev && prev.resultSlug ? resultBySlug(results, prev.resultSlug) : null
      const last = $('quiz-last')
      if (prev && Number.isInteger(prev.score) && persona && last) {
        last.innerHTML = `Last time: <strong>${prev.score}/${TOTAL}</strong> — ${persona.title}`
        last.hidden = false
      }
      if (prev && startBtn) startBtn.textContent = 'Play again'
    } catch { /* keep default hook copy */ }
    if (progressTrack) {
      progressTrack.hidden = true
      $('quiz-progress').style.width = '0%'
    }
    if (autostart && hook) {
      hook.hidden = true
      $('quiz-play').hidden = false
      if (progressTrack) progressTrack.hidden = false
      track('quiz_start', { quiz: slug })
      renderStep()
    } else if (hook) {
      hook.hidden = false
    }
    window.scrollTo({ top: 0, behavior: 'smooth' })
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
    // Persona card art — same file the static result pages use for OG.
    const imgPath = `/static/img/quiz/${slug}/og-quiz-${result.slug}.jpg`
    const rimg = $('quiz-result-img')
    if (rimg) {
      rimg.src = imgPath
      rimg.alt = result.title
      rimg.hidden = false
    }
    // Point the page OG at the persona card so reshares carry the result.
    const og = document.querySelector('meta[property="og:image"]')
    if (og) og.setAttribute('content', `https://spanified.com${imgPath}`)
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
