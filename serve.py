#!/usr/bin/env python3
"""Local dev server with production-like clean URLs (no .html).

Serves the repo root (built static site):
  /quiz/ai-or-real        -> quiz/ai-or-real.html
  /quiz/ai-or-real/       -> quiz/ai-or-real.html (or dir index if it exists)
  /                       -> index.html (default handler behavior)

Usage: py serve.py [port]   (default 8000)
Dev-only helper, not part of the build.
"""

import http.server
import os
import sys
import urllib.parse

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000


class CleanUrlsHandler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        parsed = urllib.parse.urlparse(path).path
        full = super().translate_path(parsed)
        if os.path.isdir(full) and parsed != "/" and not parsed.endswith("/"):
            index = os.path.join(full, "index.html")
            if not os.path.isfile(index):
                sibling = full + ".html"
                if os.path.isfile(sibling):
                    return sibling
        if not os.path.isdir(full) and not os.path.isfile(full):
            if os.path.isfile(full + ".html"):
                return full + ".html"
        return full


if __name__ == "__main__":
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), CleanUrlsHandler)
    print(f"Serving {os.getcwd()} at http://localhost:{PORT} (clean URLs, no .html needed)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
