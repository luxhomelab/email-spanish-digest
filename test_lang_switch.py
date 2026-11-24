"""Header language switcher (partials/lang-switch.html): the other language
links to the page's twin when ES_PATHS has one, else to that language's home;
the current language is marked aria-current and is not a link."""
import re

import jinja2
import pytest

import build

EN_ONLY = "2026-10-15"  # English edition with no Spanish translation


def _raw(date):
    return {"date": date, "subject": "Rents", "items": [{"title": "Rents rise", "body": "Up.", "category": "housing"}]}


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(build, "ES_PATHS", set(build.ES_PATHS))
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(build.TEMPLATES_DIR), autoescape=True)
    build.register_i18n(env)
    env.globals.update(current_year=2026, asset_version="t", js_version="t", js_importmap="{}",
                       site_url=build.SITE_URL, analytics_enabled=False, site_socials=[], turnstile_enabled=False,
                       pub_date=build.pub_date, listmonk_form_action="/x", listmonk_list_uuid="u-en",
                       listmonk_es_list_uuid="u-es")
    return env


@pytest.fixture
def site(env, tmp_path, monkeypatch):
    """Digests 2026-10-17 (EN + ES twin) and EN_ONLY (English only)."""
    monkeypatch.setattr(build, "OUT_DIR", str(tmp_path))
    monkeypatch.setattr(build, "ARCHIVE_DIR", str(tmp_path / "archive"))
    en = [build.digest_context(_raw(d)) for d in ("2026-10-17", EN_ONLY)]
    es = [build.digest_context(_raw("2026-10-17"), "es")]
    build.register_es_paths(es, build.collect_categories(en))
    for digests, lang in ((en, "en"), (es, "es")):
        build.attach_digest_hubs(digests, (), lang=lang)
        build.attach_related(digests)
        build.attach_share(digests)
        build.render_digests(env, digests, lang=lang)
    return lambda rel: (tmp_path / rel).read_text(encoding="utf-8")


def _switch(html):
    """(nav aria-label, current language, {lang: href} of the links)."""
    nav = re.search(r'<nav class="lang-switch" aria-label="([^"]+)">(.*?)</nav>', html, re.S)
    assert nav, "no language switcher"
    current = re.findall(r'<span aria-current="true" lang="(\w+)">', nav.group(2))
    links = re.findall(r'<a href="([^"]+)" hreflang="(\w+)" lang="\2"', nav.group(2))
    return nav.group(1), current, {lang: href for href, lang in links}


def test_digest_with_twin_links_both_ways(site):
    assert _switch(site("archive/2026-10-17.html")) == ("Language", ["en"], {"es": "/es/archive/2026-10-17"})
    assert _switch(site("es/archive/2026-10-17.html")) == ("Idioma", ["es"], {"en": "/archive/2026-10-17"})


def test_english_only_pages_link_spanish_home(site, env):
    assert _switch(site(f"archive/{EN_ONLY}.html"))[2] == {"es": "/es/"}
    search = env.get_template("search.html").render(crumbs=[])
    assert _switch(search) == ("Language", ["en"], {"es": "/es/"})


def test_legal_pages_set_alt_path_for_header(env):
    """alt_path set at template top level reaches the header (and hreflang)."""
    assert _switch(env.get_template("privacy.html").render())[2] == {"es": "/es/privacy"}
    assert _switch(env.get_template("es/privacy.html").render())[2] == {"en": "/privacy"}
