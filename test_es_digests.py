"""Spanish digest, archive and category pages (/es/archive/..., /es/category/...):
lang, Spanish copy, hreflang pairs, self canonicals and links to /es/ twins."""
import jinja2
import pytest

import build

SITE = build.SITE_URL
EN_ONLY = "2026-10-15"  # English edition with no Spanish translation


def _raw(date, lang):
    story = {"en": ("Rents keep rising", "Rents rose again."),
             "es": ("Los alquileres siguen subiendo", "Los alquileres volvieron a subir.")}[lang]
    return {"date": date, "subject": {"en": "Rents and jobs", "es": "Alquileres y empleo"}[lang],
            "items": [{"title": story[0], "body": story[1], "category": "housing",
                       "sources": [{"name": "El País", "url": "https://elpais.com/x"}]},
                      {"title": story[0] + " 2", "body": story[1], "category": "work", "important": True}]}


@pytest.fixture
def site(tmp_path, monkeypatch):
    """Build EN + ES digests, archive and categories into tmp_path; return a reader."""
    monkeypatch.setattr(build, "OUT_DIR", str(tmp_path))
    monkeypatch.setattr(build, "ARCHIVE_DIR", str(tmp_path / "archive"))
    monkeypatch.setattr(build, "ES_PATHS", set(build.ES_PATHS))
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(build.TEMPLATES_DIR), autoescape=True)
    build.register_i18n(env)
    env.globals.update(current_year=2026, asset_version="t", js_version="t", js_importmap="{}", site_url=SITE,
                       analytics_enabled=False, site_socials=[], turnstile_enabled=False, pub_date=build.pub_date,
                       listmonk_form_action="/x", listmonk_list_uuid="u-en", listmonk_es_list_uuid="u-es")
    en = [build.digest_context(_raw(d, "en")) for d in ("2026-10-17", "2026-10-16", EN_ONLY)]
    es = [build.digest_context(_raw(d, "es"), "es") for d in ("2026-10-17", "2026-10-16")]
    build.register_es_paths(es, build.collect_categories(en))
    for digests, lang in ((en, "en"), (es, "es")):
        build.attach_digest_hubs(digests, (), lang=lang)
        build.attach_related(digests)
        build.attach_share(digests)
        build.render_digests(env, digests, lang=lang)
        build.render_archive(env, digests, lang=lang)
        build.render_categories(env, digests, lang=lang)
    return lambda rel: (tmp_path / rel).read_text(encoding="utf-8")


def _pair(html, path):
    return (f'hreflang="en" href="{SITE}{path}"' in html
            and f'hreflang="es" href="{SITE}/es{path}"' in html
            and f'hreflang="x-default" href="{SITE}{path}"' in html)


def test_es_digest_page(site):
    html = site("es/archive/2026-10-17.html")
    assert '<html lang="es"' in html
    assert f'<link rel="canonical" href="{SITE}/es/archive/2026-10-17">' in html
    assert _pair(html, "/archive/2026-10-17")
    assert "<title>Alquileres y empleo | Noticias de España</title>" in html
    assert "España al Día:" in html and "17 de octubre de 2026" in html
    assert "◆ IMPORTANTE" in html and "Compartir:" in html and "Vivienda" in html
    assert '"inLanguage": "es"' in html
    # Internal links go to the Spanish twins.
    assert 'href="/es/category/housing"' in html and 'href="/category/housing"' not in html
    assert 'href="/es/archive/"' in html  # breadcrumb
    assert 'href="/es/archive/2026-10-16"' in html  # day nav + related
    assert 'href="/es/privacy"' in html and 'href="/privacy"' not in html
    assert 'class="site-nav"' not in html  # Spanish header, no English nav
    assert "Rechazar" in html and "Reject" not in html  # Spanish cookie banner
    # Spanish subscribe form: Spanish list, lang=es, Spanish confirm page.
    assert '<input type="hidden" name="lang" value="es">' in html
    assert '<input type="hidden" name="l" value="u-es">' in html
    assert f'name="next" value="{SITE}/es/confirm"' in html
    assert "Suscribirme gratis" in html


def test_en_digest_hreflang_only_with_twin(site):
    assert _pair(site("archive/2026-10-17.html"), "/archive/2026-10-17")
    en_only = site(f"archive/{EN_ONLY}.html")
    assert 'rel="alternate" hreflang=' not in en_only
    assert f"/es/archive/{EN_ONLY}" not in site("es/archive/index.html")
    with pytest.raises(FileNotFoundError):
        site(f"es/archive/{EN_ONLY}.html")


def test_english_pages_stay_english(site):
    html = site("archive/2026-10-17.html")
    assert '<html lang="en"' in html and "Spain Daily Digest:" in html
    assert 'href="/category/housing"' in html and "/es/category/" not in html.split('hreflang="x-default"')[1]


def test_es_archive(site):
    html = site("es/archive/index.html")
    assert '<html lang="es"' in html
    assert f'<link rel="canonical" href="{SITE}/es/archive/">' in html
    assert _pair(html, "/archive/")
    assert "<h1>Archivo</h1>" in html and "2 noticias" in html and "Última" in html
    assert 'href="/es/archive/2026-10-17"' in html
    assert _pair(site("archive/index.html"), "/archive/")


def test_es_category(site):
    html = site("es/category/housing.html")
    assert '<html lang="es"' in html
    assert f'<link rel="canonical" href="{SITE}/es/category/housing">' in html
    assert _pair(html, "/category/housing")
    assert build.CATEGORY_META_ES["housing"][0] in html
    assert "<h1>Vivienda</h1>" in html
    assert 'href="/es/archive/2026-10-17"' in html and 'href="/archive/2026-10-17"' not in html
    assert 'href="/es/subscribe"' in html
    assert "Calculadora de rentabilidad del alquiler" in html  # hub card, Spanish copy
    assert _pair(site("category/housing.html"), "/category/housing")


def test_sitemap_hreflang_for_registered_twins(monkeypatch):
    monkeypatch.setattr(build, "ES_PATHS", set(build.ES_PATHS) | {"/archive/2026-10-17", "/category/work"})
    for path in ("/archive/2026-10-17", "/es/archive/2026-10-17", "/es/category/work"):
        base = path.removeprefix("/es")
        assert f'hreflang="es" href="{SITE}/es{base}"' in build.sitemap_hreflang(SITE + path)
    assert build.sitemap_hreflang(SITE + "/archive/2026-10-15") == ""


def test_tr_and_localize(monkeypatch):
    monkeypatch.setattr(build, "ES_PATHS", {"/archive/"})
    assert build.tr("en", "{n} news", n=3) == "3 news"
    assert build.tr("es", "{n} news", n=3) == "3 noticias"
    assert build.localize("es", "/archive/") == "/es/archive/"
    assert build.localize("es", "/editor") == "/editor"  # no Spanish twin yet
    assert build.localize("en", "/archive/") == "/archive/"


def test_es_meta_title_and_dates():
    assert build.digest_meta_title("2026-09-10", [{"title": "Sube el SMI"}], lang="es") == \
        "Sube el SMI | Noticias de España, 10 sept"
    assert build.digest_meta_description("2026-09-10", "", [{"title": "Sube el SMI"}], lang="es") == \
        "Noticias de España, 10 de septiembre de 2026: Sube el SMI"
