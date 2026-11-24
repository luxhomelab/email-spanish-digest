"""Spanish home page (/es/): lang, Spanish copy, hreflang pair with /,
self canonicals, JSON-LD, links to /es/ twins and the Spanish subscribe flow."""
import json
import re

import jinja2
import pytest

import build

SITE = build.SITE_URL


def _raw(date, lang):
    title = {"en": "Rents keep rising", "es": "Los alquileres siguen subiendo"}[lang]
    return {"date": date, "subject": {"en": "Rents and jobs", "es": "Alquileres y empleo"}[lang],
            "items": [{"title": title, "body": "x", "category": "housing"},
                      {"title": title + " 2", "body": "x", "category": "work"}]}


PROOF = {"total_issues": 3, "first_issue": "October 15, 2026", "threads": 4100, "reddit": 1000,
         "total_issues_display": 3, "followers_display": "5,100", "first_issue_es": "15 de octubre de 2026",
         "total_issues_es": "3", "testimonials": []}


@pytest.fixture
def site(tmp_path, monkeypatch):
    """Render the English and Spanish home pages (plus /es/subscribe) into tmp_path."""
    monkeypatch.setattr(build, "OUT_DIR", str(tmp_path))
    monkeypatch.setattr(build, "ES_PATHS", set(build.ES_PATHS))
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(build.TEMPLATES_DIR), autoescape=True)
    build.register_i18n(env)
    env.globals.update(current_year=2026, asset_version="t", js_version="t", js_importmap="{}", site_url=SITE,
                       analytics_enabled=False, site_socials=[], turnstile_enabled=False, pub_date=build.pub_date,
                       listmonk_form_action="/x", listmonk_list_uuid="u-en", listmonk_es_list_uuid="u-es")
    en = [build.digest_context(_raw(d, "en")) for d in ("2026-10-17", "2026-10-16", "2026-10-15")]
    es = [build.digest_context(_raw(d, "es"), "es") for d in ("2026-10-17", "2026-10-16")]
    en_articles = build.load_articles()
    es_articles = [a for a in build.load_articles("es") if a["slug"] in {x["slug"] for x in en_articles}]
    build.register_es_paths(es, build.collect_categories(en), es_articles, en_articles)
    en_html = env.get_template("index.html").render(
        latest=en[0], topics=[{"name": "Work", "slug": "work"}], faq=build.FAQ_ITEMS, proof=PROOF,
        quizzes=[], articles=en_articles[:3], alt_path=build.es_alt_path("/"))
    (tmp_path / "index.html").write_text(en_html, encoding="utf-8")
    build.render_es_home(env, es, es_articles, PROOF)
    build.render_es_pages(env, PROOF)
    return lambda rel: (tmp_path / rel).read_text(encoding="utf-8")


def _pair(html):
    return (f'hreflang="en" href="{SITE}/"' in html
            and f'hreflang="es" href="{SITE}/es/"' in html
            and f'hreflang="x-default" href="{SITE}/"' in html)


def _hrefs(html):
    return set(re.findall(r'href="(/[^"]*)"', html))


def test_es_home_lang_canonical_hreflang(site):
    html = site("es/index.html")
    assert '<html lang="es"' in html
    assert f'<link rel="canonical" href="{SITE}/es/">' in html
    assert f'<meta property="og:url" content="{SITE}/es/">' in html
    assert _pair(html)
    assert "<title>España al Día: las noticias de España, cada mañana | Spanified</title>" in html


def test_en_home_has_pair_and_self_canonical(site):
    html = site("index.html")
    assert '<html lang="en"' in html
    assert f'<link rel="canonical" href="{SITE}/">' in html
    assert _pair(html)


def test_es_home_spanish_content_and_links(site):
    html = site("es/index.html")
    assert "Las noticias de España, cada mañana: España al Día" in html
    assert "Los alquileres siguen subiendo" in html and "17 de octubre de 2026" in html
    assert "Preguntas frecuentes" in html and build.ES_FAQ_ITEMS[0][0] in html
    hrefs = _hrefs(html)
    assert {"/es/", "/es/subscribe", "/es/archive/", "/es/archive/2026-10-17", "/es/articles/"} <= hrefs
    assert {"/es/category/housing", "/es/category/work"} <= {h for h in hrefs if h.startswith("/es/category/")}
    assert any(h.startswith("/es/articles/") and h != "/es/articles/" for h in hrefs)
    # English twins exist for all of these, so no English digest/article/category link remains.
    assert not any(h.startswith(("/archive", "/articles", "/category", "/subscribe")) for h in hrefs)
    # The Spanish header logo goes to the Spanish home.
    assert '<a href="/es/" class="brand"' in html


def test_es_home_json_ld(site):
    html = site("es/index.html")
    ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1))
    nodes = {n["@type"]: n for n in ld["@graph"]}
    assert nodes["WebSite"]["url"] == f"{SITE}/es/" and nodes["WebSite"]["inLanguage"] == "es"
    assert nodes["Periodical"]["name"] == "España al Día" and nodes["Periodical"]["inLanguage"] == "es"
    assert nodes["FAQPage"]["inLanguage"] == "es"
    assert nodes["FAQPage"]["mainEntity"][0]["name"] == build.ES_FAQ_ITEMS[0][0]


def test_es_home_subscribe_flow_uses_spanish_list(site):
    # The home page has no inline form (like the English one): its CTAs go to
    # /es/subscribe, whose form posts lang=es to the Spanish Listmonk list.
    home = site("es/index.html")
    assert "u-en" not in home
    sub = site("es/subscribe.html")
    assert 'value="u-es"' in sub and 'name="lang" value="es"' in sub and "u-en" not in sub


def test_sitemap_lists_es_home_with_alternates():
    links = build.sitemap_hreflang(SITE + "/es/")
    assert f'hreflang="es" href="{SITE}/es/"' in links and f'hreflang="en" href="{SITE}/"' in links
    assert build.sitemap_hreflang(SITE + "/") == links
