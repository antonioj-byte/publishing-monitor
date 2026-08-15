"""Tests for GitHub latest-PR lookup used by /ping."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from bot import github_pr


class LatestPrTests(unittest.TestCase):
    def setUp(self) -> None:
        github_pr._cache = None

    def test_format_latest_pr_line_from_api(self) -> None:
        fake = github_pr.MergedPullRequest(
            number=44,
            title="Fix /reclasificar",
            merged_at="2026-08-15T04:39:37Z",
            html_url="https://github.com/example/pull/44",
        )
        with patch.object(github_pr, "get_latest_merged_pr", return_value=fake):
            line = github_pr.format_latest_pr_line()
        self.assertEqual(line, "Última PR: #44 — Fix /reclasificar")

    def test_format_latest_pr_line_fallback_to_version(self) -> None:
        with patch.object(github_pr, "get_latest_merged_pr", return_value=None):
            line = github_pr.format_latest_pr_line()
        self.assertIn("#44", line)
        self.assertIn("Fix /reclasificar", line)

    def test_fetch_picks_first_merged_pull(self) -> None:
        payload = [
            {"number": 99, "title": "Open never merged", "merged_at": None, "html_url": "u"},
            {
                "number": 44,
                "title": "Merged one",
                "merged_at": "2026-08-15T04:39:37Z",
                "html_url": "https://github.com/example/pull/44",
            },
        ]
        response = unittest.mock.Mock()
        response.raise_for_status = unittest.mock.Mock()
        response.json.return_value = payload
        client = unittest.mock.Mock()
        client.get.return_value = response
        client.__enter__ = unittest.mock.Mock(return_value=client)
        client.__exit__ = unittest.mock.Mock(return_value=False)

        with patch("bot.github_pr.httpx.Client", return_value=client):
            latest = github_pr._fetch_latest_merged_pr()

        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertEqual(latest.number, 44)
        self.assertEqual(latest.title, "Merged one")


if __name__ == "__main__":
    unittest.main()
