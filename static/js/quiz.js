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
  isQuizSubscribed,
} from './quiz-logic.js'
// Shared analytics gate (flag → hostname fallback) + gtag wrapper — the local
// isLocal() + track() duplicates of subscribe-form.js now live in analytics.js.
import { trackEvent } from './analytics.js'

const $ = id => document.getElementById(id)
const TOTAL = 10

// Event name/params unchanged; the guard chain (window.SPANIFIED_ANALYTICS
// flag → local-origin probe → gtag present) is shared with every other tracker.
const track = trackEvent

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
  set('a[href*="threads.com/intent"]', `https://www.threads.com/intent/post?text=${tl}&url=${u}`)
  const copy = wrap.querySelector('.share-copy')
  if (copy) copy.dataset.url = pageUrl
}

function wireShareCopy() {
  const wrap = document.querySelector('.quiz-share .share-wrap')
  if (!wrap) return
  wrap.addEventListener('click', e => {
    const btn = e.target.closest('.share-copy')
    if (!btn) return
    const label = btn.querySelector('span')
    const done = () => {
      if (label) label.textContent = 'Copied!'
      btn.classList.add('is-copied')
      setTimeout(() => {
        if (label) label.textContent = 'Copy link'
        btn.classList.remove('is-copied')
      }, 1500)
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
  const { slug, title, questions: pool, results, real_label, fake_label } = JSON.parse(dataEl.textContent)
  let questions = pickQuestions(pool, TOTAL)
  const answers = []
  let step = 0
  let unlocked = false

  // Hook screen: show questions only after Start.
  const startBtn = $('quiz-start')
  const hook = $('quiz-hook')
  const play = $('quiz-play')
  const stage = $('quiz-stage')
  const body = document.body
  const personaImg = result => `/static/img/quiz/${slug}/og-quiz-${result.slug}.jpg`
  // Per-question correctness, in order; drives the progress segments.
  const verdicts = []

  function showLast() {
    try {
      const prev = loadQuizResult(window.localStorage, slug)
      const persona = prev && prev.resultSlug ? resultBySlug(results, prev.resultSlug) : null
      const last = $('quiz-last')
      if (prev && Number.isInteger(prev.score) && persona && last) {
        last.innerHTML = `Last time: <strong>${prev.score}/${TOTAL}</strong> — ${persona.title}`
        last.hidden = false
      }
      if (prev && Number.isInteger(prev.score) && persona && startBtn) startBtn.textContent = 'Play again'
    } catch { /* first visit: keep default hook copy */ }
  }

  // The playing screen is one fixed stage: keep the card at the top of the
  // viewport once, instantly, so answering never needs a scroll.
  function bringIntoView(el) {
    if (el && el.getBoundingClientRect().top < 0) el.scrollIntoView({ block: 'start' })
  }

  function startPlay() {
    if (hook) hook.hidden = true
    play.hidden = false
    body.classList.add('quiz-playing')
    track('quiz_start', { quiz: slug })
    buildSlides()
    showStep(0)
    window.scrollTo(0, 0)
  }

  if (startBtn && hook) {
    showLast()
    startBtn.addEventListener('click', startPlay)
  } else {
    // No hook (fallback): start immediately.
    startPlay()
  }

  const skip = $('quiz-skip')
  if (skip) skip.addEventListener('click', () => {
    track('quiz_skip', { quiz: slug })
    unlock(true)
  })

  // Retake (from the result screen).
  const retakeBtn = $('quiz-retake')
  if (retakeBtn) retakeBtn.addEventListener('click', () => {
    track('quiz_retake', { quiz: slug })
    resetQuiz(true)
  })

  // Subscription record (spanified_subscribed, site-wide — set by any
  // successful subscribe form or by the quiz-success page after the double
  // opt-in click). A saved score alone never unlocks.
  function hasSubscribed() {
    try {
      return isQuizSubscribed(window.localStorage, slug)
    } catch {
      return false
    }
  }

  function buildSegs(el) {
    el.innerHTML = ''
    for (let i = 0; i < TOTAL; i++) el.appendChild(document.createElement('li'))
  }

  function paintSegs(el, current) {
    Array.from(el.children).forEach((li, i) => {
      li.className = verdicts[i] === undefined ? '' : (verdicts[i] ? 'is-right' : 'is-wrong')
      if (i === current) li.classList.add('is-now')
    })
  }

  // Every question lives in the same grid cell, so the card is always as tall
  // as the tallest question + verdict: answering or moving on never resizes it.
  function buildSlides() {
    stage.innerHTML = ''
    verdicts.length = 0
    buildSegs($('quiz-segs'))
    questions.forEach((q, i) => {
      const slide = document.createElement('section')
      slide.className = 'quiz-slide'
      slide.innerHTML = `
        <h2 class="quiz-headline" tabindex="-1"></h2>
        <p class="quiz-summary"></p>
        <div class="quiz-choices">
          <button type="button" class="quiz-choice" data-real="1"></button>
          <button type="button" class="quiz-choice" data-real="0"></button>
        </div>
        <div class="quiz-feedback" role="status">
          <div class="quiz-fb-head">
            <span class="quiz-stamp" aria-hidden="true"></span>
            <p class="quiz-verdict"></p>
          </div>
          <p class="quiz-explain"></p>
          <p class="quiz-source"></p>
          <button type="button" class="quiz-next"></button>
        </div>`
      slide.querySelector('.quiz-headline').textContent = q.headline
      slide.querySelector('.quiz-summary').textContent = q.summary
      const [realBtn, fakeBtn] = slide.querySelectorAll('.quiz-choice')
      realBtn.textContent = real_label || 'Real — this happened'
      fakeBtn.textContent = fake_label || 'Fake — AI slop'
      realBtn.addEventListener('click', () => answer(i, true))
      fakeBtn.addEventListener('click', () => answer(i, false))
      fillFeedback(slide, q, i)
      slide.querySelector('.quiz-next').addEventListener('click', next)
      stage.appendChild(slide)
    })
  }

  // Feedback is filled in up front (verdict text aside) so its height counts
  // towards the stage size before anyone answers.
  function fillFeedback(slide, q, i) {
    const fb = slide.querySelector('.quiz-feedback')
    fb.querySelector('.quiz-stamp').textContent = q.isReal ? 'Real' : 'Fake'
    fb.querySelector('.quiz-verdict').textContent = 'Not quite. This one is real.'
    fb.querySelector('.quiz-explain').textContent = q.explanation
    const src = fb.querySelector('.quiz-source')
    if (q.isReal && q.source) {
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
      src.textContent = 'Invented by Spanified. No source, just vibes.'
    } else {
      src.hidden = true
    }
    fb.querySelector('.quiz-next').textContent = i === TOTAL - 1 ? 'See my result' : 'Next question'
  }

  function showStep(i) {
    step = i
    Array.from(stage.children).forEach((s, j) => {
      s.classList.toggle('is-current', j === i)
      s.classList.remove('is-entering')
    })
    const slide = stage.children[i]
    $('quiz-step').textContent = `Story ${i + 1} of ${TOTAL}`
    paintSegs($('quiz-segs'), i)
    if (i > 0) {
      slide.classList.add('is-entering')
      const h = slide.querySelector('.quiz-headline')
      if (h) h.focus({ preventScroll: true })
    }
  }

  function answer(i, guessIsReal) {
    if (i !== step) return
    const slide = stage.children[i]
    if (slide.classList.contains('is-answered')) return
    const q = questions[i]
    const correct = guessIsReal === q.isReal
    answers[i] = guessIsReal
    verdicts[i] = correct
    track('quiz_step', { quiz: slug, step: i + 1, correct })
    const [realBtn, fakeBtn] = slide.querySelectorAll('.quiz-choice')
    realBtn.disabled = true
    fakeBtn.disabled = true
    // The pick is coloured; the other button gets an outline when it was the truth.
    const picked = guessIsReal ? realBtn : fakeBtn
    picked.classList.add(correct ? 'quiz-correct' : 'quiz-wrong')
    if (!correct) (q.isReal ? realBtn : fakeBtn).classList.add('quiz-truth')
    const fb = slide.querySelector('.quiz-feedback')
    slide.classList.add('is-answered', correct ? 'is-right' : 'is-wrong')
    fb.querySelector('.quiz-verdict').textContent = correct
      ? 'You got it.'
      : (q.isReal ? 'Not quite. This one is real.' : 'Not quite. This one is fake.')
    const nx = fb.querySelector('.quiz-next')
    paintSegs($('quiz-segs'), i)
    nx.focus({ preventScroll: true })
  }

  function next() {
    if (step < TOTAL - 1) showStep(step + 1)
    else finish()
  }

  function showGate(score, result, showBreakdown) {
    play.hidden = true
    if (hook) hook.hidden = true
    // Still in focus mode: the gate is one phone screen with no page chrome.
    body.classList.add('quiz-playing')
    $('quiz-gate').hidden = false
    // Persona title stays sealed; only the score and the blurred art show yet.
    $('quiz-score-num').textContent = score
    $('quiz-score-line').textContent = `You scored ${score} out of ${TOTAL}`
    const segs = $('quiz-gate-segs')
    segs.hidden = !showBreakdown
    if (showBreakdown) {
      buildSegs(segs)
      paintSegs(segs, -1)
    }
    $('quiz-locked-img').src = personaImg(result)
    bringIntoView($('quiz-gate'))
  }

  // Deep link #result (e.g. "Back to my result" from the subscribed page):
  // WITHOUT a submit on record this shows the LOCKED gate (score + form),
  // never the result.
  try {
    if (window.location.hash === '#result') {
      const saved = loadQuizResult(window.localStorage, slug)
      const persona = saved && Number.isInteger(saved.score) && saved.score >= 0 && saved.score <= TOTAL
        ? resultForScore(results, saved.score) : null
      if (persona) {
        showGate(saved.score, persona, false)
        if (hasSubscribed()) {
          unlock(true)
        } else {
          $('quiz-blur').hidden = false
          $('quiz-gate-form').hidden = false
          $('quiz-result-full').hidden = true
        }
      }
    }
  } catch { /* corrupted storage — fall through to the normal hook flow */ }

  function finish() {
    const score = scoreAnswers(questions, answers)
    const result = resultForScore(results, score)
    track('quiz_finish', { quiz: slug, score })
    // Preserve a previous subscription: an already-subscribed player
    // retaking the quiz must never see the gate form (or the skip) again.
    const subscribed = hasSubscribed()
    try {
      saveQuizResult(window.localStorage, slug, { score, slug, resultSlug: result.slug })
    } catch { /* private mode — result page will show same-device hint */ }
    showGate(score, result, true)
    window.scrollTo(0, 0)
    if (subscribed) {
      // No gate, no skip, no subscribe event — straight to the full result.
      unlock(true)
    }
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
    play.hidden = true
    body.classList.remove('quiz-playing')
    const rimg = $('quiz-result-img')
    if (rimg) rimg.hidden = true
    showLast()
    if (autostart && hook) {
      startPlay()
    } else if (hook) {
      hook.hidden = false
      window.scrollTo(0, 0)
    }
  }

  function unlock(skipped) {
    if (unlocked) return
    unlocked = true
    // Re-read score/result (source of truth = localStorage).
    const saved = loadQuizResult(window.localStorage, slug)
    const score = saved ? saved.score : scoreAnswers(questions, answers)
    const result = resultForScore(results, score)
    // The opt-in itself is recorded by the quiz-success page after the
    // double opt-in click — unlock() only tracks analytics here.
    if (!skipped) {
      track('quiz_subscribe', { quiz: slug, score })
    }
    // Gate resolved (subscribed or skipped) — the teaser box is pointless now.
    body.classList.remove('quiz-playing')
    $('quiz-blur').hidden = true
    $('quiz-gate-form').hidden = true
    $('quiz-result-full').hidden = false
    $('quiz-result-title').textContent = result.title
    // Persona card art — same file the static result pages use for OG.
    const imgPath = personaImg(result)
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
    // Personal share: exact score in text + result encoded in the URL.
    // X gets the short line; FB/TG/WA get the longer roast text.
    const base = `${window.location.origin}${window.location.pathname}`
    syncShareLinks(
      personalShareText(result, score, TOTAL),
      quizResultUrl(base, result.slug, score),
      personalLongShareText(result, score, TOTAL),
    )
  }

  wireShareCopy()
  syncShareLinks(title ? `${title} — Spanified` : document.title)
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init)
} else {
  init()
}
