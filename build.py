#!/usr/bin/env python3
"""
Build script for the Spanified static site (spanified.com).

Reads Jinja2 templates from templates/ and digest JSON files from data/digests/,
and renders a static site:

  - Static pages   -> repo root (index.html, subscribe.html, success.html,
                      confirm.html, unsubscribe.html)
  - Issue pages    -> archive/YYYY-MM-DD.html
  - Archive listing -> archive/index.html + archive/page-N.html (10 per page)
  - Sitemap        -> sitemap.xml

Usage: python3 build.py [--out dist]   (idempotent)
"""

import argparse
import json
import os
import shutil
import sys
from collections import Counter
from datetime import datetime

from jinja2 import Environment, FileSystemLoader

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(SCRIPT_DIR, "templates")
DATA_DIR = os.path.join(SCRIPT_DIR, "data", "digests")
OUT_DIR = SCRIPT_DIR
ARCHIVE_DIR = os.path.join(OUT_DIR, "archive")

SITE_URL = "https://spanified.com"
PAGE_SIZE = 10

# Static pages rendered 1:1 from templates.
STATIC_PAGES = [
    "index.html",
    "subscribe.html",
    "success.html",
    "confirm.html",
    "unsubscribe.html",
]

# Static assets copied verbatim into the output dir (hand-written pages,
# images, domain config, localized pages).
STATIC_COPY = [
    "CNAME",
    "bsky.html",
    "x.html",
    "success.jpg",
    "confirm.jpg",
    "ru",
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


def issue_context(data):
    """Normalize a digest dict into the context passed to issue.html."""
    items = data.get("items", [])
    date = data.get("date", "")
    headline = data.get("headline") or data.get("variant") or "Spain Daily Digest"
    return {
        "date": date,
        "date_display": format_date(date),
        "headline": headline,
        "stories": items,
        "mercadona": mercadona_line(date),
        "story_count": len(items),
        "top_categories": top_categories(items),
        "url": f"/archive/{date}.html",
    }


def archive_url(page):
    if page == 1:
        return "/archive/"
    return f"/archive/page-{page}.html"


def pagination(page, total_pages):
    return {
        "current": page,
        "total_pages": total_pages,
        "prev_url": archive_url(page - 1) if page > 1 else None,
        "next_url": archive_url(page + 1) if page < total_pages else None,
        "pages": [
            {"number": p, "url": archive_url(p), "current": p == page}
            for p in range(1, total_pages + 1)
        ],
    }


def render_static(env):
    for name in STATIC_PAGES:
        template = env.get_template(name)
        output = template.render()
        dest = os.path.join(OUT_DIR, name)
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(output)
        print(f"  wrote {name}")


def render_issues(env, issues):
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    # Clear previously generated HTML inside archive/ so removed digests don't linger.
    for filename in os.listdir(ARCHIVE_DIR):
        if filename.endswith(".html"):
            os.remove(os.path.join(ARCHIVE_DIR, filename))

    template = env.get_template("issue.html")
    for issue in issues:
        output = template.render(issue=issue, emoji=CATEGORY_EMOJI)
        dest = os.path.join(ARCHIVE_DIR, f"{issue['date']}.html")
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(output)
        print(f"  wrote archive/{issue['date']}.html")


def render_archive(env, issues):
    total = len(issues)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE) if total else 1
    template = env.get_template("archive.html")

    for page in range(1, total_pages + 1):
        start = (page - 1) * PAGE_SIZE
        page_issues = issues[start:start + PAGE_SIZE]
        output = template.render(issues=page_issues, pagination=pagination(page, total_pages))
        dest = os.path.join(ARCHIVE_DIR, "index.html" if page == 1 else f"page-{page}.html")
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(output)
        print(f"  wrote {'archive/index.html' if page == 1 else f'archive/page-{page}.html'}")


def render_sitemap(issues):
    urls = [SITE_URL + "/"] + [SITE_URL + "/" + name for name in STATIC_PAGES]
    # Archive listing (page 1) plus extra pages.
    total = len(issues)
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE if total else 1
    urls.append(SITE_URL + "/archive/")
    for page in range(2, total_pages + 1):
        urls.append(SITE_URL + f"/archive/page-{page}.html")
    for issue in issues:
        urls.append(SITE_URL + f"/archive/{issue['date']}.html")

    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    lines.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    for url in urls:
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
        if os.path.isdir(src):
            shutil.copytree(src, dest, dirs_exist_ok=True)
        else:
            os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
            shutil.copy2(src, dest)
        print(f"  copied {name}")


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

    issues = [issue_context(d) for d in load_digests()]

    print("Copying static assets...")
    copy_static(out_dir)

    print("Building static pages...")
    render_static(env)

    print(f"Building {len(issues)} issue page(s)...")
    render_issues(env, issues)

    print("Building archive listing...")
    render_archive(env, issues)

    print("Building sitemap...")
    render_sitemap(issues)

    print("Done.")


if __name__ == "__main__":
    main()
