import jinja2

import build


def _render(**params):
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(build.TEMPLATES_DIR), autoescape=True)
    env.globals.update(site_url=build.SITE_URL, turnstile_enabled=False,
                       listmonk_form_action="/x", listmonk_list_uuid="u",
                       listmonk_es_list_uuid="u-es")
    return env.get_template("partials/subscribe-form.html").render(**params)


def test_lang_defaults_to_english():
    assert '<input type="hidden" name="lang" value="en">' in _render()


def test_lang_can_be_overridden():
    assert '<input type="hidden" name="lang" value="ru">' in _render(lang="ru")


def test_lang_falls_back_to_page_lang():
    html = _render(page_lang="es")
    assert '<input type="hidden" name="lang" value="es">' in html


def test_spanish_form_copy():
    html = _render(lang="es")
    assert "Acepto recibir España al Día" in html
    assert 'placeholder="tu@email.com"' in html
    assert "I agree" not in html and "Email address" not in html


def test_english_form_copy_unchanged():
    html = _render()
    assert "I agree to receive Spain Daily" in html
    assert "Acepto" not in html


def test_list_uuid_per_language():
    assert '<input type="hidden" name="l" value="u">' in _render()
    assert '<input type="hidden" name="l" value="u-es">' in _render(lang="es")
    assert '<input type="hidden" name="l" value="u-es">' in _render(page_lang="es")


def test_es_list_uuid_per_mode():
    import argparse
    ns = lambda **kw: argparse.Namespace(**{"es_list_uuid": None, "listmonk": "prod", **kw})
    assert build.listmonk_es_list_uuid(ns()) == "dc4801f8-3282-46e2-bbf9-488baff41312"
    assert build.listmonk_es_list_uuid(ns(listmonk="local")) == "cc400145-5ebe-4a7c-98e1-b0a336250224"
    assert build.listmonk_es_list_uuid(ns(es_list_uuid="x")) == "x"
