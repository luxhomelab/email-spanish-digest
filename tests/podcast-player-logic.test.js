import { test } from 'node:test'
import assert from 'node:assert/strict'
import { formatTime, nextSpeed, chapterAt, resumePosition, storageKey } from '../static/js/podcast-player-logic.js'

test('formatTime', () => {
  assert.equal(formatTime(0), '0:00')
  assert.equal(formatTime(65.9), '1:05')
  assert.equal(formatTime(3725), '1:02:05')
  assert.equal(formatTime(NaN), '0:00')
})

test('nextSpeed cycles', () => {
  assert.equal(nextSpeed(1), 1.25)
  assert.equal(nextSpeed(2), 1)
  assert.equal(nextSpeed(0.8), 1)
})

test('chapterAt', () => {
  const ch = [{ start: 0 }, { start: 15.9 }, { start: 33.7 }]
  assert.equal(chapterAt(ch, 0), 0)
  assert.equal(chapterAt(ch, 20), 1)
  assert.equal(chapterAt(ch, 999), 2)
  assert.equal(chapterAt([], 5), -1)
})

test('resumePosition', () => {
  assert.equal(resumePosition(null, 555), 0)
  assert.equal(resumePosition('5', 555), 0)
  assert.equal(resumePosition('120', 555), 120)
  assert.equal(resumePosition('550', 555), 0)
  assert.equal(storageKey('2026-10-18'), 'spanified:podcast:2026-10-18')
})
