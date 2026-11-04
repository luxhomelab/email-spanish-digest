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

  document.addEventListener('click', function (e) {
    var link = e.target.closest && e.target.closest('a.ve-frame[data-video-id]')
    if (!link || e.metaKey || e.ctrlKey || e.shiftKey || e.button > 0) return
    e.preventDefault()
    var iframe = document.createElement('iframe')
    iframe.className = 've-iframe'
    iframe.src = 'https://www.youtube-nocookie.com/embed/' + link.dataset.videoId + '?autoplay=1&rel=0'
    iframe.title = link.dataset.videoTitle || 'YouTube video'
    iframe.allow = 'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share'
    iframe.referrerPolicy = 'strict-origin-when-cross-origin'
    iframe.allowFullscreen = true
    link.replaceWith(iframe)
    iframe.focus()
    if (window.SPANIFIED_ANALYTICS !== false && typeof window.gtag === 'function') {
      window.gtag('event', 'video_play', { video_id: link.dataset.videoId, page_path: location.pathname })
    }
  })
})()
