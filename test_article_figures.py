from build import article_markdown_to_html


def test_figure_with_caption():
    out = article_markdown_to_html('![A chart](/static/img/a.webp "The **caption**")')
    assert out.startswith('<figure class="art-figure"><a href="/static/img/a.webp"')
    assert 'alt="A chart"' in out
    assert '<figcaption>The <strong>caption</strong></figcaption>' in out


def test_figure_without_caption_closes_list():
    out = article_markdown_to_html('- item\n![x](/a.webp)')
    assert out.splitlines() == [
        '<ul>', '<li>item</li>', '</ul>',
        '<figure class="art-figure"><a href="/a.webp" target="_blank" rel="noopener">'
        '<img src="/a.webp" alt="x" width="1600" height="900" loading="lazy" decoding="async"></a></figure>',
    ]


def test_inline_image_syntax_mid_paragraph_is_not_a_figure():
    out = article_markdown_to_html('See ![x](/a.webp) here')
    assert '<figure' not in out


def test_term_list_item_wraps_description():
    out = article_markdown_to_html('- **Term:** text (*Spanish*) more')
    assert '<li><strong>Term:</strong><span>text (<em>Spanish</em>) more</span></li>' in out


def test_graphic_directive_inlines_partial(tmp_path, monkeypatch):
    import build
    (tmp_path / "my-article").mkdir()
    (tmp_path / "my-article" / "seats.html").write_text('<figure class="ag">X</figure>\n', encoding="utf-8")
    monkeypatch.setattr(build, "ARTICLE_GRAPHICS_DIR", str(tmp_path))
    out = article_markdown_to_html("- item\n::: graphic seats\nAfter", slug="my-article")
    assert out.splitlines() == ['<ul>', '<li>item</li>', '</ul>', '<figure class="ag">X</figure>', '<p>After</p>']


def test_graphic_directive_missing_partial_renders_nothing(tmp_path, monkeypatch):
    import build
    monkeypatch.setattr(build, "ARTICLE_GRAPHICS_DIR", str(tmp_path))
    assert article_markdown_to_html("::: graphic nope", slug="my-article") == ""


def test_h2_gets_unique_ids():
    out = article_markdown_to_html("## How *it* works\n## How it works")
    assert '<h2 id="how-it-works">How <em>it</em> works</h2>' in out
    assert '<h2 id="how-it-works-2">How it works</h2>' in out


def test_toc_directive_lists_all_h2_and_extras():
    out = article_markdown_to_html(
        "Intro\n::: toc\n## One\n## Two\n## Three", toc_extra=[("faq", "FAQ")]
    )
    assert out.startswith('<p>Intro</p>\n<nav class="art-toc"')
    assert 'style="--rows: 2"' in out
    assert '<li><a href="#one">One</a></li>\n<li><a href="#two">Two</a></li>' in out
    assert '<li><a href="#faq">FAQ</a></li>' in out


def test_no_toc_without_directive():
    assert "art-toc" not in article_markdown_to_html("## One")


def test_graphic_directive_mid_paragraph_is_text():
    out = article_markdown_to_html("See ::: graphic seats here", slug="x")
    assert out == "<p>See ::: graphic seats here</p>"
