import json
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
    urls = build.render_rental_yield_pages(env)
    build.render_calculators(env)
    build.render_sitemap([], (), (), (), (), urls)
    yield out, urls
    mp.undo()


def _slugs():
    return [build.rental_yield_slug(p) for p in build.load_rental_yield_pages()["prices"]]


def _read(out, slug):
    return (out / "calculators" / f"{slug}.html").read_text(encoding="utf-8")


def test_file_per_price(site):
    out, urls = site
    slugs = _slugs()
    assert len(slugs) == len(urls) == 13
    for slug in slugs:
        assert (out / "calculators" / f"{slug}.html").is_file()


def test_seo_basics(site):
    out, _ = site
    titles = set()
    for slug in _slugs():
        html = _read(out, slug)
        assert f'<link rel="canonical" href="{build.SITE_URL}/calculators/{slug}">' in html
        assert "noindex" not in html
        title = re.search(r"<title>(.*?)</title>", html).group(1)
        assert title not in titles
        titles.add(title)
        h1 = re.search(r"<h1>(.*?)</h1>", html).group(1)
        price = int(re.search(r"rental-yield-(\d+)-euros", slug).group(1))
        assert f"€{price:,}" in h1
        blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
        assert len(blocks) == 2
        for b in blocks:
            json.loads(b)


def test_figures_come_from_the_calculator(site):
    out, _ = site
    html = _read(out, "rental-yield-250000-euros-property")
    # 250k at 5.5% gross -> €1,145/month; calculator defaults: Madrid ITP 6% = €15,000, closing 2% = €5,000
    assert "€1,145" in html
    assert "€15,000" in html and "€5,000" in html
    assert "Rent needed on a €250,000 property" in html
    assert 'href="/calculators/rental-yield?ry_pp=250000&amp;ry_rent=1145' in html


def test_hub_links_all_pages(site):
    out, _ = site
    hub = (out / "calculators" / "rental-yield.html").read_text(encoding="utf-8")
    for slug in _slugs():
        assert f'href="/calculators/{slug}"' in hub
    page = _read(out, "rental-yield-200000-euros-property")
    assert 'href="/calculators/rental-yield-200000-euros-property"' not in page
    assert "Rental yield by purchase price" in page


def test_sitemap(site):
    out, urls = site
    root = ET.parse(out / "sitemap.xml").getroot()
    locs = {e.text for e in root.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")}
    for u in urls:
        assert build.SITE_URL + u in locs
