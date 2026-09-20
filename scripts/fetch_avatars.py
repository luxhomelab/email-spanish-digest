#!/usr/bin/env python3
"""Fetch Reddit user avatars into static/img/avatars/.

Maps data/testimonials.json entries (by `avatar` filename) to Reddit
usernames (by `author`, e.g. "u/esccbeta") and downloads each user's
current icon via the public about.json endpoint.

- Stdlib only (+ optional Pillow for downscaling to 96px).
- Idempotent: skips users whose avatar file already exists.
- Graceful: any failure (403, network, parse) is a WARN, exit code
  stays 0 so CI keeps building with initial-letter fallbacks.

Usage: python3 scripts/fetch_avatars.py
"""

import html
import io
import json
import os
import sys
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(SCRIPT_DIR, "data", "testimonials.json")
AVATAR_DIR = os.path.join(SCRIPT_DIR, "static", "img", "avatars")
UA = "SpanifiedAvatarBot/1.0 (by u/spanified; contact support@spanified.com)"


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def download(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read()


def maybe_resize(raw):
    """Downscale to 96x96 PNG when Pillow is available, else raw bytes."""
    try:
        from PIL import Image
    except ImportError:
        return raw
    img = Image.open(io.BytesIO(raw)).convert("RGBA")
    img.thumbnail((96, 96), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def main():
    try:
        with open(DATA_PATH, encoding="utf-8") as fh:
            testimonials = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"WARN: cannot read {DATA_PATH}: {exc}", file=sys.stderr)
        return

    os.makedirs(AVATAR_DIR, exist_ok=True)
    for t in testimonials:
        filename = t.get("avatar")
        author = (t.get("author") or "").lstrip("u/")
        if not filename or not author:
            continue
        dest = os.path.join(AVATAR_DIR, filename)
        if os.path.exists(dest):
            print(f"  kept {filename} (already fetched)")
            continue
        try:
            data = fetch_json(
                f"https://www.reddit.com/user/{author}/about.json"
            ).get("data", {})
            icon = html.unescape(data.get("icon_img") or "")
            icon = icon.split("?")[0].strip()
            if not icon:
                raise ValueError("empty icon_img")
            with open(dest, "wb") as fh:
                fh.write(maybe_resize(download(icon)))
            print(f"  fetched {filename} <- {author}")
        except Exception as exc:  # noqa: BLE001 - graceful by design
            print(f"WARN: avatar for {author}: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
