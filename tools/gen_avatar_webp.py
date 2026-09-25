"""Resize review avatars to WebP at 32/64/96 px for the testimonials block.

Source PNGs in static/img/avatars/ are 128x128 RGBA but are only ever
rendered at 32x32 (see .t-avatar in static/css/main.css). We emit
WebP variants at 1x/2x/3x and report byte sizes so callers can compare
them against the originals.

Run: <python> tools/gen_avatar_webp.py
"""

import os
from PIL import Image

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AVATAR_DIR = os.path.join(SCRIPT_DIR, "static", "img", "avatars")

SIZES = (32, 64, 96)
QUALITY = 82
METHOD = 6


def main():
    names = sorted(f for f in os.listdir(AVATAR_DIR) if f.endswith(".png"))
    if not names:
        raise SystemExit(f"no png avatars found in {AVATAR_DIR}")

    print(f"{'file':<28} {'size':>7} {'bytes':>8}")
    for name in names:
        src = os.path.join(AVATAR_DIR, name)
        base = name[:-4]
        orig_bytes = os.path.getsize(src)
        with Image.open(src) as im:
            im = im.convert("RGBA")
            for size in SIZES:
                out = os.path.join(AVATAR_DIR, f"{base}-{size}.webp")
                resized = im.resize((size, size), Image.LANCZOS)
                resized.save(
                    out,
                    "WEBP",
                    quality=QUALITY,
                    method=METHOD,
                    exact=False,
                )
                new_bytes = os.path.getsize(out)
                label = f"{base}-{size}.webp"
                print(f"{label:<28} {size:>4}px {new_bytes:>8}")
        print(f"{name:<28} {'src':>7} {orig_bytes:>8}")
        print("-" * 46)


if __name__ == "__main__":
    main()
