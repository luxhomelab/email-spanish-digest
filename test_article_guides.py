from build import attach_guides, attach_tools


def _digest(*stories):
    return {"stories": [dict(s) for s in stories]}


ARTICLES = [
    {"title": "Governed", "url": "/articles/governed", "story_keywords": ["investiture", "Constitutional Court"]},
    {"title": "Votes", "url": "/articles/votes", "story_keywords": ["general election", "d'Hondt"]},
    {"title": "No keywords", "url": "/articles/other", "story_keywords": []},
]


def test_matches_title_or_body_case_insensitive():
    d = _digest({"title": "Sánchez calls General Election", "body": ""},
                {"title": "Senate pact", "body": "It could reshape the constitutional court."})
    attach_guides([d], ARTICLES)
    assert d["stories"][0]["guide"] == {"title": "Votes", "url": "/articles/votes"}
    assert d["stories"][1]["guide"] == {"title": "Governed", "url": "/articles/governed"}


def test_tie_goes_to_first_article_and_whole_words_only():
    d = _digest({"title": "Investiture after the general election", "body": ""},
                {"title": "Reinvestiture talk", "body": "Pensions rise"})
    attach_guides([d], ARTICLES)
    assert d["stories"][0]["guide"]["url"] == "/articles/governed"
    assert d["stories"][1]["guide"] is None


def test_story_categories_filter():
    articles = [{"title": "Votes", "url": "/articles/votes", "story_keywords": ["general election"],
                 "story_categories": ["politics"]}]
    d = _digest({"title": "Strike before the general election", "body": "", "category": "work"},
                {"title": "Snap general election", "body": "", "category": "Politics"})
    attach_guides([d], articles)
    assert d["stories"][0]["guide"] is None
    assert d["stories"][1]["guide"]["url"] == "/articles/votes"


def test_most_keyword_hits_wins():
    d = _digest({"title": "Investiture vote", "body": "After the general election, d'Hondt maths decide."})
    attach_guides([d], ARTICLES)
    assert d["stories"][0]["guide"]["url"] == "/articles/votes"


TOOLS = [
    {"url": "/calculators/a", "keywords": ["autónomo"], "anchors": ["A1", "A2"]},
    {"url": "/calculators/s", "keywords": ["salary", "wages"], "categories": ["work"], "anchors": ["S1"]},
]


def test_tools_match_once_per_digest_and_respect_categories():
    d = _digest({"title": "Wages rise", "body": "", "category": "work"},
                {"title": "Salary deal", "body": "", "category": "work"},
                {"title": "Salary row", "body": "", "category": "politics"},
                {"title": "Autónomo quota", "body": "", "category": "work"})
    d["date"] = "2026-11-06"
    attach_tools([d], TOOLS)
    tools = [s["tool"] for s in d["stories"]]
    assert tools[0] == {"url": "/calculators/s", "anchor": "S1"}
    assert tools[1] is None and tools[2] is None
    assert tools[3]["url"] == "/calculators/a" and tools[3]["anchor"] in ("A1", "A2")


def test_tools_per_digest_cap_and_fallback_to_next_match():
    d = _digest({"title": "Autónomo salary", "body": "", "category": "work"},
                {"title": "Autónomo again, salary too", "body": "", "category": "work"},
                {"title": "Wages", "body": "", "category": "work"})
    attach_tools([d], TOOLS, per_digest=2)
    assert d["stories"][0]["tool"]["url"] == "/calculators/a"
    assert d["stories"][1]["tool"]["url"] == "/calculators/s"
    assert d["stories"][2]["tool"] is None
