"""Spanish static pages: latest-edition preview on /es/subscribe and the
/es/about, /es/editor, /es/contact twins (hreflang, canonical, JSON-LD, links)."""
import json
import re

import jinja2
import pytest

import build

TWINS = ["about", "editor", "contact"]
LD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
SWITCH_RE = re.compile(r'<nav class="lang-switch".*?</nav>', re.S)


def _env():
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(build.TEMPLATES_DIR), autoescape=True)
    build.register_i18n(env)
    env.globals.update(current_year=2026, asset_version="t", js_version="t", js_importmap="{}",
                       site_url=build.SITE_URL, analytics_enabled=False, site_socials=[],
                       turnstile_enabled=False, listmonk_form_action="/x", listmonk_list_uuid="u",
                       listmonk_es_list_uuid="u-es")
    return env


PROOF = {"first_issue_es": "1 de enero de 2026", "total_issues_es": "1.234"}


@pytest.fixture(scope="module")
def latest_es():
    return build.digest_context(build.load_digests(build.ES_DATA_DIR)[0], "es")


def _subscribe(env, latest, template="es/subscribe.html", lang="es"):
    return env.get_template(template).render(
        page_lang=lang, proof=PROOF, faq=build.ES_SUBSCRIBE_FAQ_ITEMS, latest=latest,
        emoji=build.CATEGORY_EMOJI, default_emoji=build.DEFAULT_EMOJI)


def test_es_subscribe_previews_latest_spanish_edition(latest_es):
    html = _subscribe(_env(), latest_es)
    preview = html.split('<aside class="sub-preview"', 1)[1].split("</aside>", 1)[0]
    for story in latest_es["stories"][:3]:
        assert str(jinja2.utils.markupsafe.escape(story["title"])) in preview
    assert f'href="/es/archive/{latest_es["date"]}"' in preview
    assert latest_es["date_display"] in preview  # Spanish long date
    assert "La última edición" in preview and "Leer la edición completa" in preview
    if latest_es["story_count"] > 3:
        assert f'Y {latest_es["story_count"] - 3} noticias más.' in preview
    assert "Read this edition" not in preview and "more stories" not in preview


def test_es_subscribe_without_digests_has_no_preview():
    assert '<aside class="sub-preview"' not in _subscribe(_env(), None)


def test_english_subscribe_preview_unchanged():
    latest = build.digest_context(build.load_digests()[0])
    html = _subscribe(_env(), latest, template="partials/latest-edition-preview.html", lang="en")
    assert "The latest edition, as it arrived in readers" in html
    assert f'href="/archive/{latest["date"]}">Read this edition in full</a>' in html


def test_twins_registered():
    for name in TWINS:
        assert f"/{name}" in build.ES_PATHS
        assert build.localize("es", f"/{name}") == f"/es/{name}"
        assert f'hreflang="es" href="{build.SITE_URL}/es/{name}"' in build.sitemap_hreflang(
            f"{build.SITE_URL}/{name}")


@pytest.mark.parametrize("name", TWINS)
def test_twin_page_is_spanish(name):
    env = _env()
    es = env.get_template(f"es/{name}.html").render(page_lang="es")
    en = env.get_template(f"{name}.html").render()
    assert '<html lang="es"' in es
    assert f'<link rel="canonical" href="{build.SITE_URL}/es/{name}">' in es
    assert '<meta property="og:locale" content="es_ES">' in es
    for html in (es, en):
        assert f'hreflang="en" href="{build.SITE_URL}/{name}"' in html
        assert f'hreflang="es" href="{build.SITE_URL}/es/{name}"' in html
    body = SWITCH_RE.sub("", es.split("</head>", 1)[1])
    for path in ("/about", "/editor", "/contact", "/subscribe", "/privacy"):
        assert f'href="{path}"' not in body, f"es/{name} links English {path}"
    text = re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>", "", es, flags=re.S))
    assert "—" not in text  # no em dashes


@pytest.mark.parametrize("name, ld_type", [("about", "AboutPage"), ("editor", "ProfilePage"),
                                           ("contact", "ContactPage")])
def test_twin_json_ld(name, ld_type):
    html = _env().get_template(f"es/{name}.html").render(page_lang="es")
    blocks = [json.loads(b) for b in LD_RE.findall(html)]
    page = next(b for b in blocks if b["@type"] == ld_type)
    assert page["inLanguage"] == "es"
    assert page["url"] == f"{build.SITE_URL}/es/{name}"
    if name == "editor":
        assert page["mainEntity"]["@type"] == "Person"
        assert page["mainEntity"]["jobTitle"] == "Fundador y editor"


def test_shared_templates_link_spanish_twins():
    env = _env()
    footer = env.get_template("partials/es/footer.html").render()
    assert 'href="/es/about"' in footer and 'href="/es/contact"' in footer
    byline = env.from_string('{{ lang_url("/editor") }}').render(page_lang="es")
    assert byline == "/es/editor"
