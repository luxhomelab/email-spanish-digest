"""Local preview server with clean-URL fallback (mimics production hosting).

Serves extensionless URLs like /calculators/electricity-bill by falling
back to <path>.html, and directory paths to <dir>/index.html.
Local-only helper, not part of the site build.

Usage: py serve_local.py [port]  (default 8000)
"""
import os
import sys
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))


class CleanURLHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        # Strip query/fragment, resolve against ROOT.
        parsed = urllib.parse.urlparse(path)
        rel = urllib.parse.unquote(parsed.path.lstrip("/"))
        abs_path = os.path.normpath(os.path.join(ROOT, rel))
        if not abs_path.startswith(ROOT):
            return abs_path
        # Exact file or directory -> default behaviour.
        if os.path.isfile(abs_path) or os.path.isdir(abs_path):
            return super().translate_path(path)
        # Extensionless page -> try <path>.html (production clean URLs).
        if not os.path.splitext(abs_path)[1]:
            candidate = abs_path + ".html"
            if os.path.isfile(candidate):
                return candidate
        return super().translate_path(path)

    def log_message(self, *args):
        sys.stderr.write(
            "%s - %s\n" % (self.address_string(), " ".join(str(a) for a in args))
        )


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    os.chdir(ROOT)
    with ThreadingHTTPServer(("127.0.0.1", port), CleanURLHandler) as httpd:
        print(f"Serving {ROOT} at http://localhost:{port} (clean URLs enabled)")
        httpd.serve_forever()
