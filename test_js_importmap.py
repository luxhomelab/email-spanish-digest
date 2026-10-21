import hashlib
import json
import os
import re

import build


def test_importmap_versions_every_js_module():
    imports = json.loads(build.js_importmap())["imports"]
    js_dir = os.path.join(build.SCRIPT_DIR, "static", "js")
    names = [n for n in os.listdir(js_dir) if n.endswith(".js")]
    assert "autonomo-calc.js" in names
    for name in names:
        with open(os.path.join(js_dir, name), "rb") as fh:
            digest = hashlib.md5(fh.read()).hexdigest()[:8]
        assert imports[f"/static/js/{name}"] == f"/static/js/{name}?v={digest}"


def test_importmap_comes_before_any_module_script():
    # Nested `import './x.js'` carries no ?v=, so without the map a browser can keep
    # a stale module after a deploy. The map must precede every module script.
    with open(os.path.join(build.SCRIPT_DIR, "templates", "base.html"), encoding="utf-8") as fh:
        base = fh.read()
    head = base[: base.index("</head>")]
    assert 'type="importmap"' in head
    first_module = re.search(r'type="module"', base)
    assert first_module is None or base.index('type="importmap"') < first_module.start()
