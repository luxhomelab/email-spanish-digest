// Pure helpers for the digest-page podcast player (podcast-player.js).
// No DOM access here so tests/podcast-player-logic.test.js can import it.

export const SPEEDS = [1, 1.25, 1.5, 2]

export function formatTime(seconds) {
  const s = Math.max(0, Math.floor(Number(seconds) || 0))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const ss = String(s % 60).padStart(2, '0')
  return h ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${m}:${ss}`
}

export function nextSpeed(current) {
  const i = SPEEDS.indexOf(current)
  return SPEEDS[(i + 1) % SPEEDS.length]
}

// Index of the chapter playing at time t (chapters sorted by start), -1 if none.
export function chapterAt(chapters, t) {
  let idx = -1
  for (let i = 0; i < (chapters || []).length; i++) {
    if (chapters[i].start <= t) idx = i
    else break
  }
  return idx
}

// Where to resume: ignore the first few seconds and the tail end of the episode.
export function resumePosition(saved, duration) {
  const t = Number(saved)
  if (!Number.isFinite(t) || t < 10) return 0
  if (duration && t > duration - 15) return 0
  return t
}

export function storageKey(date) {
  return `spanified:podcast:${date}`
}
