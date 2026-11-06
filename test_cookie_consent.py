"""Cookie consent: no vendor script that sets cookies may load before opt-in."""
import os

from jinja2 import Environment, FileSystemLoader

import build


def render_base(analytics):
    env = Environment(loader=FileSystemLoader(build.TEMPLATES_DIR), autoescape=True)
    env.globals.update(current_year=2026, asset_version="t", js_version="t",
                       js_importmap="{}", site_url=build.SITE_URL,
                       analytics_enabled=analytics, site_socials=[])
    return env.from_string('{% extends "base.html" %}').render()


def test_prod_base_loads_no_tracker_before_consent():
    html = render_base(True)
    assert "googletagmanager.com/gtag/js" not in html
    assert "fbevents.js" not in html
    assert "facebook.com/tr" not in html  # no-JS pixel would bypass consent
    assert "gtag('consent', 'default'" in html
    assert html.index("gtag('consent', 'default'") < html.index("gtag('config'")


def test_banner_and_settings_link_on_every_page():
    for analytics in (True, False):
        html = render_base(analytics)
        assert 'id="cookie-banner"' in html
        assert "/static/js/cookie-consent.js" in html
        assert "data-cookie-settings" in html
        assert 'data-cc="reject"' in html and 'data-cc="accept"' in html


def test_cookie_policy_page_is_built():
    assert "cookies.html" in build.STATIC_PAGES
    assert os.path.exists(os.path.join(build.TEMPLATES_DIR, "cookies.html"))
