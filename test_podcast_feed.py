import xml.etree.ElementTree as ET

import build

EP = {"date": "2026-10-17", "title": "T & co", "duration": 532, "length": 8508445,
      "chapters": [{"startTime": 0.0, "title": "Cold open"}]}


def test_feed(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "OUT_DIR", str(tmp_path))
    build.render_podcast_feed([EP], {"2026-10-17"})
    item = ET.parse(tmp_path / "podcast.xml").find("channel/item")
    assert item.findtext("title") == "#1 T & co | Spain Daily News | 17 Oct 2026"
    assert item.findtext("guid") == "spanified-podcast-2026-10-17"
    assert item.findtext("pubDate") == "Sat, 17 Oct 2026 08:00:00 +0200"
    enc = item.find("enclosure")
    assert enc.get("length") == "8508445"
    assert enc.get("url") == "https://media.spanified.com/episodes/2026-10-17.mp3"
    assert (tmp_path / "podcast" / "chapters" / "2026-10-17.json").exists()


def test_episode_notes_summary_first():
    ep = dict(EP, summary="Two stories today.")
    notes = build.podcast_episode_notes(ep)
    assert notes.startswith("Two stories today.\n\n00:00:00 Cold open")


def test_episode_notes_without_summary():
    assert build.podcast_episode_notes(EP).startswith("00:00:00 Cold open")


def test_feed_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "OUT_DIR", str(tmp_path))
    build.render_podcast_feed([dict(EP, summary="Two & more.")])
    ns = {"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd"}
    item = ET.parse(tmp_path / "podcast.xml").find("channel/item")
    assert item.findtext("description").startswith("Two & more.\n\n00:00:00")
    assert item.findtext("itunes:summary", namespaces=ns).startswith("Two & more.")


def test_show_summary_audience_not_expats():
    assert "expat" not in build.PODCAST_SUMMARY.lower()
    assert "English speakers in Spain" in build.PODCAST_SUMMARY


def test_title_strips_date_and_numbers_by_date(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "OUT_DIR", str(tmp_path))
    old = dict(EP, date="2026-10-16", title="2026-10-16: Old story")
    build.render_podcast_feed([EP, old])
    titles = [i.findtext("title") for i in ET.parse(tmp_path / "podcast.xml").findall("channel/item")]
    assert titles == ["#2 T & co | Spain Daily News | 17 Oct 2026",
                      "#1 Old story | Spain Daily News | 16 Oct 2026"]
