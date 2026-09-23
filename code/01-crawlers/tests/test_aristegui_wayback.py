"""Tests for Aristegui-specific Wayback URL filtering."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


CRAWLER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CRAWLER_DIR))

from crawler_core.aristegui_wayback import default_sharded_patterns  # noqa: E402
from crawler_core.wayback import likely_wayback_article_url  # noqa: E402


class AristeguiWaybackTests(unittest.TestCase):
    def test_ddmm_article_path_is_kept(self) -> None:
        self.assertTrue(
            likely_wayback_article_url(
                "https://aristeguinoticias.com/0102/aristegui-en-vivo/example-article/",
                "aristeguinoticias",
            )
        )

    def test_non_article_paths_are_rejected(self) -> None:
        self.assertFalse(
            likely_wayback_article_url(
                "https://aristeguinoticias.com/category/mexico/",
                "aristeguinoticias",
            )
        )

    def test_default_patterns_cover_31_day_prefixes_for_three_hosts(self) -> None:
        patterns = default_sharded_patterns()
        self.assertEqual(len(patterns), 93)
        self.assertIn("aristeguinoticias.com/01*", patterns)
        self.assertIn("editorial.aristeguinoticias.com/31*", patterns)


if __name__ == "__main__":
    unittest.main()
