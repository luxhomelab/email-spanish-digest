// Click-to-load YouTube embeds rendered by build.py video_embed_html().
// The page ships only a thumbnail link; YouTube (youtube-nocookie.com) loads
// when the reader presses play. Without JS the link opens the video on YouTube.
(function () {
  if (window.__videoEmbedReady) return
  window.__videoEmbedReady = true

  document.querySelectorAll('.ve-frame img').forEach(function (img) {
    // A missing maxresdefault comes back as a 120x90 grey placeholder.
    var check = function () {
      if (img.naturalWidth && img.naturalWidth <= 120) {
        img.src = img.src.replace('maxresdefault', 'hqdefault')
      }
    }
    if (img.complete) check(); else img.addEventListener('load', check, { once: true })
  })

  function embedSrc (id, start) {
    return 'https://www.youtube-nocookie.com/embed/' + id + '?autoplay=1&rel=0' +
      (start ? '&start=' + start : '')
  }

  // Swap the facade (or an already playing iframe) for a player at `start`.
  function play (figure, start) {
    var link = figure.querySelector('a.ve-frame[data-video-id]')
    var iframe = figure.querySelector('iframe.ve-iframe')
    var id = link ? link.dataset.videoId : iframe && iframe.dataset.videoId
    if (!id) return
    if (iframe) {
      iframe.src = embedSrc(id, start)
    } else {
      iframe = document.createElement('iframe')
      iframe.className = 've-iframe'
      iframe.dataset.videoId = id
      iframe.src = embedSrc(id, start)
      iframe.title = link.dataset.videoTitle || 'YouTube video'
      iframe.allow = 'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share'
      iframe.referrerPolicy = 'strict-origin-when-cross-origin'
      iframe.allowFullscreen = true
      link.replaceWith(iframe)
    }
    iframe.focus()
    if (window.SPANIFIED_ANALYTICS !== false && typeof window.gtag === 'function') {
      window.gtag('event', 'video_play', { video_id: id, start: start || 0, page_path: location.pathname })
    }
  }

  document.addEventListener('click', function (e) {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.button > 0 || !e.target.closest) return
    var link = e.target.closest('a.ve-frame[data-video-id], a.ve-chap[data-start]')
    var figure = link && link.closest('.video-embed')
    if (!figure) return
    e.preventDefault()
    var start = parseInt(link.dataset.start || '0', 10)
    figure.querySelectorAll('a.ve-chap[aria-current]').forEach(function (a) { a.removeAttribute('aria-current') })
    if (link.classList.contains('ve-chap')) link.setAttribute('aria-current', 'true')
    play(figure, start)
    // On phones the chapter strip sits under the player: bring the player back into view.
    var player = figure.querySelector('.ve-player')
    if (player && player.getBoundingClientRect().top < 0) {
      var still = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches
      player.scrollIntoView({ block: 'start', behavior: still ? 'auto' : 'smooth' })
    }
  })
})()
