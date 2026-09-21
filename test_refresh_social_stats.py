#!/usr/bin/env python3
"""Tests for refresh_social_stats.py — social proof auto-update.

- Threads followers: fetched from the official Insights API.
- Reddit subscribers: fetched on a best-effort basis; when the fetch fails
  (e.g. Reddit blocks datacenter IPs with 403), the last known value is kept
  and a warning is emitted — the site never shows a stale invented number.
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
    def test_reddit_fallback_keeps_last_value(self):
        old = {"reddit_members": 955, "threads_followers": 4100}
        merged = rss.merge_stats(old, reddit=None, threads=4194)
        self.assertEqual(merged["reddit_members"], 955)  # kept, no fake number
        self.assertEqual(merged["threads_followers"], 4194)

    def test_reddit_new_value_wins(self):
        old = {"reddit_members": 955, "threads_followers": 4100}
        merged = rss.merge_stats(old, reddit=1005, threads=4194)
        self.assertEqual(merged["reddit_members"], 1005)

    def test_threads_fallback_keeps_last_value(self):
        old = {"reddit_members": 955, "threads_followers": 4100}
        merged = rss.merge_stats(old, reddit=1005, threads=None)
        self.assertEqual(merged["threads_followers"], 4100)

    def test_rounds_down_reddit(self):
        # "1k+" display semantics: show floor to nearest 5 (like before)
        old = {"reddit_members": 955, "threads_followers": 0}
        self.assertEqual(rss.merge_stats(old, reddit=1002, threads=0)["reddit_members"], 1000)


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