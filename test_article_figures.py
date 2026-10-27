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
