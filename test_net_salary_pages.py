import json
import os
import re
import xml.etree.ElementTree as ET

import jinja2
import pytest

import build


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("site")
    mp = pytest.MonkeyPatch()
    mp.setattr(build, "OUT_DIR", str(out))
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(build.TEMPLATES_DIR), autoescape=True)
    env.globals.update(site_url=build.SITE_URL, pub_date=build.pub_date, asset_version="1", js_importmap="{}",
                       turnstile_enabled=False, analytics_enabled=False, site_socials=[],
                       listmonk_form_action="/x", listmonk_list_uuid="u", current_year=2026)
    urls = build.render_net_salary_pages(env)
    build.render_calculators(env)
    build.render_sitemap([], (), (), urls)
    yield out, urls
    mp.undo()


def _pages():
    cfg = build.load_net_salary_pages()
    return ([build.net_salary_slug("annual", a) for a in cfg["annual"]]
            + [build.net_salary_slug("monthly", m) for m in cfg["monthly"]])


def _read(out, slug):
    return (out / "calculators" / f"{slug}.html").read_text(encoding="utf-8")


def test_file_per_amount(site):
    out, urls = site
    slugs = _pages()
    assert len(slugs) == len(urls) == 45
    for slug in slugs:
        assert (out / "calculators" / f"{slug}.html").is_file()


def test_seo_basics(site):
    out, _ = site
    titles = set()
    for slug in _pages():
        html = _read(out, slug)
        assert f'<link rel="canonical" href="{build.SITE_URL}/calculators/{slug}">' in html
        assert "noindex" not in html
        title = re.search(r"<title>(.*?)</title>", html).group(1)
        assert title not in titles
        titles.add(title)
        h1 = re.search(r"<h1>(.*?)</h1>", html).group(1)
        amount = re.search(r"net-salary-(\d+)-euros", slug).group(1)
        assert f"€{int(amount):,}" in h1
        blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
        assert len(blocks) == 2
        for b in blocks:
            json.loads(b)


def test_titles_and_descriptions(site):
    out, _ = site
    html = _read(out, "net-salary-30000-euros")
    assert "€30,000 Gross to Net in Spain (2026): €1,954/month" in html
    m = _read(out, "net-salary-2000-euros-per-month")
    assert "€2,000 Gross per Month to Net in Spain (2026)" in m
    assert "24,000" in m


def test_hub_links_all_pages(site):
    out, _ = site
    hub = (out / "calculators" / "net-salary.html").read_text(encoding="utf-8")
    for slug in _pages():
        assert f'href="/calculators/{slug}"' in hub
    page = _read(out, "net-salary-30000-euros")
    assert 'href="/calculators/net-salary-30000-euros"' not in page
    assert "Net salary for other common wages" in page and "Net salary by monthly wage" in page


def test_sitemap(site):
    out, urls = site
    root = ET.parse(out / "sitemap.xml").getroot()
    locs = {e.text for e in root.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")}
    for u in urls:
        assert build.SITE_URL + u in locs
