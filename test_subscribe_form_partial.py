import jinja2

import build


def _render(**params):
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(build.TEMPLATES_DIR), autoescape=True)
    env.globals.update(site_url=build.SITE_URL, turnstile_enabled=False,
                       listmonk_form_action="/x", listmonk_list_uuid="u")
    return env.get_template("partials/subscribe-form.html").render(**params)


def test_lang_defaults_to_english():
    assert '<input type="hidden" name="lang" value="en">' in _render()


def test_lang_can_be_overridden():
    assert '<input type="hidden" name="lang" value="ru">' in _render(lang="ru")
