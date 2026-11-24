"""Internal-link audit over a full build. Hard rule: /es/ pages never link
an English page (only hreflang alternates and the language switcher may),
every /es/ URL resolves with its #anchor, English pages never link into /es/,
and Spanish pages carry the same suggestion blocks as their English twins."""
import html
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urldefrag, urlsplit

import pytest

ROOT = Path(__file__).parent
SITE = "https://spanified.com"
ASSET_RE = re.compile(r"\.(css|js|json|png|jpe?g|webp|svg|ico|xml|txt|mp3|woff2?|pdf|webmanifest)$", re.I)
HREF_RE = re.compile(r"""<a\b[^>]*?\shref\s*=\s*(?:"([^"]*)"|'([^']*)')[^>]*>""", re.I | re.S)
ID_RE = re.compile(r"""\sid\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I)
SWITCH_RE = re.compile(r"""<nav\b[^>]*lang-switch[^>]*>.*?</nav>""", re.S | re.I)


@pytest.fixture(scope="module")
def dist(tmp_path_factory):
    out = tmp_path_factory.mktemp("dist")
    subprocess.run([sys.executable, str(ROOT / "build.py"), "--out", str(out)], cwd=ROOT, check=True,
                   capture_output=True)
    return out


def url_to_file(dist, path):
    """Served URL path -> built file (GitHub Pages: x.html or x/index.html)."""
    rel = path.strip("/")
    for cand in ((dist / "index.html",) if not rel else (dist / f"{rel}.html", dist / rel / "index.html")):
        if cand.is_file():
            return cand
    return None


def normalize(href, page_path):
    """Return (path, fragment) for an internal link, else None."""
    href = html.unescape(href).strip()
    if href.startswith(SITE):
        href = href[len(SITE):] or "/"
    if href.startswith("#"):
        return page_path, href[1:]
    if not href.startswith("/") or href.startswith("//"):
        return None
    path, frag = urldefrag(urlsplit(href).path + ("#" + urlsplit(href).fragment if urlsplit(href).fragment else ""))
    path = path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"
        if path.endswith("/index.html"):
            path = path[: -len("index.html")] or "/"
        elif path.endswith(".html"):
            path = path[: -len(".html")]
    if ASSET_RE.search(path) or path.startswith("/static/") or path.startswith("/og/"):
        return None
    return path, frag


def page_links(text, page_path):
    """Yield (path, fragment) of body links, switcher excluded (hreflang lives in <link>, not <a>)."""
    text = SWITCH_RE.sub("", text)
    for m in HREF_RE.finditer(text):
        n = normalize(m.group(1) or m.group(2) or "", page_path)
        if n:
            yield n


def ids_of(text):
    return {m.group(1) or m.group(2) for m in ID_RE.finditer(text)} | {
        m.group(1) or m.group(2) for m in re.finditer(r"""<a\b[^>]*\sname\s*=\s*(?:"([^"]*)"|'([^']*)')""", text)}


def pages(dist, sub):
    root = dist / sub if sub else dist
    for f in sorted(root.rglob("*.html")):
        rel = f.relative_to(dist).as_posix()[:-5]
        if rel.endswith("index"):
            rel = rel[:-5]
        path = "/" + rel.strip("/")
        if sub == "" and (path == "/es" or path.startswith("/es/")):
            continue
        yield path, f


def page_path_of(f, dist):
    rel = f.relative_to(dist).as_posix()[:-5]
    if rel.endswith("index"):
        rel = rel[:-5]
    return "/" + rel.strip("/")


HREFLANG_LINK_RE = re.compile(r"""<link\b[^>]*\bhreflang\s*=[^>]*>""", re.I)
TAG_RE = re.compile(r"""<[a-zA-Z][^>]*>""", re.S)
ATTR_RE = re.compile(r"""\s([\w:.-]+)\s*=\s*(?:"([^"]*)"|'([^']*)')""")
SCRIPT_RE = re.compile(r"""<script\b([^>]*)>(.*?)</script>""", re.S | re.I)
JS_PATH_RE = re.compile(r"""["'`](/[^"'`\s]*|https://spanified\.com[^"'`\s]*)["'`]""")


def is_es(path):
    return path == "/es" or path.startswith("/es/")


def json_strings(node, key=""):
    """(key, value) of every string in a parsed JSON-LD tree."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield from json_strings(v, k)
    elif isinstance(node, list):
        for v in node:
            yield from json_strings(v, key)
    elif isinstance(node, str):
        yield key, node


def internal_urls(text, page_path):
    """(where, path, fragment) of every internal page URL on a page: any tag
    attribute (href, src, action, content, value, data-*...), every string in
    JSON-LD, and quoted paths in inline scripts. Exempt: the language switcher
    and <link rel=alternate hreflang> (the hard rule's only English links);
    static assets drop out in normalize()."""
    text = HREFLANG_LINK_RE.sub("", SWITCH_RE.sub("", text))
    for attrs, code in SCRIPT_RE.findall(text):
        if "ld+json" in attrs:
            # "@id" fragments name graph nodes (#org, #website), not HTML ids.
            strings = (("json-ld @id" if k == "@id" else "json-ld", v) for k, v in json_strings(json.loads(code)))
        else:
            strings = (("script", m.group(1)) for m in JS_PATH_RE.finditer(code))
        for where, u in strings:
            n = normalize(u, page_path) if u.startswith(("/", SITE)) else None
            if n:
                yield where, *n
    for tag in TAG_RE.findall(SCRIPT_RE.sub("", text)):
        name = tag[1:].split(None, 1)[0].rstrip(">/").lower()
        for m in ATTR_RE.finditer(tag):
            value = m.group(2) if m.group(2) is not None else m.group(3)
            if not value.startswith(("/", SITE)):
                continue
            n = normalize(value, page_path)
            if n:
                yield f"<{name} {m.group(1)}>", *n


def test_spanish_pages_never_link_english(dist):
    """Hard rule: no English internal URL anywhere on /es/ pages (noindex
    flow pages included), and every /es/ URL resolves, #anchors included."""
    problems = Counter()
    examples = {}
    ids_cache = {}

    def fail(kind, src, target):
        problems[kind] += 1
        examples.setdefault(kind, []).append(f"{src} -> {target}")

    def page_ids(f):
        if f not in ids_cache:
            ids_cache[f] = ids_of(f.read_text(encoding="utf-8"))
        return ids_cache[f]

    for f in sorted((dist / "es").rglob("*.html")):
        src = page_path_of(f, dist)
        for where, path, frag in internal_urls(f.read_text(encoding="utf-8"), src):
            if not is_es(path):
                fail(f"English URL in {where}", src, path)
                continue
            target = url_to_file(dist, path)
            if target is None:
                fail(f"broken /es URL in {where}", src, path)
            elif frag and where not in ("script", "json-ld @id") and frag not in page_ids(target):
                fail(f"missing anchor in {where}", src, f"{path}#{frag}")
    assert not problems, "\n".join(f"{k}: {n}\n  " + "\n  ".join(examples[k][:15]) for k, n in problems.items())


def test_guard_catches_english_urls():
    """The scanner sees every channel the rule covers and skips the exemptions."""
    page = """<html><head>
<link rel="canonical" href="https://spanified.com/terms">
<meta property="og:url" content="https://spanified.com/quiz/ai-or-real">
<link rel="alternate" hreflang="en" href="https://spanified.com/">
<link rel="alternate" type="application/rss+xml" href="/podcast.xml">
<script type="application/ld+json">{"publisher": {"@id": "https://spanified.com/#org", "url": "https://spanified.com/"},
 "itemListElement": [{"item": "https://spanified.com/category/work"}]}</script>
</head><body>
<nav class="lang-switch" aria-label="Idioma"><a href="/subscribe" hreflang="en">EN</a></nav>
<form action="/subscribe"><input type="hidden" name="next" value="https://spanified.com/confirm"></form>
<iframe src="/calculators/net-salary"></iframe><img src="/static/img/x.png">
<script>location.assign('/archive/')</script>
<a href="/es/archive/">ok</a></body></html>"""
    found = sorted((w, p) for w, p, _ in internal_urls(page, "/es/x") if not is_es(p))
    assert found == sorted([
        ("<link href>", "/terms"), ("<meta content>", "/quiz/ai-or-real"),
        ("json-ld @id", "/"), ("json-ld", "/"), ("json-ld", "/category/work"),
        ("<form action>", "/subscribe"), ("<input value>", "/confirm"),
        ("<iframe src>", "/calculators/net-salary"), ("script", "/archive"),
    ])


def test_english_pages_do_not_link_to_es(dist):
    bad = []
    for f in sorted(dist.rglob("*.html")):
        src = page_path_of(f, dist)
        if src == "/es" or src.startswith("/es/"):
            continue
        for path, _ in page_links(f.read_text(encoding="utf-8"), src):
            if path == "/es" or path.startswith("/es/"):
                bad.append(f"{src} -> {path}")
    assert not bad, "\n".join(bad[:30])


# --- EN/ES linking parity ----------------------------------------------------
# Suggestion blocks, counted per page by their markup. Digest story lines come
# from the English twin story (attach_twin_links) plus the Spanish keyword
# match, so a Spanish digest has at least the English count; every other page
# type renders the same blocks from shared data, so the counts are equal.
BLOCKS = {
    "guide line": 'class="story-guide"',
    "calculator line": 'class="story-guide story-tool"',
    "calculator card": 'class="hub-calculator"',
    "guide card": 'class="hub-guide"',
    "breadcrumb": 'class="breadcrumbs"',
    "day nav": 'class="day-nav',
    "amount prev/next": 'class="ns-seo-',
    "other quiz card": 'class="quiz-other"',
}
CHROME_RE = re.compile(r"<header\b.*?</header>|<footer\b.*?</footer>|<script\b.*?</script>|<head>.*?</head>", re.S | re.I)
LINK_KIND_RE = re.compile(r"""<a\b[^>]*\shref="(?:https://spanified\.com)?(/[^"#?]*)""", re.I)


def link_profile(f):
    """Block counts plus body links by section (/es prefix dropped)."""
    text = f.read_text(encoding="utf-8")
    prof = Counter({k: text.count(v) for k, v in BLOCKS.items()})
    for path in LINK_KIND_RE.findall(CHROME_RE.sub("", text)):
        path = re.sub(r"^/es(?=/|$)", "", path) or "/"
        if not ASSET_RE.search(path) and not path.startswith(("/static/", "/og/")):
            prof["links to /" + (path.split("/")[1] or "")] += 1
    return prof


SAMPLE = [
    "archive/2026-05-08", "archive/2026-06-15", "archive/2026-07-13", "archive/2026-10-20", "archive/2026-11-23",
    "archive/index", "archive/2", "category/property", "category/taxes",
    "articles/autonomo-taxes-spain", "articles/spain-property-guide", "articles/how-spain-votes", "articles/index",
    "calculators/net-salary", "calculators/autonomo-tax", "calculators/rental-yield",
    "calculators/property-buying-cost", "calculators/electricity-bill",
    "calculators/net-salary-1200-euros-per-month", "calculators/rental-yield-300000-euros-property",
    "quiz/ai-or-real", "quiz/spanish-law-or-myth", "index", "about", "editor", "contact",
    "subscribe", "confirm", "success", "unsubscribe", "terms",
]
# Deliberate content gaps: the podcast player (English audio) is not on
# Spanish digests.
SKIP = {"links to /podcast"}


def test_linking_parity_sample(dist):
    bad = []
    for rel in SAMPLE:
        en, es = dist / f"{rel}.html", dist / "es" / f"{rel}.html"
        assert en.is_file() and es.is_file(), rel
        a, b = link_profile(en), link_profile(es)
        digest = rel.startswith("archive/20")
        for k in sorted(set(a) | set(b)):
            if k in SKIP:
                continue
            if digest and k in ("guide line", "calculator line", "calculator card", "guide card",
                                "links to /articles", "links to /calculators"):
                continue  # compared as a total below
            if a[k] != b[k]:
                bad.append(f"{rel}: {k} en={a[k]} es={b[k]}")
        if digest:
            if a["calculator line"] != b["calculator line"]:
                bad.append(f"{rel}: calculator lines en={a['calculator line']} es={b['calculator line']}")
            keys = ("guide line", "calculator line", "calculator card", "guide card")
            if sum(b[k] for k in keys) < sum(a[k] for k in keys):
                bad.append(f"{rel}: fewer suggestions en={[a[k] for k in keys]} es={[b[k] for k in keys]}")
    assert not bad, "\n".join(bad)


def test_every_spanish_digest_has_the_english_suggestions(dist):
    """All digests: same calculator lines, and no fewer suggestion links."""
    keys = ("guide line", "calculator line", "calculator card", "guide card")
    bad = []
    for es in sorted((dist / "es" / "archive").glob("20??-??-??.html")):
        a, b = link_profile(dist / "archive" / es.name), link_profile(es)
        if a["calculator line"] != b["calculator line"] or sum(b[k] for k in keys) < sum(a[k] for k in keys):
            bad.append(f"{es.stem}: en={[a[k] for k in keys]} es={[b[k] for k in keys]}")
    assert not bad, "\n".join(bad[:20])
