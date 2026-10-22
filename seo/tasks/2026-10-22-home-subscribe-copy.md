# Copy for PR #169 follow-up: /subscribe and home (2026-10-22)

Status: draft for seo-specialist to place. Templates and build.py are NOT edited.

Search demand (GSC Queries.csv): "spanish news in english", "spain news english", "english newspapers in spain", "english language spanish newspaper", "spanish newspaper", "spain newspaper". Zero clicks so far, positions 25-57. The home copy below targets this cluster.

Owner answers (2026-10-22), applied below:
1. No original reporting: confirmed.
2. Method: we parse Spanish outlets and translate/summarize the digest in English. International news only when it directly concerns Spain.
3. No internal links inside the copy.
4. Source list taken from the RSS config (D:\workspace\spain-news-en\rss_fetch.py): El País, Cinco Días, El Mundo, La Vanguardia, elDiario.es, El Confidencial, 20 Minutos, Heraldo, Diario Sur, Expansión, Europa Press (agency).
5. Spelling: official brands are "elDiario.es" and "Diario Sur" (JSON/feed labels "El Diario" and "Sur" are not the brand names).

---

## 1. /subscribe

### 1a. "Who is it for?" block (59 words)

Placement: in `templates/subscribe.html`, after the `.subscribe-trust` block ("What you'll get") and before the form include. Same card style as `.trust-card` or a plain `h2` + `p`.

```html
<div class="subscribe-who">
  <h2>Who is Spain Daily for?</h2>
  <p>Expats who live in Spain and need to follow rents, taxes and visas. People planning a move who want to see what daily life here really looks like. And Spain watchers abroad who want the headlines without reading the Spanish press in Spanish. Five minutes, in plain English, with a link to every source.</p>
</div>
```

### 1b. "Sample edition" lead-in (one line)

Placement: directly above the form, or under the `.proof-strip`. `{{ latest.url }}` and `{{ latest.date_display }}` need `latest` passed to the subscribe context in build.py (currently only `index.html` gets it). Fallback: link to `/archive/`.

```html
<p class="subscribe-sample">Not sure yet? <a href="{{ latest.url }}">Read the latest edition ({{ latest.date_display }})</a> first, no sign-up needed.</p>
```

Static fallback if `latest` is not passed:

```html
<p class="subscribe-sample">Not sure yet? <a href="/archive/">Browse past editions</a> first, no sign-up needed.</p>
```

---

## 2. Home H2 block (about 105 words)

Placement: in `templates/index.html`, as a new `.card` right after the "What is Spain Daily?" intro-panel (line ~67) and before "Latest news by topic". The H2 repeats the question people search for.

```html
<div class="card sources-card">
  <h2>Which Spanish newspapers do we read?</h2>
  <p>Spain Daily is a newsletter, not a newspaper. We do not report the news ourselves: every day we read the Spanish press, translate and summarize the stories in English, and link each one to its source. We read El País, Cinco Días, El Mundo, La Vanguardia, elDiario.es, El Confidencial, 20 Minutos, Heraldo, Diario Sur, Expansión and the Europa Press agency. International news makes the cut only when it directly affects Spain. It is <strong>Spanish news in English</strong>, built for the English-language reader who wants the Spanish press without reading it in Spanish.</p>
</div>
```

Notes for this block:
- Source list matches the RSS config; update it if feeds change. Europa Press is a news agency, hence "agency".
- No claims about other English-language outlets. No links, per owner.

---

## 3. Home FAQ (5 Q&As)

Placement: append to `FAQ_ITEMS` in build.py (home renders them in `<details>` and in FAQPage JSON-LD; both use the plain-text answer, so no HTML inside answers). Suggested order: put the three first, so they appear above the existing "What is Spanified?" Items 1-5 below are new; existing 5 items stay.

Python-ready tuples:

```python
    ("Where can I read Spanish news in English?", "On Spain Daily: every morning we publish a free edition with Spain's top stories in plain English, online and by email. Each item links to the original Spanish source, so you can read the full article if you want to."),
    ("Is Spain Daily a newspaper or a newsletter?", "Spain Daily is a newsletter, not a newspaper. We do not do original reporting: we read Spanish outlets, then translate and summarize their stories in English and link to each source. The summaries are AI-assisted and checked by an editor before every send."),
    ("Which Spanish newspapers does Spain Daily summarize?", "Spain Daily reads national and regional Spanish media: El País, Cinco Días, El Mundo, La Vanguardia, elDiario.es, El Confidencial, 20 Minutos, Heraldo, Diario Sur and Expansión, plus the Europa Press agency. International news is included only when it directly affects Spain. Every story shows its source."),
    ("Can Spain Daily replace an English-language newspaper about Spain?", "No, it is meant to sit alongside one. Spain Daily is a five-minute daily briefing with links to the original reporting, so you get the headlines on rents, taxes, visas and jobs fast and can go deeper in the source or in an English-language outlet."),
    ("What is a good English-language newsletter about Spain?", "Spain Daily is a free English-language newsletter about Spain: one email a day, around 08:00 Madrid time, seven days a week, with a five-minute read on the news that affects life in Spain. You can try it by reading the latest edition online before you subscribe."),
```

Fact-check flags for the FAQ:
- Q1: "online and by email" and "free" match existing site text (hero, FAQ "Is it really free?").
- Q2: "no original reporting" confirmed by the owner.
- Q3: names come from the RSS config; "international news only when it directly affects Spain" confirmed by the owner.
- Q4: wording is deliberately non-competitive; names no rival outlet.
- Q5: rewritten from the suggested "best" question. A "best" claim cannot be backed up, so the question says "a good" and the answer states only facts (free, daily, ~08:00 Madrid, 5 minutes). If you keep "best" in the question, the answer must not claim it. "Around 08:00 Madrid time, seven days a week" is copied from the hero.
- None of the answers includes subscriber counts or "only/first/leading" claims.

---

## Open points for seo-specialist

- subscribe.html needs `latest` in its render context (build.py line ~706) for the sample link, or use the `/archive/` fallback.
- No internal links in the new copy (owner decision). FAQ answers stay plain text because FAQPage JSON-LD uses `|tojson` of the string.
- The home H1 and meta description already carry "Spanish news in English"; the new H2 adds "Spanish press" and "English-language", the other two target phrases.
- FAQ now has 10 items; consider whether Q4 is needed (the least search-driven) if you want to keep it at 9 or fewer.
- "Join 500+ readers" is existing site copy; I did not reuse or verify it.
