#!/usr/bin/env python3
"""Tests for refresh_social_stats.py — social proof auto-update.

- Threads followers: fetched from the official Insights API.
- Reddit subscribers: STATIC since 2026-09-22 (owner decision) — the
  datacenter IP is 403-blocked on every Reddit endpoint, so live fetch was
  removed; the value is maintained manually in data/social_stats.json.
"""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import refresh_social_stats as rss  # noqa: E402


class LoadStatsTests(unittest.TestCase):
    def test_missing_file_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "social_stats.json")
            stats = rss.load_stats(path)
            self.assertEqual(stats["reddit_members"], 0)
            self.assertEqual(stats["threads_followers"], 0)

    def test_existing_file_loaded(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "social_stats.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"reddit_members": 955, "threads_followers": 4100}, f)
            stats = rss.load_stats(path)
            self.assertEqual(stats["reddit_members"], 955)
            self.assertEqual(stats["threads_followers"], 4100)


class MergeStatsTests(unittest.TestCase):
    def test_reddit_omitted_keeps_stored_value(self):
        old = {"reddit_members": 1100, "threads_followers": 4212}
        merged = rss.merge_stats(old, reddit=None, threads=4220)
        self.assertEqual(merged["reddit_members"], 1100)  # static, kept as-is
        self.assertEqual(merged["threads_followers"], 4220)

    def test_reddit_explicit_value_updates(self):
        # Manual maintenance path: operator edits the JSON directly; merge
        # still honours an explicit value (rounded down to nearest 5).
        old = {"reddit_members": 1000, "threads_followers": 4212}
        merged = rss.merge_stats(old, reddit=1105, threads=4212)
        self.assertEqual(merged["reddit_members"], 1105)

    def test_threads_fallback_keeps_last_value(self):
        old = {"reddit_members": 1100, "threads_followers": 4212}
        merged = rss.merge_stats(old, reddit=None, threads=None)
        self.assertEqual(merged["threads_followers"], 4212)

    def test_rounds_down_reddit(self):
        # "1k+" display semantics: show floor to nearest 5 (like before)
        old = {"reddit_members": 955, "threads_followers": 0}
        self.assertEqual(rss.merge_stats(old, reddit=1002, threads=0)["reddit_members"], 1000)


class RedditFetchRemovedTests(unittest.TestCase):
    def test_reddit_fetch_is_removed(self):
        # 2026-09-22: no point polling Reddit from a 403-blocked datacenter IP.
        self.assertFalse(hasattr(rss, "fetch_reddit_members"),
                         "fetch_reddit_members should have been removed")
        self.assertFalse(hasattr(rss, "REDDIT_SOURCES"),
                         "REDDIT_SOURCES should have been removed")


class ParseThreadsTests(unittest.TestCase):
    def test_parses_insights_response(self):
        payload = {
            "data": [{
                "name": "followers_count",
                "total_value": {"value": 4194},
            }]
        }
        self.assertEqual(rss.parse_threads_insights(payload), 4194)

    def test_missing_metric_returns_none(self):
        payload = {"data": [{"name": "likes", "total_value": {"value": 3}}]}
        self.assertIsNone(rss.parse_threads_insights(payload))

    def test_empty_data_returns_none(self):
        self.assertIsNone(rss.parse_threads_insights({"data": []}))


class RoundDownTests(unittest.TestCase):
    def test_round_down_to_nearest_5(self):
        for raw, expected in [(1000, 1000), (1001, 1000), (1004, 1000),
                              (1005, 1005), (1014, 1010), (4194, 4190)]:
            self.assertEqual(rss.round_down_5(raw), expected, f"raw={raw}")


if __name__ == "__main__":
    unittest.main()