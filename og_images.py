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

# Same DejaVu typeface on Windows dev machines (fonts ship in C:\Windows\Fonts).
# Linux/CI paths come first so server output never changes.
FONT_BOLD_CANDIDATES = (FONT_BOLD, r"C:\Windows\Fonts\DejaVuSans-Bold.ttf")
FONT_REGULAR_CANDIDATES = (FONT_REGULAR, r"C:\Windows\Fonts\DejaVuSans.ttf")

_font_cache = {}


def _font(bold, size):
    key = (bold, size)
    if key not in _font_cache:
        for path in FONT_BOLD_CANDIDATES if bold else FONT_REGULAR_CANDIDATES:
            try:
                _font_cache[key] = ImageFont.truetype(path, size)
                break
            except OSError:
                continue
        else:
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


# Central "crop-safe" column shared with the subscribe card: Reddit and
# Facebook crop link previews to a centre square, so every word must live
# inside 285..915px. The outer thirds carry flat colour + decor, no text.
SAFE_LEFT, SAFE_RIGHT = 285, 915


def _wrap_to_width(draw, text, font, max_width):
    """Greedy word-wrap returning lines that each fit max_width."""
    lines, current = [], ""
    for word in text.split():
        trial = (current + " " + word).strip()
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def render_digest_card(date_display, headline, stories, topics=None):
    """Render a 1200x630 OG card built for Reddit-cropped link previews.

    Same visual language as render_subscribe_card(): kicker, compact date
    and an oversized (up to 76pt, max 2 lines) headline, all centred in the
    crop-safe column; one summary line (story count + topics) instead of
    tiny bullets; centred domain footer. stories: list of titles (only the
    count is shown). topics: up to 3 category names for the summary line.
    """
    headline = _strip_emoji(headline)
    date_display = _strip_emoji(date_display)
    stories = [_strip_emoji(t) for t in (stories or [])]
    topics = [t for t in (_strip_emoji(t) for t in (topics or [])) if t]
    img = Image.new("RGB", (W, H), CREAM)
    draw = ImageDraw.Draw(img)
    cx = W // 2
    max_w = SAFE_RIGHT - SAFE_LEFT - 48  # 582px with breathing room

    # Edge decor only (no text outside the centre column).
    draw.rectangle([0, 0, 18, H], fill=RED)
    draw.rectangle([18, 0, 26, H], fill=GOLD)
    draw.rectangle([W - 26, 0, W - 18, H], fill=GOLD)
    draw.rectangle([W - 18, 0, W, H], fill=RED)
    draw.line([SAFE_LEFT, 26, SAFE_LEFT, H - 26], fill=GOLD, width=3)
    draw.line([SAFE_RIGHT, 26, SAFE_RIGHT, H - 26], fill=GOLD, width=3)

    # Kicker, centred.
    kicker = "SPAIN DAILY"
    kf = _font(True, 30)
    tracking = 6
    kw = sum(draw.textlength(ch, font=kf) for ch in kicker) + tracking * (len(kicker) - 1)
    _draw_letterspaced(draw, (cx - kw / 2, 64), kicker, kf, RED, tracking=tracking)

    # Date: compact single line, centred (was 72pt full-width).
    date_font = _font(True, 36)
    if draw.textlength(date_display, font=date_font) > max_w:
        date_font = _font(True, 30)
    date_h = 48

    # Headline: largest size that fits in 2 centred lines (was 46→28pt, 3 lines).
    best = None
    for size in (76, 68, 60, 52, 46, 40):
        font = _font(True, size)
        lines = _wrap_to_width(draw, headline, font, max_w)
        if len(lines) <= 2:
            best = (font, lines)
            break
    if best is None:
        # Outlier long headline: allow a third line at 40pt before cutting text.
        font = _font(True, 40)
        lines = _wrap_to_width(draw, headline, font, max_w)
        if len(lines) > 3:
            words, idx, cut = headline.split(), 0, []
            for n in range(3):
                cur = ""
                while idx < len(words):
                    trial = (cur + " " + words[idx]).strip() + ("…" if n == 2 else "")
                    if draw.textlength(trial, font=font) <= max_w:
                        cur = (cur + " " + words[idx]).strip()
                        idx += 1
                    else:
                        break
                cut.append(cur)
            if idx < len(words) and cut:
                cut[-1] = (cut[-1] + "…") if cut[-1] else "…"
            lines = [ln for ln in cut if ln] or ["…"]
        best = (font, lines)
    font, lines = best
    line_h = int(font.size * 1.18)

    # Summary: one centred line — count plus topics, or reading time.
    # (Replaces the 26pt 3-bullet list, unreadable in feed crops.)
    count = len(stories)
    noun = "story" if count == 1 else "stories"
    if topics:
        summary = f"{count} {noun}  •  " + ", ".join(t.lower() for t in topics[:3])
        if draw.textlength(summary, font=_font(False, 32)) > max_w:
            summary = f"{count} {noun}  •  " + ", ".join(t.lower() for t in topics[:2])
    else:
        summary = f"{count} {noun}  •  5-minute read"
    sum_font = _font(False, 32)
    if draw.textlength(summary, font=sum_font) > max_w:
        sum_font = _font(False, 28)
    while draw.textlength(summary, font=sum_font) > max_w and len(summary) > 24:
        summary = summary[:-2] + "…"

    # Vertical rhythm: centre the date+headline+summary block between the
    # kicker (ends ~100) and the domain line (starts ~548).
    head_h = line_h * len(lines)
    block_h = date_h + 12 + head_h + 14 + 5 + 20 + 40
    top, bottom = 112, 540
    y = top + max(0, (bottom - top - block_h) // 2)

    draw.text((cx - draw.textlength(date_display, font=date_font) / 2, y),
              date_display, font=date_font, fill=INK)
    y += date_h + 12
    for line in lines:
        draw.text((cx - draw.textlength(line, font=font) / 2, y),
                  line, font=font, fill=INK)
        y += line_h

    # Red/gold divider, centred (same as the subscribe card).
    y_div = y + 14
    draw.rectangle([cx - 100, y_div, cx + 20, y_div + 5], fill=RED)
    draw.rectangle([cx + 20, y_div, cx + 100, y_div + 5], fill=GOLD)

    draw.text((cx - draw.textlength(summary, font=sum_font) / 2, y_div + 25),
              summary, font=sum_font, fill=MUTED)

    # Domain line, centred (was bottom-right).
    df = _font(True, 26)
    tag = "spanified.com"
    draw.text((cx - draw.textlength(tag, font=df) / 2, 548), tag, font=df, fill=RED)

    return img


def render_subscribe_card():
    """High-contrast subscribe card for /subscribe (1200x630).

    Reddit/FB crop link previews to a central square, so every word lives
    inside the middle 630px column (285..915) with breathing room. The left
    and right thirds carry only flat colour + thin decor bars, no text.
    Headline is ~2x the digest card size; CTA is a solid red pill.
    """
    img = Image.new("RGB", (W, H), CREAM)
    draw = ImageDraw.Draw(img)
    cx = W // 2

    # Edge decor only (no text outside the centre column).
    draw.rectangle([0, 0, 18, H], fill=RED)
    draw.rectangle([18, 0, 26, H], fill=GOLD)
    draw.rectangle([W - 26, 0, W - 18, H], fill=GOLD)
    draw.rectangle([W - 18, 0, W, H], fill=RED)
    # Thin frame marking the crop-safe centre column.
    draw.line([285, 26, 285, H - 26], fill=GOLD, width=3)
    draw.line([915, 26, 915, H - 26], fill=GOLD, width=3)

    # Kicker, centred.
    kicker = "SPAIN DAILY"
    kf = _font(True, 30)
    tracking = 6
    kw = sum(draw.textlength(ch, font=kf) for ch in kicker) + tracking * (len(kicker) - 1)
    _draw_letterspaced(draw, (cx - kw / 2, 66), kicker, kf, RED, tracking=tracking)

    # Headline: largest size that fits the safe column (3 short lines).
    lines = ["Spain news", "in English", "every morning"]
    max_w = 915 - 285 - 48
    size = 60
    for candidate in (96, 88, 80, 72, 68, 64, 60):
        f = _font(True, candidate)
        if all(draw.textlength(line, font=f) <= max_w for line in lines):
            size = candidate
            break
    hf = _font(True, size)
    line_h = int(size * 1.18)
    y = 122
    for line in lines:
        draw.text((cx - draw.textlength(line, font=hf) / 2, y), line, font=hf, fill=INK)
        y += line_h
    # Expose the picked size for the build report.
    img.info["headline_size"] = size

    # Red/gold divider, centred.
    y_div = y + 6
    draw.rectangle([cx - 100, y_div, cx + 20, y_div + 5], fill=RED)
    draw.rectangle([cx + 20, y_div, cx + 100, y_div + 5], fill=GOLD)

    # Value prop subline, centred.
    sub = "5-minute read \u2022 free forever"
    sf = _font(False, 32)
    draw.text((cx - draw.textlength(sub, font=sf) / 2, y_div + 18), sub, font=sf, fill=MUTED)

    # CTA pill: solid red, white bold text.
    cta = "Subscribe \u2014 free"
    cf = _font(True, 40)
    tw = draw.textlength(cta, font=cf)
    pill_w, pill_h = int(tw + 110), 86
    px0, py0 = cx - pill_w / 2, y_div + 68
    try:
        draw.rounded_rectangle([px0, py0, px0 + pill_w, py0 + pill_h], radius=43, fill=RED)
    except AttributeError:
        draw.rectangle([px0, py0, px0 + pill_w, py0 + pill_h], fill=RED)
    draw.text((cx - tw / 2, py0 + (pill_h - 40) / 2 - 2), cta, font=cf, fill=(255, 255, 255))

    # Domain line, centred and small.
    df = _font(True, 26)
    tag = "spanified.com"
    draw.text((cx - draw.textlength(tag, font=df) / 2, py0 + pill_h + 14),
              tag, font=df, fill=RED)

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
        img = render_digest_card(digest["date_display"], digest["headline"], stories,
                                 topics=digest.get("tag_categories"))
        img.save(os.path.join(og_dir, f"{digest['date']}.png"))
        count += 1
    render_default_card().save(os.path.join(og_dir, "og-default.png"))
    render_subscribe_card().save(os.path.join(og_dir, "og-subscribe.png"))
    print(f"  wrote {count} og cards + og-default.png + og-subscribe.png")
    return count
