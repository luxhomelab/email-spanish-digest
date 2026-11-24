from build import dedupe_digest_titles, digest_context, digest_meta_description, digest_meta_title

ITEMS = [{"title": "Housing decrees face November 12 survival vote", "body": "x"}]


def test_title_leads_with_subject():
    ctx = digest_context({"date": "2026-11-09", "items": ITEMS,
                          "subject": "Housing vote, November 11 strike and sick pay"})
    assert ctx["meta_title"] == "Housing vote, November 11 strike and sick pay | Spain News in English"


def test_title_falls_back_to_top_story_with_date_without_subject():
    assert digest_meta_title("2026-11-09", ITEMS, None) == \
        "Housing decrees face November 12 survival vote | Spain News Nov 9"
    assert digest_meta_title("2026-11-09", ITEMS, "  ") == \
        "Housing decrees face November 12 survival vote | Spain News Nov 9"


def test_57_char_subject_is_kept_whole():
    subject = "November 11 strike, rail closure and heat pump incentives"
    assert digest_meta_title("2026-11-08", ITEMS, subject) == f"{subject} | Spain News in English"


def test_long_subject_is_cut_under_82_chars():
    subject = "November 11 strike, rail closure, heat pump incentives and a new pension calculation rule"
    title = digest_meta_title("2026-11-08", ITEMS, subject)
    assert len(title) <= 82
    assert title.endswith("… | Spain News in English")


def test_repeated_subject_gets_the_date():
    digests = [
        digest_context({"date": "2026-11-09", "items": ITEMS, "subject": "Housing vote"}),
        digest_context({"date": "2026-11-07", "items": ITEMS, "subject": "housing vote "}),
        digest_context({"date": "2026-11-06", "items": ITEMS, "subject": "Rents fall 19%"}),
        digest_context({"date": "2026-10-01", "items": ITEMS}),
    ]
    titles = [d["meta_title"] for d in dedupe_digest_titles(digests)]
    assert titles == [
        "Housing vote | Spain News in English, Nov 9",
        "housing vote | Spain News in English, Nov 7",
        "Rents fall 19% | Spain News in English",
        "Housing decrees face November 12 survival vote | Spain News Oct 1",
    ]


def test_description_skips_long_titles_and_counts_the_rest():
    items = [{"title": "Rents rise again"}, {"title": "x" * 150}, {"title": "Strike on Monday"},
             {"title": "Short one"}, {"title": "Another one"}]
    desc = digest_meta_description("2026-11-09", "", items)
    assert desc == ("Spain news, November 9, 2026: Rents rise again; Strike on Monday; Short one; "
                    "Another one")
    many = [{"title": f"Story number {n} about something long enough"} for n in range(6)]
    desc = digest_meta_description("2026-11-09", "", many)
    assert desc.endswith("; plus 4 more stories") and len(desc) <= 157


def test_es_title_can_skip_a_tagline_subject():
    raw = {"date": "2026-06-17", "items": ITEMS, "subject": "España hoy. Brevemente."}
    assert digest_context(raw, "es")["meta_title"].startswith("España hoy. Brevemente. |")
    ctx = digest_context(raw, "es", title_subject=False)
    assert ctx["meta_title"] == "Housing decrees face November 12 survival vote | Noticias de España, 17 jun"
    assert ctx["subject"] == "España hoy. Brevemente."  # still the on-page subheader
