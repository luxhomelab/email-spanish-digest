#!/usr/bin/env python3
"""OG preview images for Spanified (1200x630 PNG, Pillow only).

Generated at build time into <out_dir>/og/:
  - YYYY-MM-DD.png per digest (kicker, date, headline, top-3 stories)
  - og-default.png fallback for the homepage and static pages

Fonts: DejaVu Sans (preinstalled on Debian/Ubuntu incl. CI runners).
Falls back to Pillow's built-in bitmap font if DejaVu is missing.
"""

import os
import re
import textwrap

from PIL import Image, ImageDraw, ImageFont

# DejaVu has no emoji glyphs — strip them so they don't render as tofu boxes.
EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D\u2640\u2642\u2690-\u2699]",
    flags=re.UNICODE,
)


def _strip_emoji(text):
    return EMOJI_RE.sub("", text).strip()

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

W, H = 1200, 630
CREAM = (255, 253, 248)
INK = (60, 72, 88)
RED = (170, 21, 27)
GOLD = (241, 191, 0)
MUTED = (108, 122, 137)

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

_font_cache = {}


def _font(bold, size):
    key = (bold, size)
    if key not in _font_cache:
        path = FONT_BOLD if bold else FONT_REGULAR
        try:
            _font_cache[key] = ImageFont.truetype(path, size)
        except OSError:
            _font_cache[key] = ImageFont.load_default()
    return _font_cache[key]


def _draw_letterspaced(draw, xy, text, font, fill, tracking=3):
    """Draw text with manual letter tracking (Pillow has no CSS letter-spacing)."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += int(draw.textlength(ch, font=font)) + tracking
    return x


def _fit_text(draw, text, font_sizes, max_width, bold=True, wrap_width=32):
    """Pick the largest font size that fits the wrapped text within max_width."""
    for size in font_sizes:
        font = _font(bold, size)
        lines = []
        for para in text.split("\n"):
            lines += textwrap.wrap(para, width=wrap_width) or [""]
        if all(draw.textlength(line, font=font) <= max_width for line in lines):
            return font, lines
    font = _font(bold, font_sizes[-1])
    lines = []
    for para in text.split("\n"):
        lines += textwrap.wrap(para, width=wrap_width) or [""]
    return font, lines


def render_digest_card(date_display, headline, stories):
    """Render a 1200x630 OG card. stories: list of up to 3 titles."""
    headline = _strip_emoji(headline)
    stories = [_strip_emoji(t) for t in (stories or [])]
    img = Image.new("RGB", (W, H), CREAM)
    draw = ImageDraw.Draw(img)

    # Kicker
    _draw_letterspaced(draw, (80, 64), "SPAIN DAILY", _font(True, 30), RED, tracking=6)

    # Date
    date_font = _font(True, 72)
    draw.text((76, 110), date_display, font=date_font, fill=INK)

    # Headline (auto-shrink)
    font, lines = _fit_text(draw, headline, [46, 40, 34, 28], max_width=W - 160)
    y = 210
    line_h = int(font.size * 1.25)
    for line in lines[:3]:
        draw.text((80, y), line, font=font, fill=INK)
        y += line_h

    # Red/gold divider
    y_div = y + 14
    draw.rectangle([80, y_div, 200, y_div + 5], fill=RED)
    draw.rectangle([200, y_div, 280, y_div + 5], fill=GOLD)

    # Top stories
    y_story = y_div + 28
    story_font = _font(False, 26)
    for title in (stories or [])[:3]:
        wrapped = textwrap.wrap(title, width=56)
        line = wrapped[0] + ("…" if len(wrapped) > 1 else "")
        if draw.textlength("•  " + line, font=story_font) > W - 160:
            while line and draw.textlength("•  " + line + "…", font=story_font) > W - 160:
                line = line[:-1]
            line = line + "…"
        draw.text((80, y_story), "•  " + line, font=story_font, fill=MUTED)
        y_story += 42

    # Footer strip
    draw.rectangle([0, H - 18, W, H - 18 + 12], fill=RED)
    draw.rectangle([0, H - 6, W, H], fill=GOLD)
    foot_font = _font(True, 24)
    tag = "spanified.com"
    draw.text((W - draw.textlength(tag, font=foot_font) - 60, H - 62),
              tag, font=foot_font, fill=RED)

    return img


def render_default_card():
    """Fallback OG card for homepage / static pages."""
    return render_digest_card(
        "Every morning",
        "Spain's top news, in English.",
        ["Curated and summarized", "Free forever, 5-minute read"],
    )


def render_og_images(digests, out_dir):
    """Render per-digest cards + default card into <out_dir>/og/. Returns count."""
    og_dir = os.path.join(out_dir, "og")
    os.makedirs(og_dir, exist_ok=True)
    count = 0
    for digest in digests:
        # date doubles as the output filename — reject anything off-format
        # so a malformed value can never escape og/ via path traversal.
        if not DATE_RE.match(digest.get("date", "")):
            print(f"  WARN: skipping og card, bad date: {digest.get('date')!r}")
            continue
        stories = [s.get("title", "") for s in digest.get("stories", [])]
        img = render_digest_card(digest["date_display"], digest["headline"], stories)
        img.save(os.path.join(og_dir, f"{digest['date']}.png"))
        count += 1
    render_default_card().save(os.path.join(og_dir, "og-default.png"))
    print(f"  wrote {count} og cards + og-default.png")
    return count
