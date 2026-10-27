from build import attach_guides


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


def test_first_article_wins_and_whole_words_only():
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
