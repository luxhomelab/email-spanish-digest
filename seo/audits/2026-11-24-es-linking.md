# Spanish linking audit: no English links, EN/ES parity, new pages (2026-11-24)

Scope: everything under `dist/es/` (349 pages) after the calculators, quizzes and
subscribe/about merges. Branch `add-spanish-digests-backfill`. Follows
`2026-11-24-es-pages.md`.

Hard rule: a Spanish page never links an English page. English URLs are allowed
only in `<link rel="alternate" hreflang>`, the `og:locale:alternate` context,
`sitemap.xml` and the language switcher (`<nav class="lang-switch">`).

## 1. English URLs on Spanish pages

### Strict guard
`test_es_links.py::test_spanish_pages_never_link_english` now fails on any English
internal URL on any `/es/` page, noindex flow pages included (confirm, success,
unsubscribe, quiz `-subscribed` / `-success` / `-result-*`). It reads:

- every tag attribute that holds an internal URL (`href`, `src`, `action`,
  `content` of `og:url` and other meta tags, `value` of the hidden `next` input,
  `data-*`), canonical and prev/next included;
- every string in every JSON-LD block (`url`, `@id`, `item`, `mainEntityOfPage`,
  `isPartOf` and the rest);
- quoted paths in inline scripts.

Exempt: the switcher nav and `<link ... hreflang>`. Static assets (`/static/`,
`/og/`, images, `/podcast.xml`, favicons) drop out. The same pass checks that
every `/es/` URL resolves and that its `#anchor` exists (JSON-LD `@id` fragments
name graph nodes, so they are skipped). `test_guard_catches_english_urls` pins
each channel and each exemption on a synthetic page.

### What the guard found (build before this change)
In visible HTML, no English `href`, `src` or `action` was left on `/es/`. The `/`,
`/terms`, `/subscribe`, `/category/*` and `/quiz/*` hrefs that a raw grep shows
are all in the switcher or in hreflang tags, which the rule allows. The real
leaks were all in JSON-LD, the Organization node pointing at the English home:
**2,325 URLs on 299 of 349 pages**.

| Source | Pages | URLs | Fix |
|---|---|---|---|
| `templates/digest.html` NewsArticle `publisher.url` | 197 digests | 2,148 | `lang_url('/')` |
| `templates/calculator-*.html` WebPage `about` Organization | 88 calculators | 88 | `lang_url('/')` |
| `build.py` `video_embed_html` VideoObject `publisher.url` | 72 calculator + 4 article pages | 76 | `localize(lang, "/")` |
| `templates/es/{about,contact,editor,cookies,privacy,terms}.html` | 6 | 6 | `/es/` |
| `templates/index.html` Organization `@id`/`url` + 2 `publisher @id` | `/es/` | 4 | `lang_url('/')` + `#org` |
| `templates/quiz.html` Quiz `publisher @id` | 2 quizzes | 2 | `lang_url('/')` + `#org` |
| `templates/es/subscribe.html` `publisher @id` | `/es/subscribe` | 1 | `/es/#org` |

Spanish pages now point at a Spanish Organization node, `https://spanified.com/es/#org`,
with url `/es/`, defined on `/es/`. English output is byte-identical apart from
asset version hashes (checked by diffing the full English build before and after).

### JS-built URLs (read through)
- Share links (`quiz.js syncShareLinks`, calculator `pageUrl`, quiz-success inline
  module): built from `window.location`, so they stay on the page's own language.
- Quiz result and retake URLs: `quizResultUrl(location.origin + location.pathname)`
  and the template's `quiz_base` (`/es/quiz/<slug>` on Spanish pages).
- Calculator query links: `new URL(window.location.href)`.
- `subscribe-form.js`: the redirect fallback when a form has no `next` was a
  hard-coded `/confirm`. Every form renders `next` (Spanish forms get
  `/es/confirm`), but the fallback is now `confirmPath(lang)` → `/es/confirm`
  on Spanish forms (covered in `tests/subscribe-form.test.js`).

### Missing twins
The only English pages without a Spanish twin are `404.html` (GitHub Pages serves
the root 404 only), `search.html` (Pagefind indexes English) and the four
meta-refresh stubs (`t`, `wa`, `yt`, `mail`). No Spanish page links any of them.

## 2. Linking parity with the English site

### Fixed
- **Calculator lines in Spanish digests.** Before: none (0, against 333 in
  English), because `STORY_TOOLS` keywords and the amount regexes read English
  text. Now `attach_twin_links()` pairs each Spanish story with its English twin
  by a shared source URL (2,147 of 2,148 Spanish stories pair) and copies the
  twin's calculator, with a Spanish anchor (15 tool anchors and 5 amount-page
  templates in `ES_STRINGS`). Amount pages get Spanish number formats, for example
  "sueldo neto con 1.200 € brutos al mes" → `/es/calculators/net-salary-1200-euros-per-month`.
  Result: 333 / 333 calculator lines, 23 of them to amount pages.
- **Guide lines.** The Spanish keyword match stays. A story with no match now falls
  back to its twin's guide, with the Spanish title. Totals across 197 digests
  (EN → ES): guide lines 306 → 354, calculator cards 321 → 327, guide cards
  261 → 255 (the hub block skips pages a story line already links). Per digest,
  ES suggestions ≥ EN everywhere (154 equal, 44 more). Before this change,
  28 digests had fewer.
- **Static flow pages.** `/es/confirm`, `/es/success`, `/es/unsubscribe` and
  `/es/subscribe` now have breadcrumbs, like English. `/es/success` gains the
  "Lee la edición de hoy" (`/es/`) and "Explora el archivo" (`/es/archive/`)
  steps. `/es/unsubscribe` links `/es/contact` instead of a bare mailto.
  `/es/subscribe` gains the "¿Aún lo dudas? Lee la última edición" line.
  `/es/terms` links `/es/` and `/es/about` ("cómo trabajamos"), like English.

### Parity test
`test_es_links.py::test_linking_parity_sample` compares link profiles of 31 EN/ES
pairs (5 digests, archive listing pages, 2 categories, 3 articles plus the list,
5 calculator hubs, 2 amount pages, 2 quizzes, home, about, editor, contact,
subscribe, confirm, success, unsubscribe, terms). A profile is the block counts
(guide and calculator lines, calculator and guide cards, breadcrumbs, day nav,
amount-page prev/next, other-quiz card) plus body links by section. Counts must
be equal. On digests, calculator lines must be equal and total suggestions
ES ≥ EN. `test_every_spanish_digest_has_the_english_suggestions` applies the
digest rule to all 197 editions.

Current differences that are content, not linking: the podcast player (English
audio, not on Spanish digests); 2026-11-17 (13 English stories, 12 Spanish);
`/category/work` (one more English story).

## 3. SEO audit: calculators, quizzes, about/editor/contact, subscribe (108 pages)

Checked on the built output with a crawler script over `dist/es`.

**Passing**
- Orphans: none. Every indexable page has 2 or more inbound Spanish links.
- Depth from `/es/`: 11 pages at depth 1, 83 at depth 2 (the hubs and every
  amount page, through the home cards, the footer and prev/next). Nothing is
  deeper than 2.
- Anchor text: no English-looking anchors and no empty anchors point at these pages.
- Broken links and anchors: none (strict guard).
- Canonicals: self, `/es/` URLs. hreflang en/es/x-default is reciprocal on all 94
  indexable pages (checked against the English twin).
- og:locale `es_ES` on every page. JSON-LD `inLanguage` is `es` wherever it is
  set, and the URLs are `/es/` (strict guard).
- One `<h1>` per page; every `<img>` has `alt`.
- Sitemap: all 94 indexable pages are listed with xhtml alternates; no noindex
  page is listed.
- Descriptions: 110 to 165 characters, unique.

**Fixed**
- `/es/contact` title was 20 characters ("Contacto | Spanified"). It is now
  "Contacto: escribe a la redacción de España al Día | Spanified".
- `/es/about` title was 68 characters. It is now 64: "... en 5 minutos | Spanified".

**Left as is**
- Titles of 66 to 70 characters on 26 autónomo amount pages, the 1,000,000 €
  rental-yield page and `/es/quiz/spanish-law-or-myth`. The English twins are
  longer (up to 85), and only the " | Spanified" suffix gets truncated.
- Noindex flow pages (quiz `-subscribed`, `-success`, `-result-*`, `/es/confirm`,
  `/es/success`) have no inbound links. They are redirect and share targets,
  the same as in English. The two quizzes share the `-subscribed` and `-success`
  titles; these pages are noindex.
- Archive pagination `/es/archive/N` is up to 10 clicks deep (prev/next only),
  the same as in English. A numbered pager would fix both languages.

## Deferred
- A Spanish search page (it needs a Spanish Pagefind index).
- The Organization identity is split: `/#org` (English) and `/es/#org` (Spanish).
  Joining them with `sameAs` would put an English URL in Spanish JSON-LD, which
  the rule forbids.
- English content still on Spanish pages (YouTube videos, quiz art, social
  channels) is unchanged; see the session notes in `2026-11-24-es-pages.md`.
