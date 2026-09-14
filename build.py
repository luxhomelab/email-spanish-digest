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

Usage: python3 build.py [--out dist]   (idempotent)
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
}
DEFAULT_EMOJI = "📰"


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
    contexts = {
        "index.html": {"latest": latest, "topics": topics, "emoji": CATEGORY_EMOJI, "faq": FAQ_ITEMS},
        "about.html": {"crumbs": [{"name": "Home", "url": "/"}, {"name": "About", "url": "/about", "current": True}]},
        "contact.html": {"crumbs": [{"name": "Home", "url": "/"}, {"name": "Contact", "url": "/contact", "current": True}]},
        "editor.html": {"crumbs": [{"name": "Home", "url": "/"}, {"name": "Editor", "url": "/editor", "current": True}]},
        "subscribe.html": {"crumbs": [{"name": "Home", "url": "/"}, {"name": "Subscribe", "url": "/subscribe", "current": True}]},
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


def share_links(abs_url, text):
    """Build static share URLs (no JS SDKs) for X/TG/WA/FB + copy link."""
    u, t = quote(abs_url, safe=""), quote(text, safe="")
    return {
        "url": abs_url,
        "x": f"https://x.com/intent/tweet?text={t}&url={u}",
        "facebook": f"https://www.facebook.com/sharer/sharer.php?u={u}",
        "telegram": f"https://t.me/share/url?url={u}&text={t}",
        "whatsapp": f"https://wa.me/?text={t}%20{u}",
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
        output = template.render(
            category_name=name,
            slug=slug,
            emoji=CATEGORY_EMOJI.get(slug, "\U0001F4F0"),
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
    return parser.parse_args()


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
    env.globals["pub_date"] = pub_date
    env.globals["site_socials"] = [
        "https://www.threads.com/@spaindaily",
        "https://bsky.app/profile/spanified.bsky.social",
        "https://www.reddit.com/r/SpainDaily/",
        "https://x.com/spanified",
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
