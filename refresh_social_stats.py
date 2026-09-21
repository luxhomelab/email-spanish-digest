#!/usr/bin/env python3
"""
Spain News EN — Social Proof Refresh

Refreshes data/social_stats.json in the site repo before each digest deploy,
so spanified.com always shows fresh follower/subscriber counts.

Sources:
- Threads: official Insights API (metric=followers_count) — works with the
  existing THREADS_EN_* credentials.
- Reddit: best-effort via the public about.json (several mirrors). Reddit
  often blocks datacenter IPs (403) — on failure the last known value is kept
  and a warning printed; we never invent a number.

Usage:
    python3 refresh_social_stats.py --site /path/to/email-spanish-digest

Environment:
    THREADS_EN_USER_ID / THREADS_EN_ACCESS_TOKEN  (Threads insights)
"""

import argparse
import json
import os
import sys
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

REDDIT_SOURCES = [
    "https://www.reddit.com/r/{sub}/about.json",
    "https://old.reddit.com/r/{sub}/about.json",
    "https://api.reddit.com/r/{sub}/about.json",
]
REDDIT_SUB = os.environ.get("REDDIT_SUB", "SpainDaily")

UA = "Mozilla/5.0 (compatible; SpainDaily-stats/1.0)"


def load_stats(path):
    """Load stats JSON; safe defaults when missing/corrupt."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {"reddit_members": 0, "threads_followers": 0}


def round_down_5(raw):
    """Round down to nearest 5 (honest '1,000+' style display)."""
    return (int(raw) // 5) * 5


def merge_stats(old, reddit=None, threads=None):
    """Merge fetched values into old stats; None keeps the previous value.
    Reddit is rounded down to nearest 5; Threads stays exact."""
    out = dict(old)
    if reddit is not None:
        out["reddit_members"] = round_down_5(reddit)
    if threads is not None:
        out["threads_followers"] = int(threads)
    return out


def _get(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def fetch_threads_followers():
    """Official Threads Insights followers_count. Returns int or None."""
    uid = os.environ.get("THREADS_EN_USER_ID", "")
    token = os.environ.get("THREADS_EN_ACCESS_TOKEN", "")
    if not uid or not token:
        print("fetch_threads: no THREADS_EN_USER_ID/TOKEN", file=sys.stderr)
        return None
    url = (
        f"https://graph.threads.net/v1.0/{uid}/threads_insights"
        f"?metric=followers_count&period=day&access_token={token}"
    )
    try:
        payload = json.loads(_get(url, timeout=15))
        return parse_threads_insights(payload)
    except Exception as e:
        print(f"fetch_threads: failed: {e}", file=sys.stderr)
        return None


def parse_threads_insights(payload):
    """Extract followers_count.value from Insights response; None if absent."""
    for row in payload.get("data", []):
        if row.get("name") == "followers_count":
            tv = row.get("total_value") or {}
            if "value" in tv:
                return int(tv["value"])
    return None


def fetch_reddit_members():
    """Best-effort subreddit subscriber count; int or None on total failure."""
    for template in REDDIT_SOURCES:
        url = template.format(sub=REDDIT_SUB)
        try:
            payload = json.loads(_get(url))
            subs = payload.get("data", {}).get("subscribers")
            if subs is not None:
                return int(subs)
        except Exception as e:
            print(f"fetch_reddit: {url} failed: {e}", file=sys.stderr)
    print(f"fetch_reddit: all sources failed — keeping last known value",
          file=sys.stderr)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", required=True,
                    help="path to the email-spanish-digest repo checkout")
    args = ap.parse_args()

    target = os.path.join(args.site, "data", "social_stats.json")
    old = load_stats(target)
    threads = fetch_threads_followers()
    reddit = fetch_reddit_members()

    merged = merge_stats(old, reddit=reddit, threads=threads)
    changed = merged != old
    if changed:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as fh:
            json.dump(merged, fh, indent=2)
            fh.write("\n")
    print(f"social_stats: reddit={merged['reddit_members']} "
          f"threads={merged['threads_followers']}"
          f" ({'updated' if changed else 'unchanged'})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())