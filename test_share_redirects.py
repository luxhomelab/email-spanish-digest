"""Short share links from the Spain Daily email (/wa, /mail).

Readers forward these to friends, so they must be short, redirect to
/subscribe with the share UTM tags, and carry their own OG tags: WhatsApp
builds the link preview from this page and does not follow the redirect.
"""
import os
import re
import unittest

import build

ROOT = os.path.dirname(os.path.abspath(__file__))
TARGET = ("https://spanified.com/subscribe?utm_source=newsletter"
          "&utm_medium=email&utm_campaign=share&utm_content={}")
PAGES = {"wa.html": "whatsapp", "mail.html": "email"}
NOINDEX_PAGES = ["t.html", "yt.html", *PAGES]


class ShareRedirectTests(unittest.TestCase):
    def read(self, name):
        with open(os.path.join(ROOT, name), encoding="utf-8") as f:
            return f.read()

    def test_copied_by_build(self):
        for name in PAGES:
            self.assertIn(name, build.STATIC_COPY)

    def test_redirects_to_subscribe_with_utm(self):
        for name, content in PAGES.items():
            html = self.read(name)
            target = TARGET.format(content)
            self.assertIn(f'content="0; url={target}"', html, name)
            self.assertIn(f'window.location.replace("{target}")', html, name)
            self.assertIn(f'<a href="{target}"', html, name)

    def test_not_indexed(self):
        for name in NOINDEX_PAGES:
            self.assertIn('name="robots" content="noindex, nofollow"', self.read(name))

    def test_link_preview_tags(self):
        for name in PAGES:
            html = self.read(name)
            for prop in ("og:title", "og:description", "og:image", "og:url"):
                self.assertRegex(html, rf'property="{prop}" content="[^"]+"', f"{name} {prop}")
            self.assertIn("https://spanified.com/og/og-subscribe.png", html)
            self.assertIn('name="twitter:card" content="summary_large_image"', html)


if __name__ == "__main__":
    unittest.main()
