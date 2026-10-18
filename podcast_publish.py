#!/usr/bin/env python3
"""Register a podcast episode for the RSS feed (podcast.xml).

Reads a pipeline episode dir (…/output/podcast/YYYY-MM-DD/) and writes
data/podcast/YYYY-MM-DD.json with what build.py needs for the feed: title,
duration, byte length, chapters. The MP3 itself never enters git; it lives
in Cloudflare R2 at MEDIA_URL/episodes/YYYY-MM-DD.mp3.

Usage:
  python3 podcast_publish.py <episode_dir> [--upload]

--upload runs `npx wrangler r2 object put` (needs `wrangler login`);
without it the command is only printed.
"""

import argparse
import json
import os
import re
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PODCAST_DATA_DIR = os.path.join(SCRIPT_DIR, "data", "podcast")
R2_BUCKET = "spanified-podcast"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def read_ffmetadata(path):
    """Top-level key=value pairs of an ffmetadata file (before any [CHAPTER])."""
    meta = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line.startswith("["):
                break
            if "=" in line and not line.startswith(";"):
                key, _, value = line.partition("=")
                meta[key] = value
    return meta


def probe_duration(mp3):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", mp3],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    return round(float(out))


def build_episode(episode_dir):
    date = os.path.basename(os.path.normpath(episode_dir))
    if not DATE_RE.match(date):
        sys.exit(f"episode dir must be named YYYY-MM-DD, got {date!r}")
    audio = os.path.join(episode_dir, "audio")
    mp3 = os.path.join(audio, "episode.mp3")
    meta = read_ffmetadata(os.path.join(audio, "ffmetadata.txt"))
    if not meta.get("title"):
        sys.exit("ffmetadata.txt has no title")
    with open(os.path.join(audio, "chapters.json"), encoding="utf-8") as fh:
        chapters = json.load(fh).get("chapters", [])
    episode = {
        "date": date,
        "title": f"{date}: {meta['title']}",
        "duration": probe_duration(mp3),
        "length": os.path.getsize(mp3),
        "chapters": chapters,
    }
    return episode, mp3


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("episode_dir")
    ap.add_argument("--upload", action="store_true")
    args = ap.parse_args()

    episode, mp3 = build_episode(args.episode_dir)
    os.makedirs(PODCAST_DATA_DIR, exist_ok=True)
    dest = os.path.join(PODCAST_DATA_DIR, f"{episode['date']}.json")
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump(episode, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print(f"wrote {os.path.relpath(dest, SCRIPT_DIR)}")

    cmd = ["npx", "wrangler", "r2", "object", "put",
           f"{R2_BUCKET}/episodes/{episode['date']}.mp3",
           "--file", mp3, "--content-type", "audio/mpeg", "--remote"]
    if args.upload:
        subprocess.run(cmd, check=True, shell=(os.name == "nt"))
    else:
        print("upload with:\n  " + " ".join(cmd))


if __name__ == "__main__":
    main()
