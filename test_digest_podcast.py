import os

import jinja2

import build

EP = {"date": "2026-10-17", "title": "T & co", "duration": 532, "length": 1,
      "chapters": [{"startTime": 0.0, "title": "Cold open"}, {"startTime": 75.5, "title": "Story"}]}


def test_podcast_context():
    ctx = build.digest_podcast_context(EP)
    assert ctx["audio_url"] == "https://media.spanified.com/episodes/2026-10-17.mp3"
    assert ctx["minutes"] == 9
    assert ctx["iso_duration"] == "PT8M52S"
    assert ctx["chapters"][1] == {"start": 75.5, "title": "Story", "label": "1:15"}
    assert build.digest_podcast_context(None) is None


def _render(tmp_path, monkeypatch, episodes):
    monkeypatch.setattr(build, "ARCHIVE_DIR", str(tmp_path))
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(os.path.join(build.SCRIPT_DIR, "templates")))
    env.globals.update(site_url="https://spanified.com", pub_date=build.pub_date, asset_version="1",
                       turnstile_enabled=False, analytics_enabled=False, site_socials=[])
    digest = build.digest_context({"date": "2026-10-17", "headline": "H", "items": []})
    digest["share"] = {}
    build.render_digests(env, [digest], episodes)
    return (tmp_path / "2026-10-17.html").read_text(encoding="utf-8")


def test_digest_page_has_player(tmp_path, monkeypatch):
    html = _render(tmp_path, monkeypatch, {"2026-10-17": EP})
    assert 'class="podcast-player"' in html
    assert "episodes/2026-10-17.mp3" in html
    assert "podcast-player.js" in html
    assert '"@type": "AudioObject"' in html


def test_digest_page_without_episode(tmp_path, monkeypatch):
    html = _render(tmp_path, monkeypatch, {})
    assert "podcast-player" not in html
