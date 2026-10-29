import html as htmllib
import json
import re

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
    build.render_calculators(env)
    build.render_autonomo_pages(env)
    yield out
    mp.undo()


def _read(out, slug):
    return htmllib.unescape((out / "calculators" / f"{slug}.html").read_text(encoding="utf-8"))


def _faq_answers(page):
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S):
        data = json.loads(block)
        for node in data.get("@graph", [data]):
            if node.get("@type") == "FAQPage":
                return {q["name"]: q["acceptedAnswer"]["text"] for q in node["mainEntity"]}
    return {}


def test_calculator_ss_deduction_has_no_cap(site):
    page = _read(site, "autonomo-tax")
    assert "7% of revenue (no cap)" in page
    assert "7% of net revenues (no cap)" in _faq_answers(page)["What deductions can autónomos claim?"]
    assert "7% of revenue (max €2,000)" not in page
    assert "capped at €2,000/year) when determining their SS bracket" not in page


def test_calculator_tarifa_plana_mei_and_disclaimer(site):
    page = _read(site, "autonomo-tax")
    notice = re.search(r'<div class="notice notice-amber" id="r-tarifa" hidden>(.*?)</div>', page).group(1)
    assert "€88.65" in notice and "MEI" in notice
    assert "no 2026 rule has fixed a new amount" in notice
    assert "€88.65" in _faq_answers(page)["What is tarifa plana?"]


def test_calculator_ceuta_notice_states_assumption(site):
    page = _read(site, "autonomo-tax")
    notice = re.search(r'<div class="notice notice-amber" id="r-ceuta" hidden>(.*?)</div>', page).group(1)
    assert "art. 68.4 LIRPF" in notice
    assert "assumes your activity is carried on there" in notice


def test_calculator_explains_regional_minimos(site):
    page = _read(site, "autonomo-tax")
    assert "The regional half of IRPF uses your region's own mínimos" in page
    assert "€5,956.65" in page


def test_amount_pages_charge_mei_on_tarifa_plana(site):
    page = _read(site, "autonomo-tax-18000-euros")
    assert "first 12 months, €80 + MEI quota" in page
    tp = next(a for q, a in _faq_answers(page).items() if "tarifa plana" in a)
    assert "€80 tarifa plana plus the MEI levy" in tp
    # 88.65 × 12 = 1,063.80, shown rounded
    assert "€1,064 a year" in tp


def test_amount_page_ceuta_wording(site):
    answers = _faq_answers(_read(site, "autonomo-tax-32000-euros"))
    region = next(a for a in answers.values() if a.startswith("Ceuta and Melilla"))
    assert "on income earned there" in region


def test_amount_page_uses_regional_minimo_figures(site):
    # Madrid €32k with the Madrid regional mínimo: IRPF €4,453, net €22,420 (fact-check figures)
    page = _read(site, "autonomo-tax-32000-euros")
    assert "€22,420" in page
    assert "€4,453" in page
