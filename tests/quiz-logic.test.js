import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import {
  storageKey,
  pickQuestions,
  scoreAnswers,
  resultForScore,
  resultBySlug,
  personalShareText,
  personalLongShareText,
  quizResultUrl,
  saveQuizResult,
  loadQuizResult,
  subscribeKey,
  markQuizSubscribed,
  isQuizSubscribed,
} from '../static/js/quiz-logic.js'

function makePool() {
  const pool = []
  for (let i = 0; i < 30; i++) {
    pool.push({ id: `r${i}`, headline: `real ${i}`, summary: 's', isReal: true, explanation: 'e' })
    pool.push({ id: `f${i}`, headline: `fake ${i}`, summary: 's', isReal: false, explanation: 'e' })
  }
  return pool
}

const RESULTS = [
  { slug: 'a', min: 0, max: 2 },
  { slug: 'b', min: 3, max: 4 },
  { slug: 'c', min: 5, max: 6 },
  { slug: 'd', min: 7, max: 8 },
  { slug: 'e', min: 9, max: 10 },
]

function memStorage() {
  const map = new Map()
  return {
    getItem: k => (map.has(k) ? map.get(k) : null),
    setItem: (k, v) => { map.set(k, v) },
  }
}

describe('storageKey', () => {
  it('namespaces per quiz slug', () => {
    assert.equal(storageKey('ai-or-real'), 'spanified_quiz_ai-or-real')
  })
})

describe('pickQuestions', () => {
  it('picks 10 with 5 real + 5 fake balance', () => {
    const picked = pickQuestions(makePool(), 10, () => 0.5)
    assert.equal(picked.length, 10)
    assert.equal(picked.filter(q => q.isReal).length, 5)
    assert.equal(picked.filter(q => !q.isReal).length, 5)
  })

  it('has no duplicates', () => {
    const picked = pickQuestions(makePool(), 10)
    assert.equal(new Set(picked.map(q => q.id)).size, 10)
  })

  it('shuffles (different order across seeds)', () => {
    const a = pickQuestions(makePool(), 10, () => 0.1).map(q => q.id).join(',')
    const b = pickQuestions(makePool(), 10, () => 0.9).map(q => q.id).join(',')
    assert.notEqual(a, b)
  })
})

describe('scoreAnswers', () => {
  it('counts correct guesses', () => {
    const qs = [{ isReal: true }, { isReal: false }, { isReal: true }]
    assert.equal(scoreAnswers(qs, [true, false, false]), 2)
  })

  it('scores 0 for all wrong', () => {
    const qs = [{ isReal: true }, { isReal: true }]
    assert.equal(scoreAnswers(qs, [false, false]), 0)
  })
})

describe('resultForScore', () => {
  it('maps boundaries correctly', () => {
    assert.equal(resultForScore(RESULTS, 0).slug, 'a')
    assert.equal(resultForScore(RESULTS, 2).slug, 'a')
    assert.equal(resultForScore(RESULTS, 3).slug, 'b')
    assert.equal(resultForScore(RESULTS, 5).slug, 'c')
    assert.equal(resultForScore(RESULTS, 7).slug, 'd')
    assert.equal(resultForScore(RESULTS, 9).slug, 'e')
    assert.equal(resultForScore(RESULTS, 10).slug, 'e')
  })
})

describe('storage helpers', () => {
  it('round-trips save/load', () => {
    const s = memStorage()
    assert.equal(saveQuizResult(s, 'ai-or-real', { score: 7, slug: 'ai-or-real' }), true)
    assert.deepEqual(loadQuizResult(s, 'ai-or-real'), { score: 7, slug: 'ai-or-real' })
  })

  it('returns null when nothing stored (same-device hint case)', () => {
    assert.equal(loadQuizResult(memStorage(), 'ai-or-real'), null)
  })

  it('returns null on corrupted JSON', () => {
    const s = memStorage()
    s.setItem(storageKey('ai-or-real'), '{broken')
    assert.equal(loadQuizResult(s, 'ai-or-real'), null)
  })

  it('save returns false when storage throws (private mode)', () => {
    const bad = { getItem: () => null, setItem: () => { throw new Error('deny') } }
    assert.equal(saveQuizResult(bad, 'ai-or-real', { score: 1 }), false)
  })
})

describe('resultBySlug', () => {
  it('finds result by slug', () => {
    assert.equal(resultBySlug(RESULTS, 'c').max, 6)
  })
  it('returns null for unknown slug', () => {
    assert.equal(resultBySlug(RESULTS, 'nope'), null)
  })
  it('returns null for empty pool', () => {
    assert.equal(resultBySlug([], 'a'), null)
  })
})

describe('personalShareText', () => {
  it('replaces score range with exact score', () => {
    const r = { shareText: 'I got 3-4/10 on AI or Real? — Tourist! Beat me?' }
    assert.equal(
      personalShareText(r, 4, 10),
      'I scored 4/10 on AI or Real? — Tourist! Beat me?',
    )
  })
  it('falls back when result has no shareText', () => {
    assert.ok(personalShareText(null, 7, 10).includes('AI or Real?'))
    assert.ok(personalShareText({}, 7, 10).includes('AI or Real?'))
  })
})

describe('quizResultUrl', () => {
  it('builds per-persona static page URL with score', () => {
    assert.equal(
      quizResultUrl('https://spanified.com/quiz/ai-or-real', 'suspicious-tourist', 4),
      'https://spanified.com/quiz/ai-or-real-result-suspicious-tourist?score=4',
    )
  })
  it('strips existing query and hash', () => {
    assert.equal(
      quizResultUrl('https://spanified.com/quiz/ai-or-real?x=1#top', 'a', 10),
      'https://spanified.com/quiz/ai-or-real-result-a?score=10',
    )
  })
  it('omits score param when score is null', () => {
    assert.equal(
      quizResultUrl('https://spanified.com/quiz/ai-or-real', 'half-spanish', null),
      'https://spanified.com/quiz/ai-or-real-result-half-spanish',
    )
  })
  it('inserts persona slug before .html (local file serving)', () => {
    assert.equal(
      quizResultUrl('http://localhost:8000/quiz/ai-or-real.html', 'half-spanish', 5),
      'http://localhost:8000/quiz/ai-or-real-result-half-spanish.html?score=5',
    )
  })
  it('keeps the quiz topic explicit in share text', () => {
    const r = { shareText: 'I got 5-6/10 telling real Spanish news from AI fakes — Half-Spanish! Can you beat me?' }
    assert.equal(
      personalShareText(r, 5, 10),
      'I scored 5/10 telling real Spanish news from AI fakes — Half-Spanish! Can you beat me?',
    )
  })
})

describe('personalLongShareText', () => {  const r = {
    shareText: 'I got 5-6/10 telling real Spanish news from AI fakes — Half-Spanish! Can you beat me?',
    text: 'Fifty-fifty! First para.\n\nSecond para.',
  }
  it('appends the first paragraph to the exact-score line', () => {
    assert.equal(
      personalLongShareText(r, 5, 10),
      'I scored 5/10 telling real Spanish news from AI fakes — Half-Spanish! Can you beat me?\n\nFifty-fifty! First para.',
    )
  })
  it('falls back to the short line when there is no text', () => {
    assert.equal(
      personalLongShareText({ shareText: 'I got 1-2/10 — X' }, 2, 10),
      personalShareText({ shareText: 'I got 1-2/10 — X' }, 2, 10),
    )
  })
})

describe('subscribe tracking (separate from score)', () => {
  it('is false with a saved score but no submit — score alone never unlocks', () => {
    const s = memStorage()
    saveQuizResult(s, 'ai-or-real', { score: 7, slug: 'ai-or-real', resultSlug: 'd' })
    assert.equal(isQuizSubscribed(s, 'ai-or-real'), false)
  })

  it('markQuizSubscribed flips it and keeps the email', () => {
    const s = memStorage()
    assert.equal(markQuizSubscribed(s, 'ai-or-real', 'a@b.com'), true)
    assert.equal(isQuizSubscribed(s, 'ai-or-real'), true)
    const raw = JSON.parse(s.getItem(subscribeKey('ai-or-real')))
    assert.equal(raw.subscribed, true)
    assert.equal(raw.email, 'a@b.com')
  })

  it('survives broken storage (private mode)', () => {
    const bad = { getItem: () => { throw new Error('deny') }, setItem: () => { throw new Error('deny') } }
    assert.equal(isQuizSubscribed(bad, 'ai-or-real'), false)
    assert.equal(markQuizSubscribed(bad, 'ai-or-real'), false)
  })
})
