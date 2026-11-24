"""SEO invariants over a full build for the Spanish section (/es/) and its
English twins: html lang, meta length bounds, og:locale pairs, self
canonicals, reciprocal hreflang, JSON-LD language, sitemap coverage and
llms.txt. See seo/audits/2026-11-24-es-pages.md."""
import json
import re
import subprocess
import sys
from collections import defaultdict
from html import unescape
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
SITE = "https://spanified.com"
# Digest titles are story-led and cut at 82 characters in both languages
# (digest_meta_title); every other page keeps to the usual ~60-70.
DIGEST_TITLE_MAX = 82
TITLE_MAX = 70
DESC_MIN, DESC_MAX = 100, 160


@pytest.fixture(scope="module")
def dist(tmp_path_factory):
    out = tmp_path_factory.mktemp("dist")
    subprocess.run([sys.executable, str(ROOT / "build.py"), "--out", str(out)], cwd=ROOT, check=True,
                   capture_output=True)
    return out


def page_url(dist, f):
    rel = f.relative_to(dist).as_posix()
    rel = rel[: -len("index.html")] if rel.endswith("index.html") else rel[: -len(".html")]
    return f"{SITE}/{rel}"


def url_file(dist, url):
    rel = url[len(SITE):].strip("/")
    for cand in ((dist / "index.html",) if not rel else (dist / f"{rel}.html", dist / rel / "index.html")):
        if cand.is_file():
            return cand
    return None


def head(html):
    return html.split("</head>", 1)[0]


def meta(html, key):
    return [unescape(v) for v in re.findall(
        rf'<meta (?:name|property)="{re.escape(key)}" content="([^"]*)"', head(html))]


def hreflang(html):
    return dict(re.findall(r'<link rel="alternate" hreflang="([^"]+)" href="([^"]+)"', head(html)))


def canonical(html):
    return re.findall(r'<link rel="canonical" href="([^"]+)"', head(html))


def title(html):
    return unescape(re.search(r"<title>(.*?)</title>", head(html), re.S).group(1).strip())


def noindex(html):
    return any("noindex" in v for v in meta(html, "robots"))


@pytest.fixture(scope="module")
def es_pages(dist):
    return {page_url(dist, f): f.read_text(encoding="utf-8") for f in sorted((dist / "es").rglob("*.html"))}


@pytest.fixture(scope="module")
def indexable(es_pages):
    return {u: h for u, h in es_pages.items() if not noindex(h)}


@pytest.fixture(scope="module")
def sitemap(dist):
    xml = (dist / "sitemap.xml").read_text(encoding="utf-8")
    entries = {}
    for block in re.findall(r"<url>(.*?)</url>", xml, re.S):
        loc = re.search(r"<loc>(.*?)</loc>", block).group(1)
        lastmod = re.search(r"<lastmod>(.*?)</lastmod>", block)
        entries[loc] = (lastmod.group(1) if lastmod else None,
                        dict(re.findall(r'hreflang="([^"]+)" href="([^"]+)"', block)))
    return entries


def test_every_es_page_is_spanish_with_es_locale(es_pages):
    assert len(es_pages) > 200
    for url, html in es_pages.items():
        assert '<html lang="es"' in html, url
        assert meta(html, "og:locale") == ["es_ES"], url


def test_meta_title_and_description_bounds(indexable):
    for url, html in indexable.items():
        t = title(html)
        desc = meta(html, "description")
        limit = DIGEST_TITLE_MAX if re.search(r"/es/archive/\d{4}-\d{2}-\d{2}$", url) else TITLE_MAX
        assert 20 <= len(t) <= limit, (url, len(t), t)
        assert len(desc) == 1 and DESC_MIN <= len(desc[0]) <= DESC_MAX, (url, desc)
        assert "—" not in t + desc[0], (url, t, desc[0])


def test_titles_and_descriptions_are_unique(indexable):
    for key in ("title", "description"):
        seen = defaultdict(list)
        for url, html in indexable.items():
            seen[title(html) if key == "title" else meta(html, "description")[0]].append(url)
        dupes = {v: us for v, us in seen.items() if len(us) > 1}
        assert not dupes, (key, dupes)


def test_canonical_og_and_hreflang_pairs(dist, indexable):
    for url, html in indexable.items():
        assert canonical(html) == [url], url
        assert meta(html, "og:url") == [url], url
        assert meta(html, "og:locale:alternate") == ["en_GB"], url
        assert meta(html, "og:title") and meta(html, "og:description"), url
        alt = hreflang(html)
        assert set(alt) == {"en", "es", "x-default"} and alt["es"] == url, (url, alt)
        assert alt["x-default"] == alt["en"], url
        en_file = url_file(dist, alt["en"])
        assert en_file, (url, alt["en"])
        en_html = en_file.read_text(encoding="utf-8")
        assert hreflang(en_html) == alt, (url, alt["en"])
        assert canonical(en_html) == [alt["en"]], alt["en"]
        assert meta(en_html, "og:locale") == ["en_GB"], alt["en"]
        assert meta(en_html, "og:locale:alternate") == ["es_ES"], alt["en"]


def test_json_ld_parses_and_is_spanish(indexable):
    for url, html in indexable.items():
        blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
        assert blocks, url
        nodes = [n for b in blocks for n in (lambda j: j.get("@graph", [j]))(json.loads(b))]
        langs = {n.get("inLanguage") for n in nodes if isinstance(n, dict)}
        assert "es" in langs, (url, langs)
        assert "en" not in langs, (url, langs)
        assert all(n.get("@id", "").startswith((f"{SITE}/es/", f"{SITE}/#")) for n in nodes if n.get("@id")), url


def test_sitemap_lists_every_indexable_es_page_with_alternates(es_pages, indexable, sitemap):
    for url, html in es_pages.items():
        if url in indexable:
            assert url in sitemap, url
            assert sitemap[url][1] == hreflang(html), url
        else:
            assert url not in sitemap, url


def test_es_digest_and_archive_lastmod_match_english(sitemap):
    checked = 0
    for url, (lastmod, alt) in sitemap.items():
        if url.startswith(f"{SITE}/es/archive/") or url.startswith(f"{SITE}/es/category/"):
            assert lastmod == sitemap[alt["en"]][0], url
            checked += 1
    assert checked > 200


def test_llms_txt_points_to_spanish_section(dist):
    llms = (dist / "llms.txt").read_text(encoding="utf-8")
    assert f"{SITE}/es/" in llms
    assert f"{SITE}/es/archive/" in llms
