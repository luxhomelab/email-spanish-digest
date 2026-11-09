"""YouTube embeds: "::: video <id>" in article markdown and data/videos.json."""
import json

import build


def test_article_video_directive_renders_facade_and_schema():
    html = build.article_markdown_to_html("Intro.\n\n::: video 891GhtG_AkU\n\n## Next")
    assert '<figure class="video-embed' in html
    assert 'data-video-id="891GhtG_AkU"' in html
    assert "maxresdefault.jpg" in html
    ld = json.loads(html.split('<script type="application/ld+json">')[1].split("</script>")[0])
    assert ld["@type"] == "VideoObject"
    assert ld["duration"] == "PT7M15S"
    assert html.index("<p>Intro.</p>") < html.index("video-embed") < html.index("<h2")


def test_unknown_video_renders_nothing():
    assert "video-embed" not in build.article_markdown_to_html("::: video AAAAAAAAAAA")


def test_every_video_has_schema_fields():
    for vid, v in build.load_videos().items():
        assert len(vid) == 11
        for key in ("title", "description", "upload_date", "duration"):
            assert v.get(key), (vid, key)


def test_chapters_render_rail_and_clip_schema():
    html = build.video_embed_html("_ZzFIR-Zl5A")
    assert 'class="video-embed has-chapters"' in html
    assert html.count('class="ve-chap"') == 15
    assert 'data-start="399"' in html and "&amp;t=399s" in html
    assert '<li class="ve-chap-key">' in html
    ld = json.loads(html.split('<script type="application/ld+json">')[1].split("</script>")[0])
    clips = ld["hasPart"]
    assert clips[0]["startOffset"] == 0 and clips[0]["endOffset"] == clips[1]["startOffset"]
    assert clips[-1]["endOffset"] == 673


def test_video_without_chapters_has_no_rail(monkeypatch):
    v = {k: val for k, val in build.load_videos()["891GhtG_AkU"].items() if k != "chapters"}
    monkeypatch.setattr(build, "_videos_cache", {"891GhtG_AkU": v})
    html = build.video_embed_html("891GhtG_AkU")
    assert 'class="video-embed"' in html
    assert "ve-chapters" not in html and "hasPart" not in html
