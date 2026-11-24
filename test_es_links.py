"""Internal-link audit over a full build: Spanish pages link to Spanish twins
whenever one exists, every /es/ link resolves, #anchors exist, and English
pages never link into /es/ (except the language switcher and hreflang)."""
import html
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


def test_spanish_links(dist):
    exists = {}
    problems = Counter()
    examples = {}
    english_only = Counter()

    def fail(kind, src, target):
        problems[kind] += 1
        examples.setdefault(kind, []).append(f"{src} -> {target}")

    ids_cache = {}

    def page_ids(path):
        f = url_to_file(dist, path)
        if f not in ids_cache:
            ids_cache[f] = ids_of(f.read_text(encoding="utf-8"))
        return ids_cache[f]

    for f in sorted((dist / "es").rglob("*.html")):
        src = page_path_of(f, dist)
        for path, frag in page_links(f.read_text(encoding="utf-8"), src):
            if path == "/es" or path.startswith("/es/"):
                if url_to_file(dist, path) is None:
                    fail("broken /es link", src, path)
                elif frag and frag not in page_ids(path):
                    fail("missing anchor", src, f"{path}#{frag}")
            else:
                twin = "/es" + path if path != "/" else "/es"
                if url_to_file(dist, twin) is not None:
                    fail("English link with Spanish twin", src, path)
                else:
                    english_only[path.split("/")[1] if path != "/" else "/"] += 1
    assert not problems, "\n".join(f"{k}: {n}\n  " + "\n  ".join(examples[k][:15]) for k, n in problems.items())


LD_RE = re.compile(r"""<script[^>]*application/ld\+json[^>]*>(.*?)</script>""", re.S | re.I)
LD_URL_RE = re.compile(r""""(?:url|item|mainEntityOfPage)"\s*:\s*"(https://spanified\.com[^"]*|/[^"]*)\"""")
REL_RE = re.compile(r"""<link\b[^>]*\brel\s*=\s*"(canonical|prev|next)"[^>]*\bhref\s*=\s*"([^"]*)\"""", re.I)


def test_spanish_metadata_urls(dist):
    """JSON-LD urls and canonical/prev/next point at existing Spanish pages
    (non-/es targets are fine only when no Spanish twin exists)."""
    bad = []
    for f in sorted((dist / "es").rglob("*.html")):
        src = page_path_of(f, dist)
        text = f.read_text(encoding="utf-8")
        urls = [m.group(1) for blk in LD_RE.findall(text) for m in LD_URL_RE.finditer(blk)]
        urls += [m.group(2) for m in REL_RE.finditer(text)]
        for u in urls:
            n = normalize(u, src)
            if not n:
                continue
            path, frag = n
            if path == "/es" or path.startswith("/es/"):
                target = url_to_file(dist, path)
                if target is None:
                    bad.append(f"{src}: broken {path}")
                elif frag and frag not in ids_of(target.read_text(encoding="utf-8")):
                    bad.append(f"{src}: missing anchor {path}#{frag}")
            elif path == "/":
                continue  # publisher Organization url: site identity, stays the root
            elif url_to_file(dist, "/es" + path):
                bad.append(f"{src}: English URL with Spanish twin {path}")
    assert not bad, "\n".join(bad[:30])


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
