"""The 2026 election article: data validation and its data-driven graphics."""
import json

import pytest

import build

SLUG = "spain-election-2026-promises"


@pytest.fixture(autouse=True)
def fresh_cache(monkeypatch):
    monkeypatch.setattr(build, "_election_cache", None)


def test_data_loads_and_is_consistent():
    d = build.load_election_2026()
    assert sum(p["count"] for p in d["parties"]) == d["total_items"] == 865
    ids = [it["id"] for it in d["promises"]]
    assert len(ids) == len(set(ids))
    for it in d["promises"]:
        assert it["f"] in "ABCDV"
        # Pros and cons exist exactly for the feasible promises.
        assert bool(it.get("pos")) == (it["f"] in "AB")
        assert all(s["u"].startswith("https://") for s in it["s"])
    # Every party has promises in the explorer and three headline items.
    for p in d["parties"]:
        assert p["shown"] > 0 and len(p["headline_items"]) == 3
        assert abs(sum(pct for _, _, pct in p["shares"]) - 100) < 0.01


def test_adelante_is_the_twelfth_party_and_links_each_proposal():
    d = build.load_election_2026()
    assert len(d["parties"]) == 12
    adelante = next(p for p in d["parties"] if p["key"] == "adelante")
    assert adelante["count"] == 102 and adelante["feasible_pct"] == 40 and adelante["shown"] == 14
    assert adelante["programme_pdf"].endswith(".pdf")
    out = build.article_graphic_html(SLUG, "explorer")
    # The programme has no pages: each promise links to its own proposal page.
    assert 'href="https://programa.adelanteandalucia.org/propuesta/161/"' in out
    assert "Adelante Andalucía" in build.article_graphic_html(SLUG, "compare")


def test_bad_item_fails_the_build(tmp_path, monkeypatch):
    src = build.ELECTION_2026_DIR
    (tmp_path / "items").mkdir()
    meta = json.load(open(f"{src}/meta.json", encoding="utf-8"))
    (tmp_path / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    for p in meta["parties"]:
        items = json.load(open(f"{src}/items/{p['key']}.json", encoding="utf-8"))
        if p["key"] == "pp":
            items[0]["s"] = [{"t": "x", "u": "http://insecure.example"}]
        (tmp_path / "items" / f"{p['key']}.json").write_text(json.dumps(items), encoding="utf-8")
    monkeypatch.setattr(build, "ELECTION_2026_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="https"):
        build.load_election_2026()


def test_explorer_renders_every_promise_with_sources():
    d = build.load_election_2026()
    out = build.article_graphic_html(SLUG, "explorer")
    assert out.count('<details class="el-item"') == len(d["promises"])
    assert 'id="p-pp-1"' in out and 'data-f="A"' in out
    # Spanish terms in *italics* become <em>, text is escaped.
    assert "<em>Ley de Vivienda</em>" in out
    assert "{{" not in out and "{%" not in out


def test_other_articles_graphics_are_still_inlined_as_is(tmp_path, monkeypatch):
    (tmp_path / "other").mkdir()
    (tmp_path / "other" / "g.html").write_text("<p>{{ not jinja }}</p>\n", encoding="utf-8")
    monkeypatch.setattr(build, "ARTICLE_GRAPHICS_DIR", str(tmp_path))
    assert build.article_graphic_html("other", "g") == "<p>{{ not jinja }}</p>"


def test_article_is_listed_with_its_graphics():
    art = next(a for a in build.load_articles() if a["slug"] == SLUG)
    for cls in ("ag-el-scale", "ag-el-ladder", "el-parties", "el-explorer", "el-progs"):
        assert cls in art["body_html"]
    progs = art["body_html"].split('class="el-progs"')[1].split("</ul>")[0]
    for p in build.load_election_2026()["parties"]:
        assert f'href="{p["programme"]}"' in progs
    assert art["faq"] and art["date"] == "2026-11-23"


def test_compare_boards_place_every_promise_once():
    d = build.load_election_2026()
    out = build.article_graphic_html(SLUG, "compare")
    in_boards = sum(c["count"] for c in d["compare"])
    # Defence has a single promise, so it gets no comparison board.
    assert in_boards == len(d["promises"]) - 1
    assert out.count('class="el-chip"') == in_boards
    housing = next(c for c in d["compare"] if c["topic"]["key"] == "housing")
    assert housing["ratings"] == list("ABCDV")
    # Within a cell, chips follow the party order and all share the cell's rating.
    for row in housing["rows"]:
        for r, cell in row["cells"]:
            assert all(it["f"] == r for it in cell)


def test_compare_rejects_an_unplaced_promise(monkeypatch):
    meta = json.load(open(f"{build.ELECTION_2026_DIR}/meta.json", encoding="utf-8"))
    meta["approaches"]["energy"][0]["items"].remove("pp-82")
    real_load = json.load

    def fake_load(fh, *a, **k):
        data = real_load(fh, *a, **k)
        return meta if isinstance(data, dict) and "approaches" in data else data

    monkeypatch.setattr(build.json, "load", fake_load)
    with pytest.raises(ValueError, match="energy"):
        build.load_election_2026()
