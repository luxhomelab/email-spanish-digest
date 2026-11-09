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


from build import _amount_page_link, attach_digest_hubs, story_amount_pages

AMOUNTS = story_amount_pages(
    ns={"annual": [16000, 30000], "monthly": [1200, 1500]},
    au={"revenue": [20000], "monthly": [2000]},
    ry={"prices": [200000]},
)


def test_amount_page_picks_closest_page_with_context():
    link = _amount_page_link("The minimum wage (SMI) rises to €1,184 a month.", AMOUNTS["/calculators/net-salary"])
    assert link == {"url": "/calculators/net-salary-1200-euros-per-month",
                    "anchor": "take-home pay on €1,200 gross a month"}
    link = _amount_page_link("Average gross salary hits 29,500 euros.", AMOUNTS["/calculators/net-salary"])
    assert link["url"] == "/calculators/net-salary-30000-euros"


def test_amount_page_needs_context_range_and_tolerance():
    groups = AMOUNTS["/calculators/net-salary"]
    assert _amount_page_link("Homeowners can deduct up to €1,356 for home insurance.", groups) is None
    assert _amount_page_link("Wages: the state will spend €1,200 million.", groups) is None
    assert _amount_page_link("Salary of €45,000 for ministers.", groups) is None  # no page within 10%


def test_digest_hubs_skip_linked_pages_and_follow_categories():
    articles = [{"title": "Property guide", "url": "/articles/spain-property-guide", "reading_time": 20}]
    d = {"stories": [
        {"category": "property", "guide": None,
         "tool": {"url": "/calculators/net-salary-1200-euros-per-month", "base": "/calculators/property-buying-cost"}},
        {"category": "property", "guide": None, "tool": None},
        {"category": "work", "guide": None, "tool": None},
    ]}
    attach_digest_hubs([d], articles, limit=3)
    assert [c["url"] for c in d["hub_cards"]] == [
        "/articles/spain-property-guide", "/calculators/rental-yield", "/calculators/net-salary"]
    assert d["hub_cards"][0]["desc"] == "A 20-minute read"
