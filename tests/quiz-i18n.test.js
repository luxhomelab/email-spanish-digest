import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import {
  QUIZ_STRINGS,
  quizStrings,
  fillText,
  personalShareText,
  personalLongShareText,
} from '../static/js/quiz-logic.js'

const esQuiz = slug => JSON.parse(readFileSync(new URL(`../data/quizzes/es/${slug}.json`, import.meta.url), 'utf8'))

describe('quizStrings', () => {
  it('has a Spanish string for every English key', () => {
    assert.deepEqual(Object.keys(QUIZ_STRINGS.es).sort(), Object.keys(QUIZ_STRINGS.en).sort())
  })

  it('picks Spanish for es and region variants', () => {
    assert.equal(quizStrings('es').next, 'Siguiente pregunta')
    assert.equal(quizStrings('es-ES').next, 'Siguiente pregunta')
    assert.equal(quizStrings('ES').scoreLine, QUIZ_STRINGS.es.scoreLine)
  })

  it('falls back to English for other, empty or missing languages', () => {
    for (const lang of ['en', 'en-GB', 'fr', '', undefined, null]) {
      assert.equal(quizStrings(lang).next, 'Next question', String(lang))
    }
  })

  it('Spanish strings carry the same placeholders and no em dashes', () => {
    for (const [key, en] of Object.entries(QUIZ_STRINGS.en)) {
      const vars = s => (s.match(/\{\w+\}/g) || []).sort()
      assert.deepEqual(vars(QUIZ_STRINGS.es[key]), vars(en), key)
      assert.ok(!QUIZ_STRINGS.es[key].includes('—'), key)
    }
  })
})

describe('fillText', () => {
  it('fills named placeholders', () => {
    assert.equal(fillText(QUIZ_STRINGS.es.step, { n: 3, total: 10 }), 'Pregunta 3 de 10')
    assert.equal(fillText(QUIZ_STRINGS.en.scoreLine, { score: 0, total: 10 }), 'You scored 0 out of 10')
  })

  it('leaves unknown placeholders alone', () => {
    assert.equal(fillText('{a} {b}', { a: 1 }), '1 {b}')
  })
})

describe('personalShareText in Spanish', () => {
  const r = { shareText: 'He sacado 3-4/10 distinguiendo noticias reales de España de bulos de IA: turista con sospechas. ¿Lo haces mejor?' }

  it('swaps the score band for the exact score', () => {
    assert.equal(
      personalShareText(r, 4, 10, quizStrings('es')),
      'He sacado 4/10 distinguiendo noticias reales de España de bulos de IA: turista con sospechas. ¿Lo haces mejor?',
    )
  })

  it('uses the Spanish fallback line without a result', () => {
    assert.equal(personalShareText(null, 7, 10, quizStrings('es')), QUIZ_STRINGS.es.defaultShare)
  })

  it('long text appends the first paragraph', () => {
    const long = personalLongShareText({ ...r, text: 'Uno.\n\nDos.' }, 3, 10, quizStrings('es'))
    assert.equal(long, 'He sacado 3/10 distinguiendo noticias reales de España de bulos de IA: turista con sospechas. ¿Lo haces mejor?\n\nUno.')
  })

  it('every Spanish persona share line gets the exact score', () => {
    for (const slug of ['ai-or-real', 'spanish-law-or-myth']) {
      for (const [persona, res] of Object.entries(esQuiz(slug).results)) {
        const out = personalShareText(res, 6, 10, quizStrings('es'))
        assert.ok(/He sacado 6\/10 /.test(out), `${slug}/${persona}: ${out}`)
      }
    }
  })
})
