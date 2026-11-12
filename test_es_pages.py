"""Minimal Spanish subscribe flow (/es/*): Spanish layout, lang=es form, links."""
import jinja2
import pytest

import build


def _env():
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(build.TEMPLATES_DIR), autoescape=True)
    env.globals.update(current_year=2026, asset_version="t", js_version="t", js_importmap="{}",
                       site_url=build.SITE_URL, analytics_enabled=False, site_socials=[],
                       turnstile_enabled=False, listmonk_form_action="/x", listmonk_list_uuid="u",
                       listmonk_es_list_uuid="u-es")
    return env


PROOF = {"first_issue_es": "1 de enero de 2026", "total_issues_es": "1.234"}


@pytest.mark.parametrize("name", build.ES_PAGES)
def test_es_page_is_spanish(name):
    html = _env().get_template(f"es/{name}").render(proof=PROOF, faq=build.ES_SUBSCRIBE_FAQ_ITEMS)
    assert '<html lang="es"' in html
    assert "Rechazar" in html  # Spanish cookie banner
    assert "Reject" not in html
    assert 'class="site-nav"' not in html  # stripped header, no English nav


def test_es_subscribe_form_and_hreflang():
    html = _env().get_template("es/subscribe.html").render(proof=PROOF, faq=build.ES_SUBSCRIBE_FAQ_ITEMS)
    assert '<input type="hidden" name="lang" value="es">' in html
    assert '<input type="hidden" name="l" value="u-es">' in html
    assert f'name="next" value="{build.SITE_URL}/es/confirm"' in html
    assert f'<link rel="canonical" href="{build.SITE_URL}/es/subscribe">' in html
    assert 'hreflang="en"' in html and 'hreflang="es"' in html
    assert "1.234 ediciones" in html


def test_english_pages_stay_english():
    html = _env().from_string('{% extends "base.html" %}').render()
    assert '<html lang="en"' in html
    assert "Reject" in html and "Rechazar" not in html


def test_format_date_es():
    assert build.format_date_es("2026-09-10") == "10 de septiembre de 2026"


@pytest.mark.parametrize("path", ["/privacy", "/terms", "/cookies"])
def test_legal_pages_have_hreflang_pair(path):
    env = _env()
    es = env.get_template(f"es{path}.html").render()
    en = env.get_template(f"{path[1:]}.html").render()
    for html in (es, en):
        assert f'hreflang="en" href="{build.SITE_URL}{path}"' in html
        assert f'hreflang="es" href="{build.SITE_URL}/es{path}"' in html
    assert f'<link rel="canonical" href="{build.SITE_URL}/es{path}">' in es


def test_spanish_form_links_spanish_legal_pages():
    html = _env().get_template("es/subscribe.html").render(proof=PROOF, faq=build.ES_SUBSCRIBE_FAQ_ITEMS)
    assert 'href="/es/privacy"' in html and 'href="/es/terms"' in html
    assert 'href="/privacy"' not in html and 'href="/terms"' not in html


@pytest.mark.parametrize("name", build.ES_PAGES)
def test_es_pages_link_spanish_legal_pages(name):
    html = _env().get_template(f"es/{name}").render(proof=PROOF, faq=build.ES_SUBSCRIBE_FAQ_ITEMS)
    for path in ("/privacy", "/terms", "/cookies"):
        assert f'href="{path}' not in html, f"{name} links English {path}"


def test_sitemap_hreflang_pairs():
    for path in ("/subscribe", "/es/subscribe", "/cookies", "/es/cookies"):
        links = build.sitemap_hreflang(build.SITE_URL + path)
        base = path.removeprefix("/es")
        assert f'hreflang="en" href="{build.SITE_URL}{base}"' in links
        assert f'hreflang="es" href="{build.SITE_URL}/es{base}"' in links
        assert f'hreflang="x-default" href="{build.SITE_URL}{base}"' in links
    assert build.sitemap_hreflang(build.SITE_URL + "/about") == ""
    assert build.sitemap_hreflang(build.SITE_URL + "/es/confirm") == ""


def test_es_subscribe_uses_spanish_og_image():
    import os
    html = _env().get_template("es/subscribe.html").render(proof=PROOF, faq=build.ES_SUBSCRIBE_FAQ_ITEMS)
    assert 'content="https://spanified.com/static/img/social/subscribe-es.jpg"' in html
    assert "social/subscribe.jpg" not in html
    assert os.path.isfile(os.path.join(build.SCRIPT_DIR, "static", "img", "social", "subscribe-es.jpg"))
