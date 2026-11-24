"""Spanish quizzes (/es/quiz/<slug>): the data/quizzes/es overlays, and the
pages a full build writes from them."""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

import build

ROOT = Path(__file__).parent
SITE = "https://spanified.com"
SLUGS = ("ai-or-real", "spanish-law-or-myth")


def es_overlay(slug):
    return json.loads((ROOT / "data" / "quizzes" / "es" / f"{slug}.json").read_text(encoding="utf-8"))


def overlay_strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from overlay_strings(v)


@pytest.mark.parametrize("slug", SLUGS)
def test_overlay_matches_english_and_has_no_em_dashes(slug):
    en = next(q for q in build.load_quizzes() if q["slug"] == slug)
    es = next(q for q in build.load_quizzes("es") if q["slug"] == slug)
    # Structure, answers, sources and score bands stay the English ones.
    for qe, qs in zip(en["questions"], es["questions"]):
        assert {k: qe.get(k) for k in ("id", "isReal", "source", "source_url")} == \
               {k: qs.get(k) for k in ("id", "isReal", "source", "source_url")}
        assert qs["headline"] != qe["headline"]
    assert [(r["slug"], r["min"], r["max"]) for r in en["results"]] == \
           [(r["slug"], r["min"], r["max"]) for r in es["results"]]
    assert es["title"] != en["title"] and es["meta_description"]
    for text in overlay_strings(es_overlay(slug)):
        assert "—" not in text, text


def test_overlay_out_of_sync_fails_the_build():
    en = next(q for q in build.load_quizzes() if q["slug"] == "ai-or-real")
    es = es_overlay("ai-or-real")
    del es["questions"]["r1"]
    with pytest.raises(ValueError, match="r1"):
        build._quiz_es_overlay(en, es)


@pytest.fixture(scope="module")
def dist(tmp_path_factory):
    out = tmp_path_factory.mktemp("dist")
    subprocess.run([sys.executable, str(ROOT / "build.py"), "--out", str(out)], cwd=ROOT, check=True,
                   capture_output=True)
    return out


def read(dist, rel):
    return (dist / rel).read_text(encoding="utf-8")


def quiz_data(html):
    return json.loads(re.search(r'<script id="quiz-data" type="application/json">(.*?)</script>', html, re.S).group(1))


@pytest.mark.parametrize("slug", SLUGS)
def test_es_quiz_page(dist, slug):
    html = read(dist, f"es/quiz/{slug}.html")
    es = es_overlay(slug)
    assert '<html lang="es"' in html
    assert f'<link rel="canonical" href="{SITE}/es/quiz/{slug}">' in html
    assert f'<link rel="alternate" hreflang="es" href="{SITE}/es/quiz/{slug}">' in html
    assert f'<link rel="alternate" hreflang="en" href="{SITE}/quiz/{slug}">' in html
    assert f'<title>{es["title"]} | Spanified</title>' in html
    assert '"inLanguage": "es"' in html
    data = quiz_data(html)
    assert data["title"] == es["title"] and data["real_label"] == es["real_label"]
    assert data["questions"][0]["headline"] == es["questions"][data["questions"][0]["id"]]["headline"]
    # Subscribe gate: Spanish list, lang=es, Spanish confirm page.
    assert 'name="lang" value="es"' in html
    assert f'name="next" value="{SITE}/es/quiz/{slug}-subscribed"' in html
    assert "Empezar el test" in html and "Start the quiz" not in html
    # The English twin points back.
    en_html = read(dist, f"quiz/{slug}.html")
    assert f'<link rel="alternate" hreflang="es" href="{SITE}/es/quiz/{slug}">' in en_html


def test_es_quiz_form_posts_to_spanish_list(dist):
    es_uuid = re.search(r'name="l" value="([^"]+)"', read(dist, "es/subscribe.html")).group(1)
    en_uuid = re.search(r'name="l" value="([^"]+)"', read(dist, "quiz/ai-or-real.html")).group(1)
    assert es_uuid != en_uuid
    assert f'name="l" value="{es_uuid}"' in read(dist, "es/quiz/ai-or-real.html")


@pytest.mark.parametrize("slug", SLUGS)
def test_es_flow_pages_are_spanish_noindex_and_link_es(dist, slug):
    es = es_overlay(slug)
    pages = [f"es/quiz/{slug}-subscribed.html", f"es/quiz/{slug}-success.html"] + [
        f"es/quiz/{slug}-result-{r}.html" for r in es["results"]]
    for rel in pages:
        html = read(dist, rel)
        assert '<html lang="es"' in html, rel
        assert 'content="noindex, nofollow"' in html, rel
        assert f'href="/es/quiz/{slug}"' in html, rel
        # No alt_path on flow pages, so the switcher links "/" and no English quiz URL appears.
        assert 'href="/quiz/' not in html, rel
    persona, res = next(iter(es["results"].items()))
    html = read(dist, f"es/quiz/{slug}-result-{persona}.html")
    assert f"<h1>{res['title']}</h1>" in html
    assert f'<link rel="canonical" href="{SITE}/es/quiz/{slug}-result-{persona}">' in html


def test_sitemap_lists_es_quizzes_with_alternates(dist):
    xml = read(dist, "sitemap.xml")
    for slug in SLUGS:
        block = re.search(rf"<url><loc>{SITE}/es/quiz/{slug}</loc>(.*?)</url>", xml).group(1)
        assert f'hreflang="en" href="{SITE}/quiz/{slug}"' in block
    assert "/es/quiz/ai-or-real-result" not in xml


def test_es_home_quiz_cards_link_spanish_quizzes(dist):
    html = read(dist, "es/index.html")
    for slug in SLUGS:
        title = es_overlay(slug)["title"]
        assert f'<a href="/es/quiz/{slug}" aria-label="Hacer el test: {title}">' in html
        assert f'alt="Portada del test {title}"' in html
    assert 'href="/quiz/' not in html.split('class="hm-quizzes"', 1)[1].split("</ul>", 1)[0]
