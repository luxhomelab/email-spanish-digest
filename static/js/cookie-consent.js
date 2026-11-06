// Cookie banner + consent-gated loading of Google Analytics 4 and Meta Pixel.
// templates/base.html defines a gtag() queue with every consent signal
// "denied" but loads no vendor script; this module loads gtag.js only after an
// "analytics" opt-in and the Meta Pixel only after a "marketing" opt-in.
// Markup: templates/partials/cookie-banner.html. Logic: cookie-consent-logic.js.
import {
  CONSENT_KEY, parseConsent, serializeConsent, allChoice, isWithdrawal, vendorCookieNames
} from './cookie-consent-logic.js'
import { isAnalyticsEnabled } from './analytics.js'

const ids = window.SPANIFIED_CONSENT_IDS || {}
// Local builds and local origins (same gate as every tracker) show the banner
// but load nothing, even after "Accept".
const vendorsAllowed = isAnalyticsEnabled()

function readStored () {
  try { return parseConsent(window.localStorage.getItem(CONSENT_KEY)) } catch { return null }
}

function store (choice) {
  try { window.localStorage.setItem(CONSENT_KEY, serializeConsent(choice)) } catch { /* private mode: ask again next visit */ }
}

let gaLoaded = false
function loadAnalytics () {
  if (gaLoaded || !vendorsAllowed || !ids.ga || typeof window.gtag !== 'function') return
  gaLoaded = true
  window.gtag('consent', 'update', { analytics_storage: 'granted' })
  const s = document.createElement('script')
  s.async = true
  s.src = 'https://www.googletagmanager.com/gtag/js?id=' + encodeURIComponent(ids.ga)
  document.head.appendChild(s)
}

let pixelLoaded = false
function loadMarketing () {
  if (pixelLoaded || !vendorsAllowed || !ids.pixel) return
  pixelLoaded = true
  if (typeof window.gtag === 'function') {
    window.gtag('consent', 'update', { ad_storage: 'granted', ad_user_data: 'granted', ad_personalization: 'granted' })
  }
  /* eslint-disable */
  !function(f,b,e,v,n,t,s){if(f.fbq)return;n=f.fbq=function(){n.callMethod?
  n.callMethod.apply(n,arguments):n.queue.push(arguments)};if(!f._fbq)f._fbq=n;
  n.push=n;n.loaded=!0;n.version='2.0';n.queue=[];t=b.createElement(e);t.async=!0;
  t.src=v;s=b.getElementsByTagName(e)[0];s.parentNode.insertBefore(t,s)}(window,
  document,'script','https://connect.facebook.net/en_US/fbevents.js');
  /* eslint-enable */
  window.fbq('init', ids.pixel)
  window.fbq('track', 'PageView')
}

function apply (choice) {
  if (choice.analytics) loadAnalytics()
  if (choice.marketing) loadMarketing()
}

// Expire vendor cookies on this host and every parent domain they may sit on.
function clearVendorCookies (choice) {
  const names = vendorCookieNames(document.cookie, choice)
  if (!names.length) return
  const parts = location.hostname.split('.')
  const domains = ['']
  for (let i = 0; i < parts.length - 1; i++) domains.push('; domain=.' + parts.slice(i).join('.'))
  for (const n of names) {
    for (const d of domains) document.cookie = n + '=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/' + d
  }
}

const banner = document.getElementById('cookie-banner')
let current = readStored()

function showBanner (withDetails) {
  if (!banner) return
  const details = banner.querySelector('.cc-details')
  const c = current || allChoice(false)
  banner.querySelectorAll('input[data-cc-category]').forEach((box) => {
    box.checked = c[box.dataset.ccCategory] === true
  })
  if (details) details.hidden = !withDetails
  banner.classList.toggle('is-open', !!withDetails)
  banner.querySelector('[data-cc="save"]').hidden = !withDetails
  banner.querySelector('[data-cc="customize"]').hidden = !!withDetails
  banner.hidden = false
}

function decide (choice) {
  const withdrawn = isWithdrawal(current, choice)
  current = choice
  store(choice)
  if (banner) banner.hidden = true
  if (withdrawn) {
    // Already-running vendor scripts cannot be unloaded: drop their cookies and start clean.
    clearVendorCookies(choice)
    location.reload()
    return
  }
  apply(choice)
}

if (current) apply(current)
else showBanner(false)

if (banner) {
  banner.addEventListener('click', (e) => {
    const btn = e.target.closest && e.target.closest('[data-cc]')
    if (!btn) return
    const action = btn.dataset.cc
    if (action === 'accept') decide(allChoice(true))
    else if (action === 'reject') decide(allChoice(false))
    else if (action === 'customize') showBanner(true)
    else if (action === 'save') {
      const choice = allChoice(false)
      banner.querySelectorAll('input[data-cc-category]').forEach((box) => {
        choice[box.dataset.ccCategory] = box.checked
      })
      decide(choice)
    }
  })
}

// "Cookie settings" links (footer, cookie policy page) reopen the choices.
document.addEventListener('click', (e) => {
  const link = e.target.closest && e.target.closest('[data-cookie-settings]')
  if (!link) return
  e.preventDefault()
  showBanner(true)
  const first = banner && banner.querySelector('input[data-cc-category]')
  if (first) first.focus()
})
