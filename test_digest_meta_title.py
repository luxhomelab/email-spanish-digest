from build import digest_context, digest_meta_title

ITEMS = [{"title": "Housing decrees face November 12 survival vote", "body": "x"}]


def test_title_leads_with_subject():
    ctx = digest_context({"date": "2026-11-09", "items": ITEMS,
                          "subject": "Housing vote, November 11 strike and sick pay"})
    assert ctx["meta_title"] == "Housing vote, November 11 strike and sick pay | Spain News Nov 9"


def test_title_falls_back_to_top_story_without_subject():
    assert digest_meta_title("2026-11-09", ITEMS, None) == \
        "Housing decrees face November 12 survival vote | Spain News Nov 9"
    assert digest_meta_title("2026-11-09", ITEMS, "  ") == \
        "Housing decrees face November 12 survival vote | Spain News Nov 9"


def test_long_subject_is_cut_under_80_chars():
    subject = "November 11 strike, rail closure, heat pump incentives and a new pension calculation rule"
    title = digest_meta_title("2026-11-08", ITEMS, subject)
    assert len(title) <= 80
    assert title.endswith("… | Spain News Nov 8")
