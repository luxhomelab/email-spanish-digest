#!/usr/bin/env python3
"""OG preview images for Spanified (1200x630 PNG, Pillow only).

Generated at build time into <out_dir>/og/:
  - YYYY-MM-DD.png per digest (kicker, date, headline, top-3 stories)
  - article-<slug>.png per guide article (kicker, title, read time + date)
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

# Slugs come from data/articles/*.md filenames (build.py) — reject anything
# outside lowercase-kebab-case so a malformed value can never escape og/ via
# path traversal, exactly like DATE_RE above.
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

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

# Card copy per edition. Spanish cards are written to og/es/ (see
# render_og_images) so /es/ pages never share the English image.
LABELS = {
    "en": {
        "brand": "SPAIN DAILY",
        "guide": "GUIDE",
        "calculator": "CALCULATOR",
        "story": "story",
        "stories": "stories",
        "read": "5-minute read",
        "article_read": "{n}-minute read",
        "default_date": "Every morning",
        "default_headline": "Spain's top news, in English.",
        "default_stories": ["Curated and summarized", "Free forever, 5-minute read"],
    },
    "es": {
        "brand": "ESPAÑA AL DÍA",
        "guide": "GUÍA",
        "calculator": "CALCULADORA",
        "story": "noticia",
        "stories": "noticias",
        "read": "5 minutos de lectura",
        "article_read": "{n} min de lectura",
        "default_date": "Cada mañana",
        "default_headline": "Las noticias de España, resumidas.",
        "default_stories": ["Seleccionadas y resumidas", "Gratis, 5 minutos de lectura"],
    },
}

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
    # Split on plain spaces only: str.split() would also break at the
    # no-break space in Spanish amounts ("100.000\xa0€").
    for word in filter(None, text.split(" ")):
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


def render_digest_card(date_display, headline, stories, topics=None, lang="en"):
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
    labels = LABELS[lang]
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
    kicker = labels["brand"]
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
            words, idx, cut = [w for w in headline.split(" ") if w], 0, []
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
    noun = labels["story"] if count == 1 else labels["stories"]
    if topics:
        summary = f"{count} {noun}  •  " + ", ".join(t.lower() for t in topics[:3])
        if draw.textlength(summary, font=_font(False, 32)) > max_w:
            summary = f"{count} {noun}  •  " + ", ".join(t.lower() for t in topics[:2])
    else:
        summary = f"{count} {noun}  •  {labels['read']}"
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


def render_article_card(title, reading_time, date_display, lang="en"):
    """OG card for a guide article: GUIDE kicker, title, "X-minute read • date"."""
    labels = LABELS[lang]
    summary = labels["article_read"].format(n=reading_time) + f"  •  {_strip_emoji(date_display)}"
    return _render_titled_card(labels["guide"], title, summary)


def render_calculator_card(title, summary, lang="en"):
    """OG card for a calculator page: CALCULATOR kicker, page title, key result
    or tagline as the summary line (built in build.py, already localized)."""
    return _render_titled_card(LABELS[lang]["calculator"], title, summary)


def _render_titled_card(kicker, title, summary):
    """Render a 1200x630 OG card (guide articles, calculators), in the same visual
    language as render_digest_card(): crop-safe centred column, red/gold
    edge decor, letterspaced kicker, auto-fit headline, red/gold divider,
    one summary line and the domain footer.

    Two differences, both driven by content shape: guide titles run longer
    than digest headlines, so the size ladder tops out at 64pt and allows
    a third centred line (digest: 76pt, 2 lines); and the date joins the
    summary line ("X-minute read • <date>") instead of sitting above the
    headline, which buys the headline its extra line.
    """
    title = _strip_emoji(title)
    summary = _strip_emoji(summary)
    img = Image.new("RGB", (W, H), CREAM)
    draw = ImageDraw.Draw(img)
    cx = W // 2
    max_w = SAFE_RIGHT - SAFE_LEFT - 48

    # Edge decor only (no text outside the centre column).
    draw.rectangle([0, 0, 18, H], fill=RED)
    draw.rectangle([18, 0, 26, H], fill=GOLD)
    draw.rectangle([W - 26, 0, W - 18, H], fill=GOLD)
    draw.rectangle([W - 18, 0, W, H], fill=RED)
    draw.line([SAFE_LEFT, 26, SAFE_LEFT, H - 26], fill=GOLD, width=3)
    draw.line([SAFE_RIGHT, 26, SAFE_RIGHT, H - 26], fill=GOLD, width=3)

    # Kicker, centred.
    kf = _font(True, 30)
    tracking = 6
    kw = sum(draw.textlength(ch, font=kf) for ch in kicker) + tracking * (len(kicker) - 1)
    _draw_letterspaced(draw, (cx - kw / 2, 64), kicker, kf, RED, tracking=tracking)

    # Headline: largest size that fits in 3 centred lines.
    best = None
    for size in (64, 56, 48, 42, 36, 32, 28):
        font = _font(True, size)
        lines = _wrap_to_width(draw, title, font, max_w)
        if len(lines) <= 3:
            best = (font, lines)
            break
    if best is None:
        # Outlier long title: 3 lines at 28pt before cutting text.
        font = _font(True, 28)
        lines = _wrap_to_width(draw, title, font, max_w)
        if len(lines) > 3:
            words, idx, cut = [w for w in title.split(" ") if w], 0, []
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

    # Summary: one centred line (reading time + date, or a calculator result).
    # Spanish dates ("23 de noviembre de 2026") need the 24pt step.
    for size in (32, 28, 24):
        sum_font = _font(False, size)
        if draw.textlength(summary, font=sum_font) <= max_w:
            break
    while draw.textlength(summary, font=sum_font) > max_w and len(summary) > 24:
        summary = summary[:-2] + "…"

    # Vertical rhythm: centre the headline+summary block between the
    # kicker (ends ~100) and the domain line (starts ~548).
    head_h = line_h * len(lines)
    block_h = head_h + 14 + 5 + 20 + 40
    top, bottom = 112, 540
    y = top + max(0, (bottom - top - block_h) // 2)

    for line in lines:
        draw.text((cx - draw.textlength(line, font=font) / 2, y),
                  line, font=font, fill=INK)
        y += line_h

    # Red/gold divider, centred (same as the digest card).
    y_div = y + 14
    draw.rectangle([cx - 100, y_div, cx + 20, y_div + 5], fill=RED)
    draw.rectangle([cx + 20, y_div, cx + 100, y_div + 5], fill=GOLD)

    draw.text((cx - draw.textlength(summary, font=sum_font) / 2, y_div + 25),
              summary, font=sum_font, fill=MUTED)

    # Domain line, centred.
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


def render_default_card(lang="en"):
    """Fallback OG card for homepage / static pages."""
    labels = LABELS[lang]
    return render_digest_card(labels["default_date"], labels["default_headline"],
                              labels["default_stories"], lang=lang)


def save_calculator_card(out_dir, lang, slug, title, summary):
    """Write og/[es/]calc-<slug>.png and return its site path."""
    if not SLUG_RE.match(slug):
        raise ValueError(f"bad calculator slug for og card: {slug!r}")
    rel = "/".join(["og"] + (["es"] if lang == "es" else []) + [f"calc-{slug}.png"])
    path = os.path.join(out_dir, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    render_calculator_card(title, summary, lang).save(path)
    return "/" + rel


def render_og_images(digests, articles, out_dir, lang="en"):
    """Render per-digest + per-article cards + default card into <out_dir>/og/
    (lang="es": <out_dir>/og/es/, same file names). Returns total count."""
    og_dir = os.path.join(out_dir, "og", *(["es"] if lang == "es" else []))
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
                                 topics=digest.get("tag_categories"), lang=lang)
        img.save(os.path.join(og_dir, f"{digest['date']}.png"))
        count += 1
    for article in articles or []:
        # slug doubles as the output filename — reject anything off-format
        # so a malformed value can never escape og/ via path traversal.
        if not SLUG_RE.match(article.get("slug", "")):
            print(f"  WARN: skipping article og card, bad slug: {article.get('slug')!r}")
            continue
        img = render_article_card(article["title"], article["reading_time"],
                                  article["date_display"], lang=lang)
        img.save(os.path.join(og_dir, f"article-{article['slug']}.png"))
        count += 1
    render_default_card(lang).save(os.path.join(og_dir, "og-default.png"))
    if lang == "es":
        # /es/subscribe uses static/img/social/subscribe-es.jpg instead.
        print(f"  wrote {count} Spanish og cards + og-default.png into og/es/")
        return count
    render_subscribe_card().save(os.path.join(og_dir, "og-subscribe.png"))
    print(f"  wrote {count} og cards + og-default.png + og-subscribe.png")
    return count
