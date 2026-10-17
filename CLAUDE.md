# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Static site for [spanified.com](https://spanified.com) (Spain Daily newsletter). A single Python script, `build.py`, renders Jinja2 templates plus content in `data/` into plain HTML. Deployed to GitHub Pages by `.github/workflows/deploy.yml` on push to `main`.

## Commands

```bash
pip install jinja2 pillow       # build deps (CI uses the same, plus Python 3.12)
python3 build.py                # build in place (prod Listmonk); idempotent, no required args
python3 build.py --out dist     # what CI runs; CI then runs `npx pagefind --site dist`
python3 build.py --listmonk local   # point subscribe forms at the dev Listmonk
python3 serve.py [port]         # local server with clean URLs (/quiz/ai-or-real); don't use http.server
npm test                        # node --test tests/*.test.js (JS logic for calculators, quizzes, forms)
node --test tests/quiz-logic.test.js   # single JS test file
python3 -m pytest test_refresh_social_stats.py   # Python test (social stats script)
```

## Architecture

- `build.py` (large, single file) loads three content sources and renders everything: `data/digests/*.json` (one newsletter edition per `YYYY-MM-DD.json`), `data/articles/*.md` (custom markdown parser with FAQ extraction, in `build.py`), and quiz/calculator definitions. Outputs: root pages, `archive/`, `articles/`, `category/`, `quiz/`, `calculators/`, `sitemap.xml`, `llms.txt`.
- `templates/` holds all page templates; `base.html` is the shared layout and `partials/` has header/footer/forms.
- `static/js/` holds browser JS. The `*-calc.js` / `quiz-logic.js` / `subscription-store.js` files are pure logic modules that `tests/*.test.js` import; the others wire them to the DOM.
- The subscribe form posts natively to Listmonk (via a Cloudflare Worker that verifies Turnstile); URL and list UUID are chosen by `--listmonk` or the `LISTMONK_URL` / `LISTMONK_LIST_UUID` env vars.
- `og_images.py` and `refresh_social_stats.py` are helper scripts that generate OG images and social stats data used by the build.

## Gotchas

- Generated output is gitignored (root `index.html` etc., `archive/`, `articles/`, `category/`, `quiz/`, `calculators/`, `sitemap.xml`, `llms.txt`, `dist/`, `og/`). Only edit sources: `templates/`, `data/`, `static/`, `build.py`. Parts of the README still describe generated files as committed; trust `.gitignore`.
- `CNAME`, `x.html`, and `ru/` are maintained by hand; leave them alone.
- Publishing a digest: copy the pipeline's `digest.json` to `data/digests/<edition-date>.json`, run the build, and commit through a branch + PR (never directly to `main`). The build reads `date`, `headline` (falls back to `variant`), `items`, and `category`/`important`/`sources`; the weekend Mercadona line derives from the edition date.
