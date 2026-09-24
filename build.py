#!/usr/bin/env python3
"""
Build script for the Spanified static site (spanified.com).

Reads Jinja2 templates from templates/ and digest JSON files from data/digests/,
and renders a static site:

  - Static pages   -> repo root (index.html, subscribe.html, success.html,
                      confirm.html, unsubscribe.html)
  - Issue pages    -> archive/YYYY-MM-DD.html
  - Archive listing -> archive/index.html + archive/N.html (10 per page)
  - Sitemap        -> sitemap.xml

Usage: python3 build.py [--out dist] [--listmonk local]   (idempotent)

  Local dev against the dev Listmonk instead of prod:
    python3 build.py --listmonk local
  (endpoint + dev list UUID are picked automatically; override with
  --list-uuid or env LISTMONK_URL / LISTMONK_LIST_UUID)
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
from collections import Counter
from datetime import datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(SCRIPT_DIR, "templates")
DATA_DIR = os.path.join(SCRIPT_DIR, "data", "digests")
OUT_DIR = SCRIPT_DIR
ARCHIVE_DIR = os.path.join(OUT_DIR, "archive")

SITE_URL = "https://spanified.com"
PAGE_SIZE = 10

# Listmonk backend for the native subscribe form (templates/partials/
# subscribe-form.html renders these into action / l value).
# The form POSTs urlencoded natively to <base>/api/public/subscription
# (Listmonk public API, which also accepts form-encoded `l`). A Cloudflare
# Worker in front of the endpoint verifies the Turnstile token server-side
# and issues the post-success redirect (Listmonk itself returns JSON here).
# Default is prod; local dev builds pass --listmonk local (or LISTMONK_URL)
# so the browser talks to the dev instance instead of prod.
LISTMONK_PROD_URL = "https://api.spanified.com"
LISTMONK_LOCAL_URL = "https://listmonk.dslab.fyi"
LISTMONK_PROD_LIST_UUID = "d4edf463-70a3-45e5-a964-a39b48c49b2d"
LISTMONK_LOCAL_LIST_UUID = "5dcb6e29-0181-4c55-b68a-705133b53e10"

# Static pages rendered 1:1 from templates.
# Pages listed here are rendered to dist root. NOINDEX_PAGES are still
# rendered (linked from the site) but kept out of sitemap.xml.
NOINDEX_PAGES = {
    "success.html",
    "confirm.html",
    "unsubscribe.html",
    "404.html",
}
STATIC_PAGES = [
    "index.html",
    "subscribe.html",
    "success.html",
    "confirm.html",
    "unsubscribe.html",
    "contact.html",
    "privacy.html",
    "terms.html",
    "editor.html",
    "about.html",
    "search.html",
    "404.html",
]

# Static assets copied verbatim into the output dir (hand-written pages,
# images, domain config, localized pages).
STATIC_COPY = [
    "CNAME",
    "bsky.html",
    "x.html",
    "success.jpg",
    "confirm.jpg",
    "logo.jpg",
    "favicon.ico",
    "favicon.png",
    "apple-touch-icon.png",
    "static",
]

# Category emoji — mirrors format_email.py in spain-news-en.
CATEGORY_EMOJI = {
    "property": "🏠",
    "economy": "💰",
    "politics": "🏛️",
    "work": "👥",
    "visa": "📋",
    "health": "🏥",
    "migration": "🌍",
    "taxes": "📊",
    "events": "📅",
    "housing": "🏘️",
}
DEFAULT_EMOJI = "📰"

# SEO meta titles + descriptions per category (from SEO review, 2026-09-14).
CATEGORY_META = {
    "economy": ("Spain Economy News: Inflation, Jobs & GDP — Spanified", "Spain economy explained for expats: GDP growth, inflation, salaries and Bank of Spain data. Track the numbers that hit your prices and savings."),
    "politics": ("Spanish Politics News: Laws & Elections — Spanified", "Spanish politics without the noise: coalition deals, regional elections, new laws and EU relations. What Madrid decides, explained for residents."),
    "work": ("Jobs in Spain: Workers' Rights, SMI & Hiring — Spanified", "Jobs and labour in Spain: hiring trends, minimum wage (SMI), workers' rights, strikes and workplace reforms. Essential reading for workers."),
    "property": ("Spanish Property: Prices, Mortgages & Rent Caps — Spanified", "Spanish property news in English: house prices by region, rental caps, housing laws and mortgage trends. For buyers, renters and landlords."),
    "events": ("Events in Spain: Holidays, Festivals & Strikes — Spanified", "What's on in Spain: national holidays, festivals, strikes affecting travel, and major cultural moments. Daily life in the country, in brief."),
    "health": ("Healthcare in Spain: SNS News & Waiting Lists — Spanified", "Healthcare in Spain explained: public system (SNS) updates, waiting lists, new treatments and health alerts. Practical news for residents."),
    "taxes": ("Spanish Taxes: IRPF, Renta & Deadlines Explained — Spanified", "Spanish taxes without tears: IRPF brackets, renta and modelo 720 deadlines, deductions and Hacienda reforms. What you owe and when."),
    "visa": ("Spain Visas & Residency: Nomad, NIE & TIE — Spanified", "Visas and residency in Spain: digital nomad permit, Beckham Law, NIE/TIE procedures and immigration rules. The paperwork side, decoded."),
    "housing": ("Renting in Spain: Tenant Rights & Rental Prices — Spanified", "Renting and housing access in Spain: rental prices, tenant rights (LAU), evictions and regional housing plans. What protects you as a tenant."),
    "migration": ("Spain Migration: Arrivals, Policy & Integration — Spanified", "Migration and life between countries: arrivals data, integration policies, consular services and stories of people moving to and from Spain."),
}

# Unique SEO descriptions per category (2-3 sentences each).
CATEGORY_DESCRIPTIONS = {
    "economy": "Spain's economy in plain English: GDP growth, inflation, jobs data, EU funds, and what the Bank of Spain actually says. We track the numbers that affect prices, salaries, and savings — without the jargon.",
    "politics": "Spanish politics without the noise: coalition deals, regional elections, new laws, and EU relations. Short summaries of what was decided in Madrid — and what it means for people living in Spain.",
    "work": "Jobs and labour in Spain: hiring trends, workers' rights, minimum wage (SMI), strikes, and workplace reforms. Essential reading if you work here or plan to.",
    "property": "Spanish property market in English: house prices by region, rental caps, new housing laws, and mortgage trends. For buyers, renters, and landlords watching Spain's bricks.",
    "events": "What's on in Spain: national holidays, festivals, strikes affecting travel, and major cultural and sporting moments. The day-to-day life of the country, in brief.",
    "health": "Healthcare in Spain explained: public system (SNS) updates, waiting lists, new treatments, and public-health alerts. Practical news for residents and newcomers alike.",
    "taxes": "Spanish taxes without tears: IRPF brackets, deadlines (renta, modelo 720), deductions, and reforms from Hacienda. What you owe, when, and what changed this year.",
    "visa": "Visas and residency in Spain: digital nomad permits, Beckham Law, NIE/TIE procedures, and immigration rule changes. The paperwork side of Spanish life, decoded.",
    "housing": "Renting and housing access in Spain: rental prices, tenant rights (LAU), evictions data, and regional housing plans. Where the market is going — and what protects you as a tenant.",
    "migration": "Migration and life between countries: arrivals data, integration policies, consular services, and stories of people moving to and from Spain. The human side of the statistics.",
}


def format_date(date_str):
    """'2026-09-10' -> 'September 10, 2026'."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return f"{dt.strftime('%B')} {dt.day}, {dt.year}"
    except (ValueError, TypeError):
        return date_str


def mercadona_line(date_str):
    """Weekend Mercadona reminder, keyed to the edition's own date."""
    try:
        weekday = datetime.strptime(date_str, "%Y-%m-%d").weekday()
    except (ValueError, TypeError):
        return ""
    if weekday == 5:  # Saturday
        return "🛒 Mercadona is closed tomorrow — stock up your fridge!"
    if weekday == 6:  # Sunday
        return "🛒 Mercadona is closed today, but not everywhere!"
    return ""


def top_categories(items, n=3):
    """Most frequent categories as display strings, e.g. '💰 Economy'."""
    counts = Counter(item.get("category", "") for item in items)
    result = []
    for category, _ in counts.most_common(n):
        if not category:
            continue
        emoji = CATEGORY_EMOJI.get(category, DEFAULT_EMOJI)
        result.append(f"{emoji} {category.capitalize()}")
    return result


def load_digests():
    """Load and sort (newest first) all digest JSON files in data/digests/."""
    digests = []
    if os.path.isdir(DATA_DIR):
        for filename in sorted(os.listdir(DATA_DIR)):
            if not filename.endswith(".json"):
                continue
            path = os.path.join(DATA_DIR, filename)
            try:
                with open(path, encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, json.JSONDecodeError) as exc:
                print(f"WARN: skipping {filename}: {exc}", file=sys.stderr)
                continue
            date = data.get("date") or filename[:-5]
            data["date"] = date
            digests.append(data)
    digests.sort(key=lambda d: d.get("date", ""), reverse=True)
    return digests


def digest_context(data):
    """Normalize a digest dict into the context passed to digest.html."""
    items = data.get("items", [])
    date = data.get("date", "")
    headline = data.get("headline") or data.get("variant") or "Spain Daily Digest"
    words = len(headline.split()) + sum(
        len((i.get("title", "") + " " + i.get("body", "")).split()) for i in items
    )
    tag_cats = [c.capitalize() for c in dict.fromkeys(
        i.get("category", "") for i in items if i.get("category"))][:3]
    return {
        "date": date,
        "date_display": format_date(date),
        "headline": headline,
        "stories": items,
        "mercadona": mercadona_line(date),
        "story_count": len(items),
        "top_categories": top_categories(items),
        "url": f"/archive/{date}",
        "meta_description": digest_meta_description(date, headline, items),
        "word_count": words,
        "tag_categories": tag_cats,
    }


def digest_meta_description(date, headline, items):
    """Unique per-day description: headline plus the top two story titles.

    Falls back to the generic blurb when a digest has no items. Capped at
    ~155 chars so Google shows it whole in the snippet.
    """
    topics = [i.get("title", "").strip() for i in items[:2]]
    topics = [t for t in topics if t]
    if topics:
        desc = f"{headline}: " + " — ".join(topics)
    else:
        desc = f"Spain Daily Digest for {date} — the day's top news from Spain, summarized in English."
    return desc if len(desc) <= 157 else desc[:154].rsplit(" ", 1)[0] + "…"


def archive_url(page):
    if page == 1:
        return "/archive/"
    return f"/archive/{page}"


def pagination(page, total_pages):
    # Compact window: current + up to 2 neighbours each side (max 5 numbers).
    # Near the edges the window shifts so it stays full when possible.
    start = min(max(page - 2, 1), max(total_pages - 4, 1))
    end = min(start + 4, total_pages)
    return {
        "current": page,
        "total_pages": total_pages,
        "prev_url": archive_url(page - 1) if page > 1 else None,
        "next_url": archive_url(page + 1) if page < total_pages else None,
        "pages": [
            {"number": p, "url": archive_url(p), "current": p == page}
            for p in range(start, end + 1)
        ],
    }


def load_social_stats():
    """Load social stats from data/social_stats.json with safe defaults."""
    try:
        path = os.path.join(SCRIPT_DIR, "data", "social_stats.json")
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {"threads_followers": 4100, "reddit_members": 1000}


def load_testimonials():
    """Load testimonials from data/testimonials.json.

    Avatar files live in static/img/avatars/ and are wired into the
    template directly via ``avatar_url``.
    """
    try:
        path = os.path.join(SCRIPT_DIR, "data", "testimonials.json")
        with open(path, encoding="utf-8") as fh:
            testimonials = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return []
    for t in testimonials:
        t["avatar_url"] = f"/static/img/avatars/{t.get('avatar')}"
    return testimonials


FAQ_ITEMS = [
    ("What is Spanified?", "Spanified is a free newsletter that summarizes the most important news from Spain in plain English — rents, taxes, visas, jobs and everyday life."),
    ("How often does the digest arrive?", "Every morning, seven days a week. Five minutes with your coffee and you're up to speed."),
    ("Is it really free?", "Yes — free forever. No paywall, no trial, just the news."),
    ("What language is it in?", "The summaries are written in clear English, based on the Spanish press we read cover to cover each morning."),
    ("Where can I read past editions?", "Every edition stays online in the archive — browse by date or search the whole history."),
]


def render_llms_txt(digests):
    latest = digests[0]["date"] if digests else "n/a"
    lines = [
        "# Spanified — Spain Daily",
        "> A free newsletter summarizing the most important news from Spain in plain English. Every morning, 5-minute read.",
        "",
        f"Latest edition: {latest}",
        "",
        "## Key pages",
        f"- Home: {SITE_URL}/",
        f"- Archive (all editions): {SITE_URL}/archive/",
        f"- Search (newest first): {SITE_URL}/search",
        f"- About & methodology: {SITE_URL}/about",
        f"- Editor: {SITE_URL}/editor",
        f"- Subscribe: {SITE_URL}/subscribe",
        "",
        "## How to cite",
        "- Link editions as {SITE_URL}/archive/<YYYY-MM-DD>#news-<N>.",
        "- Publisher: Spanified. Editor: Dmytro Shvechikov.",
        "",
        "## Topics",
        "- property, economy, politics, work, visa, health, migration, taxes, events",
    ]
    dest = os.path.join(OUT_DIR, "llms.txt")
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("  wrote llms.txt")


def render_static(env, digests):
    latest = digests[0] if digests else None
    topics = [
        {"emoji": emoji, "name": category.capitalize(), "slug": category.lower()}
        for category, emoji in CATEGORY_EMOJI.items()
    ]

    # --- social proof -------------------------------------------------------
    social = load_social_stats()
    testimonials = load_testimonials()
    total_issues = len(digests)
    if digests:
        first_issue = format_date(digests[-1]["date"])
    else:
        first_issue = ""
    threads_n = social.get("threads_followers", 4100)
    reddit_n = social.get("reddit_members", 1000)
    proof = {
        "total_issues": total_issues,
        "first_issue": first_issue,
        "threads": threads_n,
        "reddit": reddit_n,
        "threads_display": f"{threads_n:,}",
        "reddit_display": f"{reddit_n:,}",
        "testimonials": testimonials,
    }

    contexts = {
        "index.html": {"latest": latest, "topics": topics, "emoji": CATEGORY_EMOJI, "faq": FAQ_ITEMS, "proof": proof},
        "about.html": {"crumbs": [{"name": "Home", "url": "/"}, {"name": "About", "url": "/about", "current": True}]},
        "contact.html": {"crumbs": [{"name": "Home", "url": "/"}, {"name": "Contact", "url": "/contact", "current": True}]},
        "editor.html": {"crumbs": [{"name": "Home", "url": "/"}, {"name": "Editor", "url": "/editor", "current": True}]},
        "subscribe.html": {"crumbs": [{"name": "Home", "url": "/"}, {"name": "Subscribe", "url": "/subscribe", "current": True}], "proof": proof, "js_version": js_version()},
        "unsubscribe.html": {"crumbs": [{"name": "Home", "url": "/"}, {"name": "Unsubscribe", "url": "/unsubscribe", "current": True}]},
        "confirm.html": {"crumbs": [{"name": "Home", "url": "/"}, {"name": "Confirm", "url": "/confirm", "current": True}]},
        "search.html": {"crumbs": [{"name": "Home", "url": "/"}, {"name": "Search", "url": "/search", "current": True}]},
        "success.html": {"crumbs": [{"name": "Home", "url": "/"}, {"name": "Success", "url": "/success", "current": True}]},
        "404.html": {"crumbs": [{"name": "Home", "url": "/"}, {"name": "Not found", "url": "/404", "current": True}]},
    }
    for name in STATIC_PAGES:
        template = env.get_template(name)
        output = template.render(**contexts.get(name, {}))
        dest = os.path.join(OUT_DIR, name)
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(output)
        print(f"  wrote {name}")
    render_calculators(env)
    render_quizzes(env)


def render_calculators(env):
    """Render calculator pages (static shell, logic runs client-side)."""
    calcs = [
        ("calculator-autonomo.html", "calculators/autonomo-tax.html", [
            {"name": "Home", "url": "/"},
            {"name": "Autónomo Tax", "url": "/calculators/autonomo-tax", "current": True},
        ], "Autónomo Tax Calculator — Spain self-employed taxes — Spanified"),
        ("calculator-property-buying-cost.html", "calculators/property-buying-cost.html", [
            {"name": "Home", "url": "/"},
            {"name": "Property Buying Cost", "url": "/calculators/property-buying-cost", "current": True},
        ], "Spain Property Buying Cost Calculator — ITP, IVA/IGIC & AJD by region — Spanified"),
    ]
    for template_name, rel_dest, crumbs, share_text in calcs:
        template = env.get_template(template_name)
        calc_url = f"{SITE_URL}/{rel_dest.replace('.html', '')}"
        share = share_links(calc_url, share_text)
        # Fiscal year of the calculator data (SS quotas, IRPF scales). Bump ONLY
        # together with the engine data (quotas/brackets/deductions), never alone.
        calc_year = 2026
        output = template.render(crumbs=crumbs, js_version=js_version(), share=share, calc_year=calc_year)
        dest = os.path.join(OUT_DIR, rel_dest)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(output)
        print(f"  wrote {rel_dest}")


def render_quizzes(env):
    """Render quiz pages from data/quizzes/*.json (multi-quiz ready).

    Per quiz <slug>: quiz/<slug>.html (app), quiz/<slug>-subscribed.html
    (legacy Brevo confirmation snippet, kept for old links, noindex),
    quiz/<slug>-success.html (post double-opt-in page, noindex),
    quiz/<slug>-result-<persona>.html (per-persona share landing, noindex
    until launch). Quiz pages stay out of the sitemap until launch
    (see render_sitemap).
    """
    import json as _json

    quizzes_dir = os.path.join(SCRIPT_DIR, "data", "quizzes")
    if not os.path.isdir(quizzes_dir):
        return
    for name in sorted(os.listdir(quizzes_dir)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(quizzes_dir, name), encoding="utf-8") as fh:
            quiz = _json.load(fh)
        slug = quiz["slug"]
        quiz_json = _json.dumps(quiz)
        base = f"{SITE_URL}/quiz/{slug}"
        share = share_links(
            base,
            f"{quiz['title']} — Spanified",
            f"{quiz['title']} — can you tell real Spanish news from AI fakes? "
            "10 wild headlines, 2 minutes. Take the quiz:",
        )
        crumbs = [
            {"name": "Home", "url": "/"},
            {"name": "Quiz", "url": f"/quiz/{slug}", "current": True},
        ]
        ctx = dict(
            quiz=quiz, quiz_json=quiz_json, crumbs=crumbs,
            js_version=js_version(), share=share,
        )
        pages = [
            ("quiz.html", f"quiz/{slug}.html"),
            ("quiz-subscribed.html", f"quiz/{slug}-subscribed.html"),
            ("quiz-success.html", f"quiz/{slug}-success.html"),
        ]
        for template_name, rel_dest in pages:
            output = env.get_template(template_name).render(**ctx)
            dest = os.path.join(OUT_DIR, rel_dest)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w", encoding="utf-8") as out:
                out.write(output)
            print(f"  wrote {rel_dest}")

        # Per-persona share landing pages (static, OG-scrapeable).
        result_template = env.get_template("quiz-result.html")
        for result in quiz.get("results", []):
            result_url = f"{SITE_URL}/quiz/{slug}-result-{result['slug']}"
            share_text = result.get('shareText', f"{result['title']} — {quiz['title']} — Spanified")
            first_para = (result.get('text') or '').split('\n\n')[0].strip()
            share_long = f"{share_text}\n\n{first_para}" if first_para else share_text
            result_share = share_links(result_url, share_text, share_long)
            result_ctx = dict(
                quiz=quiz,
                result=result,
                all_results=quiz.get("results", []),
                friend_score=None,
                share=result_share,
                crumbs=crumbs,
            )
            dest_path = f"quiz/{slug}-result-{result['slug']}.html"
            output = result_template.render(**result_ctx)
            dest = os.path.join(OUT_DIR, dest_path)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w", encoding="utf-8") as out:
                out.write(output)
            print(f"  wrote {dest_path}")
def attach_related(digests, limit=3):
    """Attach same-category 'More news' links to every story.

    Only stories from strictly older digests (newest first,
    /archive/<date>#news-N). Same-digest siblings are excluded.
    Within one digest, links are dealt out without repetition: if two
    stories share a category, the second one gets the next batch,
    reaching deeper into the archive.
    Stories with no same-category peers get an empty list (block not rendered).
    """
    for i, digest in enumerate(digests):
        stories = digest.get("stories", [])
        used = set()  # urls already dealt out within this digest
        for pos, item in enumerate(stories, start=1):
            cat = (item.get("category") or "").lower()
            if not cat:
                item["related"] = []
                continue
            related = []
            # Only older digests (list is newest-first), newest first.
            for older in digests[i + 1:]:
                for k, other in enumerate(older.get("stories", []), start=1):
                    if (other.get("category") or "").lower() != cat:
                        continue
                    title = other.get("title", "")
                    if not title:
                        continue
                    url = f"{older['url']}#news-{k}"
                    if url in used:
                        continue
                    related.append({"title": title, "url": url})
                    if len(related) >= limit:
                        break
                if len(related) >= limit:
                    break
            item["related"] = related[:limit]
            used.update(r["url"] for r in item["related"])


def share_links(abs_url, text, long_text=None):
    """Build static share URLs (no JS SDKs) for X/TG/WA/FB + copy link.

    X keeps the short text (280-char limit); Telegram/WhatsApp get
    long_text when provided (falls back to text). Facebook ``quote``
    carries long_text — FB scrapes OG tags by default, but ``quote``
    sometimes surfaces as pre-filled text for manual posting."""
    u, t = quote(abs_url, safe=""), quote(text, safe="")
    tl = quote(long_text or text, safe="")
    return {
        "url": abs_url,
        "x": f"https://x.com/intent/tweet?text={t}&url={u}",
        "facebook": f"https://www.facebook.com/sharer/sharer.php?u={u}&quote={tl}",
        "telegram": f"https://t.me/share/url?url={u}&text={tl}",
        "whatsapp": f"https://wa.me/?text={tl}%20{u}",
    }


def attach_share(digests):
    """Attach page-level + per-story share links (absolute URLs)."""
    for digest in digests:
        page_url = f"{SITE_URL}{digest['url']}"
        digest["share"] = share_links(
            page_url, f"{digest['headline']} — Spain Daily Digest")
        for pos, item in enumerate(digest.get("stories", []), start=1):
            abs_url = f"{page_url}#news-{pos}"
            item["share"] = share_links(
                abs_url, f"{item.get('title', '')} — via Spanified")


def render_digests(env, digests):
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    # Clear previously generated HTML inside archive/ so removed digests don't linger.
    for filename in os.listdir(ARCHIVE_DIR):
        if filename.endswith(".html"):
            os.remove(os.path.join(ARCHIVE_DIR, filename))

    template = env.get_template("digest.html")
    for i, digest in enumerate(digests):
        crumbs = [
            {"name": "Home", "url": "/"},
            {"name": "Archive", "url": "/archive/"},
            {"name": digest["date_display"], "url": digest["url"], "current": True},
        ]
        # digests is newest-first: i-1 is the newer day, i+1 the older day.
        older = digests[i + 1] if i + 1 < len(digests) else None
        newer = digests[i - 1] if i > 0 else None
        day_nav = {
            "older": {"url": older["url"], "date_display": older["date_display"]} if older else None,
            "newer": {"url": newer["url"], "date_display": newer["date_display"]} if newer else None,
        }
        output = template.render(digest=digest, emoji=CATEGORY_EMOJI, crumbs=crumbs, day_nav=day_nav)
        dest = os.path.join(ARCHIVE_DIR, f"{digest['date']}.html")
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(output)
        print(f"  wrote archive/{digest['date']}.html")


def render_archive(env, digests):
    total = len(digests)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE) if total else 1
    template = env.get_template("archive.html")

    for page in range(1, total_pages + 1):
        start = (page - 1) * PAGE_SIZE
        page_digests = digests[start:start + PAGE_SIZE]
        crumbs = [{"name": "Home", "url": "/"}]
        if page == 1:
            crumbs.append({"name": "Archive", "url": "/archive/", "current": True})
        else:
            crumbs.append({"name": "Archive", "url": "/archive/"})
            crumbs.append({"name": f"Page {page}", "url": f"/archive/{page}", "current": True})
        output = template.render(digests=page_digests, pagination=pagination(page, total_pages), crumbs=crumbs)
        dest = os.path.join(ARCHIVE_DIR, "index.html" if page == 1 else f"{page}.html")
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(output)
        print(f"  wrote {'archive/index.html' if page == 1 else f'archive/{page}.html'}")


def collect_categories(digests):
    """Group all stories by category slug (newest digest first)."""
    cats = {}
    for digest in digests:
        for item in digest.get("stories", []):
            slug = (item.get("category") or "news").lower()
            cats.setdefault(slug, []).append({**item, "date": digest["date"], "date_display": digest["date_display"]})
    return cats


def render_categories(env, digests):
    cats = collect_categories(digests)
    cat_dir = os.path.join(OUT_DIR, "category")
    os.makedirs(cat_dir, exist_ok=True)
    # Clear previously generated pages so removed categories don't linger.
    for filename in os.listdir(cat_dir):
        if filename.endswith(".html"):
            os.remove(os.path.join(cat_dir, filename))

    template = env.get_template("category.html")
    for slug, stories in sorted(cats.items()):
        name = slug.capitalize()
        crumbs = [
            {"name": "Home", "url": "/"},
            {"name": name, "url": f"/category/{slug}", "current": True},
        ]
        meta_title, meta_desc = CATEGORY_META.get(slug, (name + " News in Spain, in English — Spanified", ""))
        output = template.render(
            category_name=name,
            slug=slug,
            emoji=CATEGORY_EMOJI.get(slug, "\U0001F4F0"),
            category_description=CATEGORY_DESCRIPTIONS.get(slug, ""),
            meta_title=meta_title,
            meta_description=meta_desc,
            stories=stories,
            crumbs=crumbs,
        )
        dest = os.path.join(cat_dir, f"{slug}.html")
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(output)
        print(f"  wrote category/{slug}.html ({len(stories)} stories)")
    return sorted(cats.keys())


def render_sitemap(digests, categories=()):
    urls = [(SITE_URL + "/", None)] + [
        (SITE_URL + "/" + name[:-len(".html")], None)
        for name in STATIC_PAGES
        if name.endswith(".html") and name != "index.html" and name not in NOINDEX_PAGES
    ]
    # Archive listing (page 1) plus extra pages.
    total = len(digests)
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE if total else 1
    urls.append((SITE_URL + "/archive/", None))
    for page in range(2, total_pages + 1):
        urls.append((SITE_URL + f"/archive/{page}", None))
    for digest in digests:
        urls.append((SITE_URL + f"/archive/{digest['date']}", digest["date"]))
    for slug in categories:
        urls.append((SITE_URL + f"/category/{slug}", None))
    urls.append((SITE_URL + "/calculators/autonomo-tax", None))
    urls.append((SITE_URL + "/calculators/property-buying-cost", None))
    # Quiz pages stay out of the sitemap until launch (no external links either).

    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    lines.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    for url, lastmod in urls:
        if lastmod:
            lines.append(f"  <url><loc>{url}</loc><lastmod>{lastmod}</lastmod></url>")
        else:
            lines.append(f"  <url><loc>{url}</loc></url>")
    lines.append("</urlset>")

    dest = os.path.join(OUT_DIR, "sitemap.xml")
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"  wrote sitemap.xml ({len(urls)} urls)")


def parse_args():
    parser = argparse.ArgumentParser(description="Build the Spanified static site.")
    parser.add_argument(
        "--out",
        default=SCRIPT_DIR,
        help="Output directory (default: repo root, for local preview). "
        "CI uses --out dist.",
    )
    parser.add_argument(
        "--listmonk",
        default=os.environ.get("LISTMONK_URL", "prod"),
        help="Listmonk backend for the subscribe form: 'prod' (default, "
        "https://api.spanified.com), 'local' (dev instance, "
        "https://listmonk.dslab.fyi), or a custom base URL. "
        "Env LISTMONK_URL overrides the default.",
    )
    parser.add_argument(
        "--list-uuid",
        default=os.environ.get("LISTMONK_LIST_UUID"),
        help="Listmonk list UUID for the subscribe form (default: prod "
        "Spain Daily list, or the dev list with --listmonk local). "
        "Env LISTMONK_LIST_UUID overrides.",
    )
    return parser.parse_args()


def listmonk_form_action(listmonk):
    """Resolve the --listmonk value to the Listmonk public API route."""
    base = {"prod": LISTMONK_PROD_URL, "local": LISTMONK_LOCAL_URL}.get(
        listmonk, listmonk)
    return base.rstrip("/") + "/api/public/subscription"


def listmonk_list_uuid(args):
    """Resolve the list UUID: explicit --list-uuid wins, otherwise per mode."""
    if args.list_uuid:
        return args.list_uuid
    if args.listmonk == "local":
        return LISTMONK_LOCAL_LIST_UUID
    return LISTMONK_PROD_LIST_UUID


def copy_static(out_dir):
    for name in STATIC_COPY:
        src = os.path.join(SCRIPT_DIR, name)
        if not os.path.exists(src):
            print(f"WARN: static asset missing, skipping: {name}", file=sys.stderr)
            continue
        dest = os.path.join(out_dir, name)
        if os.path.exists(dest) and os.path.samefile(src, dest):
            print(f"  kept {name} (build in place)")
            continue
        if os.path.isdir(src):
            shutil.copytree(src, dest, dirs_exist_ok=True)
        else:
            os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
            shutil.copy2(src, dest)
        print(f"  copied {name}")


def pub_date(date_str):
    """Full ISO 8601 with Europe/Madrid offset for schema.org datetimes.

    The digest goes out in the morning; DST offset resolves itself
    (+02:00 summer, +01:00 winter). Falls back to the raw string."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").replace(
            hour=8, tzinfo=ZoneInfo("Europe/Madrid")
        ).isoformat()
    except (ValueError, TypeError):
        return date_str


def css_version():
    """Short content hash of main.css for cache-busting (?v=...)."""
    path = os.path.join(SCRIPT_DIR, "static", "css", "main.css")
    try:
        with open(path, "rb") as fh:
            return hashlib.md5(fh.read()).hexdigest()[:8]
    except OSError:
        return "dev"


def js_version():
    """Short content hash of calculator JS bundle for cache-busting."""
    h = hashlib.md5()
    for name in ("autonomo.js", "autonomo-calc.js", "autonomo-form.js",
                   "property-buying-cost.js", "property-buying-cost-calc.js",
                   "property-buying-cost-form.js", "quiz-ai-or-real.js",
                   "quiz-logic.js", "subscribe-form.js", "subscription-store.js"):
        path = os.path.join(SCRIPT_DIR, "static", "js", name)
        try:
            with open(path, "rb") as fh:
                h.update(fh.read())
        except OSError:
            pass
    return h.hexdigest()[:8] or "dev"


def main():
    args = parse_args()
    out_dir = os.path.abspath(args.out)
    archive_dir = os.path.join(out_dir, "archive")
    os.makedirs(archive_dir, exist_ok=True)

    # Rebind module-level outputs when building into a custom dir.
    global OUT_DIR, ARCHIVE_DIR
    OUT_DIR = out_dir
    ARCHIVE_DIR = archive_dir

    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=True,
    )
    env.globals["current_year"] = datetime.now().year
    env.globals["asset_version"] = css_version()
    env.globals["site_url"] = SITE_URL
    env.globals["listmonk_form_action"] = listmonk_form_action(args.listmonk)
    env.globals["listmonk_list_uuid"] = listmonk_list_uuid(args)
    # Captcha (Cloudflare Turnstile via Worker) only exists in front of the
    # prod API. Local builds post straight at the dev Listmonk — no Worker,
    # so no widget is rendered and the JS token check is skipped.
    env.globals["turnstile_enabled"] = args.listmonk != "local"
    env.globals["pub_date"] = pub_date
    env.globals["site_socials"] = [
        "https://www.threads.com/@spaindaily",
        "https://bsky.app/profile/spanified.bsky.social",
        "https://www.reddit.com/r/SpainDaily/",
        "https://x.com/spanified",
        "https://substack.com/@spanified",
        "https://www.facebook.com/spanified",
    ]

    digests = [digest_context(d) for d in load_digests()]

    print("Copying static assets...")
    copy_static(out_dir)

    print("Building static pages...")
    render_static(env, digests)

    print(f"Building {len(digests)} digest page(s)...")
    attach_related(digests)
    attach_share(digests)
    render_digests(env, digests)

    print("Rendering OG images...")
    from og_images import render_og_images
    render_og_images(digests, out_dir)

    print("Building archive listing...")
    render_archive(env, digests)

    print("Building category pages...")
    categories = render_categories(env, digests)

    print("Building sitemap...")
    render_sitemap(digests, categories)

    print("Writing llms.txt...")
    render_llms_txt(digests)

    print("Done.")


if __name__ == "__main__":
    main()
