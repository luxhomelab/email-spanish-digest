"""Spanish article pages (/es/articles/<slug>, /es/articles/): lang, hreflang
pairs, self canonicals, Spanish JSON-LD, localized links and Spanish graphics."""
import glob
import json
import os
import re

import jinja2
import pytest

import build

SITE = build.SITE_URL


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    """Render the real English and Spanish articles into a temp dir; return a reader."""
    out = tmp_path_factory.mktemp("site")
    mp = pytest.MonkeyPatch()
    mp.setattr(build, "OUT_DIR", str(out))
    mp.setattr(build, "ARTICLES_DIR", str(out / "articles"))
    mp.setattr(build, "ES_PATHS", set(build.ES_PATHS))
    mp.setattr(build, "_election_cache", None)
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(build.TEMPLATES_DIR), autoescape=True)
    build.register_i18n(env)
    env.globals.update(current_year=2026, asset_version="t", js_version="t", js_importmap="{}", site_url=SITE,
                       analytics_enabled=False, site_socials=[], turnstile_enabled=False, pub_date=build.pub_date,
                       listmonk_form_action="/x", listmonk_list_uuid="u-en", listmonk_es_list_uuid="u-es",
                       video_embed=build.video_embed)
    en = build.load_articles()
    es = build.load_articles("es")
    build.register_es_paths([], None, es, en)
    for articles, lang in ((en, "en"), (es, "es")):
        build.render_articles_list(env, articles, lang=lang)
        build.render_article_pages(env, articles, lang=lang)
    yield lambda rel: (out / rel).read_text(encoding="utf-8")
    mp.undo()


def _pair(html, path):
    return (f'hreflang="en" href="{SITE}{path}"' in html
            and f'hreflang="es" href="{SITE}/es{path}"' in html
            and f'hreflang="x-default" href="{SITE}{path}"' in html)


def _ld(html, kind):
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        data = json.loads(block)
        if data.get("@type") == kind:
            return data
    raise AssertionError(f"no {kind} JSON-LD")


def test_every_spanish_article_has_an_english_twin():
    en = {a["slug"] for a in build.load_articles()}
    es = {a["slug"] for a in build.load_articles("es")}
    assert es and es <= en


def test_es_article_page(site):
    html = site("es/articles/how-spain-votes.html")
    assert '<html lang="es"' in html
    assert f'<link rel="canonical" href="{SITE}/es/articles/how-spain-votes">' in html
    assert _pair(html, "/articles/how-spain-votes")
    assert '<meta property="og:locale" content="es_ES">' in html
    # Spanish OG card (og/es/), not the English page's card.
    assert f'{SITE}/og/es/article-how-spain-votes.png' in html
    assert f'{SITE}/og/article-how-spain-votes.png' not in html
    toc = site("es/articles/spain-property-guide.html")
    assert "En esta guía" in toc and "In this guide" not in toc
    assert '<a href="#faq">Preguntas frecuentes</a>' in toc
    for text in ("Preguntas frecuentes", "min de lectura", ">Por <",
                 "Calculadoras y guías relacionadas", "¿Te ha resultado útil? Compártelo con alguien."):
        assert text in html, text
    for english in ("In this guide", "Frequently asked questions", "min read", "Related calculators and guides"):
        assert english not in html, english


def test_english_article_gets_the_pair_and_stays_english(site):
    html = site("articles/how-spain-votes.html")
    assert '<html lang="en"' in html
    assert f'<link rel="canonical" href="{SITE}/articles/how-spain-votes">' in html
    assert _pair(html, "/articles/how-spain-votes")
    assert "Frequently asked questions" in html and "min read" in html
    assert "In this guide" in site("articles/spain-property-guide.html")
    assert '"inLanguage": "en"' in html and "/es/articles/" not in html.split("</header>", 1)[1]  # body after the header (its ES link is the twin)


def test_es_json_ld_is_spanish(site):
    html = site("es/articles/how-spain-votes.html")
    art = _ld(html, "Article")
    assert art["inLanguage"] == "es"
    assert art["mainEntityOfPage"] == f"{SITE}/es/articles/how-spain-votes"
    assert art["headline"].startswith("Cómo se vota en España")
    assert "Política" in art["articleSection"]
    faq = _ld(html, "FAQPage")
    assert faq["inLanguage"] == "es"
    assert faq["mainEntity"][0]["name"].startswith("¿")
    crumbs = [(i["name"], i["item"]) for i in _ld(html, "BreadcrumbList")["itemListElement"]]
    assert crumbs[0][0] == "Inicio"
    assert crumbs[1] == ("Artículos", f"{SITE}/es/articles/")
    assert crumbs[2][1] == f"{SITE}/es/articles/how-spain-votes"


def test_es_links_point_to_spanish_twins(site):
    html = site("es/articles/spain-property-guide.html")
    body = html.split('class="email-body article-body"', 1)[1]
    hrefs = re.findall(r'href="(/[^"]*)"', body)
    # Every internal article link (body, FAQ, related cards) goes to /es/, anchors included.
    assert not [h for h in hrefs if h.startswith("/articles/")]
    assert "/es/articles/autonomo-taxes-spain#pagar-durante-el-ano-retenciones-y-modelo-130" in hrefs
    # Pages without a Spanish twin keep their English path.
    assert "/calculators/property-buying-cost" in hrefs
    cards = re.search(r'<section class="hub-cards".*?</section>', html, re.S).group(0)
    assert 'href="/es/articles/switching-electricity-provider-spain"' in cards
    assert "Cómo cambiar de compañía de luz" in cards


def test_es_anchors_exist(site):
    for slug in ("spain-property-guide", "autonomo-taxes-spain", "switching-electricity-provider-spain"):
        html = site(f"es/articles/{slug}.html")
        for href in re.findall(r'href="(/es/articles/[^"#]+)#([^"]+)"', html):
            target = site(f"es/articles/{href[0].rsplit('/', 1)[1]}.html")
            assert f'id="{href[1]}"' in target, href
        for frag in re.findall(r'href="#([^"{]+)"', html):
            assert f'id="{frag}"' in html, (slug, frag)


def test_es_graphics_are_spanish(site):
    votes = site("es/articles/how-spain-votes.html")
    assert "Papeleta blanca" in votes and "White ballot" not in votes
    assert "100.000 votos válidos" in votes
    tax = site("es/articles/autonomo-taxes-spain.html")
    assert "Te quedas con 22.794 € (71 %)" in tax and "You keep" not in tax
    election = site("es/articles/spain-election-2026-promises.html")
    assert "Mostrando las 127 promesas" in election
    assert 'data-some="Mostrando {shown} de {total} promesas"' in election
    assert "Derogar la Ley de Vivienda de 2023" in election
    assert "Our assessment" not in election and "Nuestra valoración." in election


def test_every_graphic_has_a_spanish_copy_with_the_same_markup():
    def tags(s):
        s = re.sub(r"\{#.*?#\}", "", s, flags=re.S)
        return [re.sub(r'\s(?:title|aria-label|alt|placeholder|href|data-[a-z-]+)="[^"]*"', "", t)
                for t in re.findall(r"<[^>]+>", s)]
    for en_path in glob.glob(os.path.join(build.ARTICLE_GRAPHICS_DIR, "*", "*.html")):
        es_path = os.path.join(os.path.dirname(en_path), "es", os.path.basename(en_path))
        assert os.path.isfile(es_path), es_path
        with open(en_path, encoding="utf-8") as a, open(es_path, encoding="utf-8") as b:
            assert tags(a.read()) == tags(b.read()), es_path


def test_spanish_election_data_matches_english(monkeypatch):
    monkeypatch.setattr(build, "_election_cache", None)
    en, es = build.load_election_2026(), build.load_election_2026("es")
    assert [(p["id"], p["f"], p["t"], p["n"], [s["u"] for s in p["s"]]) for p in en["promises"]] == \
           [(p["id"], p["f"], p["t"], p["n"], [s["u"] for s in p["s"]]) for p in es["promises"]]
    assert all(a["title"] != b["title"] for a, b in zip(en["promises"], es["promises"]))
    assert es["election_display"] == "29 de noviembre de 2026"


def test_es_articles_list(site):
    html = site("es/articles/index.html")
    assert '<html lang="es"' in html
    assert f'<link rel="canonical" href="{SITE}/es/articles/">' in html
    assert _pair(html, "/articles/")
    assert "<title>Guías prácticas para vivir en España | Spanified</title>" in html
    assert 'href="/es/articles/how-spain-votes"' in html and "min de lectura" in html
    assert '"inLanguage": "es"' in html
    assert _pair(site("articles/index.html"), "/articles/")


def test_sitemap_alternates_for_articles(monkeypatch):
    monkeypatch.setattr(build, "ES_PATHS", {"/articles/how-spain-votes"})
    for url in (f"{SITE}/articles/how-spain-votes", f"{SITE}/es/articles/how-spain-votes"):
        links = build.sitemap_hreflang(url)
        assert f'hreflang="es" href="{SITE}/es/articles/how-spain-votes"' in links
        assert f'hreflang="x-default" href="{SITE}/articles/how-spain-votes"' in links
