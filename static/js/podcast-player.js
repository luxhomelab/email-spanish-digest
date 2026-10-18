// Digest-page podcast player: wires templates/partials/podcast-player.html
// to a native <audio>. Logic lives in podcast-player-logic.js.
import { formatTime, nextSpeed, chapterAt, resumePosition, storageKey } from './podcast-player-logic.js'
import { trackEvent } from './analytics.js'

const root = document.querySelector('.podcast-player')
if (root) init(root)

function init(root) {
  const audio = root.querySelector('.pp-audio')
  const play = root.querySelector('.pp-play')
  const controls = root.querySelector('.pp-controls')
  const seek = root.querySelector('.pp-seek')
  const current = root.querySelector('.pp-current')
  const speed = root.querySelector('.pp-speed')
  const chapterBtns = [...root.querySelectorAll('.pp-chapter')]
  const mini = document.querySelector('.pp-mini')
  const miniLabel = mini.querySelector('.pp-mini-label')
  const miniBar = mini.querySelector('.pp-mini-bar')
  const date = root.dataset.date
  const title = root.dataset.title
  const duration = Number(root.dataset.duration) || 0
  let chapters = []
  try { chapters = JSON.parse(root.dataset.chapters || '[]') } catch { /* no chapters */ }

  play.hidden = false
  let started = false
  let miniDismissed = false
  let cardVisible = true
  let lastChapter = -2
  let lastSave = 0
  const milestones = new Set()

  const key = storageKey(date)
  let resumeAt = 0
  try { resumeAt = resumePosition(localStorage.getItem(key), duration) } catch { /* storage blocked */ }
  if (resumeAt) {
    current.textContent = formatTime(resumeAt)
    seek.value = resumeAt
    play.setAttribute('aria-label', `Resume from ${formatTime(resumeAt)}`)
    root.querySelector('.pp-kicker').textContent += ` · resume at ${formatTime(resumeAt)}`
  }

  function start() {
    if (!started) {
      started = true
      controls.hidden = false
      if (resumeAt && audio.currentTime < 1) audio.currentTime = resumeAt
      trackEvent('podcast_play', { edition_date: date })
      setupMediaSession()
    }
    return audio.play()
  }

  function toggle() {
    if (audio.paused) start()
    else audio.pause()
  }

  play.addEventListener('click', toggle)
  mini.querySelector('.pp-mini-play').addEventListener('click', toggle)
  mini.querySelector('.pp-mini-close').addEventListener('click', () => {
    audio.pause()
    miniDismissed = true
    updateMini()
  })

  root.querySelectorAll('.pp-skip').forEach((b) => b.addEventListener('click', () => {
    audio.currentTime = Math.max(0, Math.min(duration || audio.duration || 0, audio.currentTime + Number(b.dataset.skip)))
  }))

  seek.addEventListener('input', () => {
    audio.currentTime = Number(seek.value)
    current.textContent = formatTime(seek.value)
  })

  speed.addEventListener('click', () => {
    audio.playbackRate = nextSpeed(audio.playbackRate)
    speed.textContent = `${audio.playbackRate}×`
  })

  chapterBtns.forEach((b) => b.addEventListener('click', () => {
    const t = Number(b.dataset.start)
    if (!started) resumeAt = 0
    start().then(() => { audio.currentTime = t }, () => {})
    audio.currentTime = t
  }))

  audio.addEventListener('play', () => { root.classList.add('is-playing'); mini.classList.add('is-playing'); miniDismissed = false; updateMini() })
  audio.addEventListener('pause', () => { root.classList.remove('is-playing'); mini.classList.remove('is-playing'); save() })
  audio.addEventListener('ended', () => {
    trackEvent('podcast_complete', { edition_date: date })
    try { localStorage.removeItem(key) } catch { /* ignore */ }
  })

  audio.addEventListener('timeupdate', () => {
    const t = audio.currentTime
    const total = duration || audio.duration || 0
    seek.value = t
    current.textContent = formatTime(t)
    if (total) miniBar.style.width = `${Math.min(100, (t / total) * 100)}%`
    if (total && t / total >= 0.5 && !milestones.has(50)) {
      milestones.add(50)
      trackEvent('podcast_progress', { edition_date: date, percent: 50 })
    }
    const idx = chapterAt(chapters, t)
    if (idx !== lastChapter) {
      lastChapter = idx
      chapterBtns.forEach((b, i) => b.classList.toggle('is-current', i === idx))
      miniLabel.textContent = idx >= 0 ? chapters[idx].title : title
    }
    if (Date.now() - lastSave > 5000) save()
  })

  function save() {
    lastSave = Date.now()
    try { localStorage.setItem(key, String(Math.floor(audio.currentTime))) } catch { /* ignore */ }
  }

  // Mini player shows only after playback started, while the card is off-screen.
  function updateMini() {
    mini.hidden = !started || miniDismissed || cardVisible
  }
  if ('IntersectionObserver' in window) {
    new IntersectionObserver(([e]) => { cardVisible = e.isIntersecting; updateMini() }).observe(root)
  }

  function setupMediaSession() {
    if (!('mediaSession' in navigator)) return
    try {
      navigator.mediaSession.metadata = new MediaMetadata({
        title,
        artist: 'Spain Daily',
        album: `Spain Daily · ${date}`,
        artwork: [{ src: '/static/podcast-cover.jpg', sizes: '1400x1400', type: 'image/jpeg' }],
      })
      const ms = navigator.mediaSession
      ms.setActionHandler('play', () => audio.play())
      ms.setActionHandler('pause', () => audio.pause())
      ms.setActionHandler('seekbackward', () => { audio.currentTime = Math.max(0, audio.currentTime - 15) })
      ms.setActionHandler('seekforward', () => { audio.currentTime += 15 })
      ms.setActionHandler('seekto', (d) => { audio.currentTime = d.seekTime })
    } catch { /* partial support */ }
  }
}
