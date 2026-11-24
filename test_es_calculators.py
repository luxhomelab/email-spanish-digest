"""Spanish calculators (/es/calculators/...): every hub and amount page has a
Spanish twin with Spanish copy and number formats, self canonical, hreflang
pair, Spanish JSON-LD, /es/ links only, and sitemap entries with alternates."""
import json
import re
from html import unescape
from pathlib import Path

import jinja2
import pytest

import build

SITE = build.SITE_URL
NBSP = " "


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("site")
    mp = pytest.MonkeyPatch()
    mp.setattr(build, "OUT_DIR", str(out))
    mp.setattr(build, "ES_PATHS", set(build.ES_PATHS))
    build.register_es_calculator_paths()
    # Pages the calculators link to whose Spanish twins the full build registers.
    build.ES_PATHS.update(a["path"] for a in build.load_articles("es"))
    # Header nav targets (partials/header.html) the full build registers too.
    build.ES_PATHS.update(["/", "/archive/", "/articles/", "/about", "/contact"])
    build.register_es_quiz_paths()
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(build.TEMPLATES_DIR), autoescape=True)
    build.register_i18n(env)
    env.globals.update(site_url=SITE, pub_date=build.pub_date, video_embed=build.video_embed, asset_version="1",
                       js_importmap="{}", turnstile_enabled=False, analytics_enabled=False, site_socials=[],
                       listmonk_form_action="/x", listmonk_list_uuid="u", listmonk_es_list_uuid="ues", current_year=2026)
    build._untranslated.clear()
    build.render_calculators(env)
    ns = build.render_net_salary_pages(env)
    au = build.render_autonomo_pages(env)
    ry = build.render_rental_yield_pages(env)
    build.render_sitemap([], (), (), ns, au, ry)
    untranslated = set(build._untranslated)
    yield Path(out), untranslated
    mp.undo()


def es_files(out):
    return sorted((out / "es" / "calculators").glob("*.html"))


def head(html):
    return html.split("</head>", 1)[0]


def meta(html, key):
    return [unescape(v) for v in re.findall(rf'<meta (?:name|property)="{re.escape(key)}" content="([^"]*)"', head(html))]


def without_video(html):
    """Drop the YouTube embed: the videos (titles, chapters) are in English."""
    return re.sub(r'<figure class="video-embed.*?</figure>', "", html, flags=re.S)


def body_without_switcher(html):
    body = html.split("</head>", 1)[1]
    return re.sub(r'<nav\b[^>]*lang-switch[^>]*>.*?</nav>', "", body, flags=re.S)


def test_every_calculator_page_has_a_spanish_twin(site):
    out, _ = site
    en = {p.name for p in (out / "calculators").glob("*.html")}
    es = {p.name for p in es_files(out)}
    assert len(en) == 5 + 45 + 25 + 13
    assert es == en
    assert {p[len("/calculators/"):] + ".html" for p in build.calculator_paths()} == en


def test_no_untranslated_ui_strings(site):
    _, untranslated = site
    assert not untranslated, sorted(untranslated)[:20]


def test_spanish_head_canonical_hreflang_and_locale(site):
    out, _ = site
    for f in es_files(out):
        html = f.read_text(encoding="utf-8")
        url = f"{SITE}/es/calculators/{f.stem}"
        assert '<html lang="es"' in html, f.name
        assert re.findall(r'<link rel="canonical" href="([^"]+)"', html) == [url], f.name
        assert meta(html, "og:url") == [url], f.name
        assert meta(html, "og:locale") == ["es_ES"] and meta(html, "og:locale:alternate") == ["en_GB"], f.name
        alt = dict(re.findall(r'<link rel="alternate" hreflang="([^"]+)" href="([^"]+)"', head(html)))
        assert alt == {"en": f"{SITE}/calculators/{f.stem}", "es": url, "x-default": f"{SITE}/calculators/{f.stem}"}, f.name
        en_html = (out / "calculators" / f.name).read_text(encoding="utf-8")
        assert '<html lang="en"' in en_html
        assert dict(re.findall(r'<link rel="alternate" hreflang="([^"]+)" href="([^"]+)"', head(en_html))) == alt


def test_spanish_titles_and_descriptions(site):
    out, _ = site
    titles, descs = set(), set()
    for f in es_files(out):
        html = f.read_text(encoding="utf-8")
        title = unescape(re.search(r"<title>(.*?)</title>", html, re.S).group(1).strip())
        desc = meta(html, "description")[0]
        assert 20 <= len(title) <= 70, (f.name, len(title), title)
        assert 100 <= len(desc) <= 160, (f.name, len(desc), desc)
        assert "—" not in title + desc, f.name
        assert title not in titles and desc not in descs, f.name
        titles.add(title)
        descs.add(desc)


def test_json_ld_is_spanish_with_es_urls(site):
    out, _ = site
    for f in es_files(out):
        html = f.read_text(encoding="utf-8")
        blocks = [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]
        nodes = [n for b in blocks for n in b.get("@graph", [b])]
        types = {n["@type"] for n in nodes}
        assert {"WebPage", "FAQPage", "BreadcrumbList"} <= types, (f.name, types)
        for n in nodes:
            if n["@type"] in ("WebPage", "FAQPage"):
                assert n["inLanguage"] == "es", f.name
        page = next(n for n in nodes if n["@type"] == "WebPage")
        assert page["url"] == f"{SITE}/es/calculators/{f.stem}"
        if "isPartOf" in page:
            assert page["isPartOf"]["url"].startswith(f"{SITE}/es/calculators/")
        crumbs = next(n for n in nodes if n["@type"] == "BreadcrumbList")["itemListElement"]
        assert [c["item"] for c in crumbs][0] == f"{SITE}/es/"
        assert all(c["item"].startswith(f"{SITE}/es/") for c in crumbs), f.name
        faq = next(n for n in nodes if n["@type"] == "FAQPage")["mainEntity"]
        assert faq and all(q["name"].startswith("¿") for q in faq), f.name


def test_spanish_pages_link_spanish_pages(site):
    """Body links go to /es/ (or assets); the language switcher is the one English link."""
    out, _ = site
    for f in es_files(out):
        html = f.read_text(encoding="utf-8")
        for href in re.findall(r'<a\b[^>]*\shref="(/[^"]*)"', body_without_switcher(html)):
            assert href.startswith(("/es/", "/static/")), (f.name, href)
        switch = re.search(r'<nav\b[^>]*lang-switch[^>]*>.*?</nav>', html, re.S).group(0)
        assert f'href="/calculators/{f.stem}"' in switch, f.name


def test_english_pages_unchanged_in_language(site):
    out, _ = site
    html = (out / "calculators" / "net-salary-30000-euros.html").read_text(encoding="utf-8")
    assert "€30,000" in html and "30.000" not in html
    assert 'href="/calculators/net-salary?' in html
    assert "/es/calculators/" not in body_without_switcher(html)


def test_spanish_number_formats_and_copy(site):
    out, _ = site
    ns = without_video((out / "es" / "calculators" / "net-salary-30000-euros.html").read_text(encoding="utf-8"))
    assert f"30.000{NBSP}€ brutos al año" in ns
    assert "€30,000" not in ns and "Gross" not in ns
    assert re.search(rf"\d,\d{NBSP}%", ns), "decimal comma percent"
    assert "Comunidad Valenciana" in ns and "Valencian Community" not in ns
    hub = (out / "es" / "calculators" / "net-salary.html").read_text(encoding="utf-8")
    assert '<option value="andalucia">Andalucía</option>' in hub
    assert "Calculadora de sueldo neto" in hub and "Net Salary Calculator" not in body_without_switcher(hub)
    ry = (out / "es" / "calculators" / "rental-yield-200000-euros-property.html").read_text(encoding="utf-8")
    assert f"200.000{NBSP}€" in ry and "p. p." in ry
    au = (out / "es" / "calculators" / "autonomo-take-home-2000-euros-per-month.html").read_text(encoding="utf-8")
    assert f"1.500{NBSP}€/mes" in au and "/mo<" not in au
    elec = (out / "es" / "calculators" / "electricity-bill.html").read_text(encoding="utf-8")
    assert "Calculadora de la factura de la luz" in elec and "in English" not in elec


def test_spanish_pages_load_the_calculator_scripts(site):
    """Same JS as English: calc-i18n.js picks Spanish from <html lang>."""
    out, _ = site
    for name, script in (("net-salary", "net-salary.js"), ("electricity-bill", "electricity.js"),
                         ("autonomo-tax", "autonomo.js"), ("rental-yield", "rental-yield.js"),
                         ("property-buying-cost", "property-buying-cost.js")):
        html = (out / "es" / "calculators" / f"{name}.html").read_text(encoding="utf-8")
        assert f'src="/static/js/{script}?v=' in html, name


def test_sitemap_lists_spanish_calculators_with_alternates(site):
    out, _ = site
    xml = (out / "sitemap.xml").read_text(encoding="utf-8")
    entries = {re.search(r"<loc>(.*?)</loc>", b).group(1): b for b in re.findall(r"<url>(.*?)</url>", xml, re.S)}
    for path in build.calculator_paths():
        es = f"{SITE}/es{path}"
        assert es in entries, es
        assert f'hreflang="en" href="{SITE}{path}"' in entries[es]
        assert f'hreflang="es" href="{es}"' in entries[SITE + path]
