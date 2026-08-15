"""Fetch latest merged pull request from GitHub (for /ping deploy visibility)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import httpx

from bot.config import settings
from bot.version import LAST_PR_NUMBER, LAST_PR_TITLE

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 600


@dataclass(frozen=True)
class MergedPullRequest:
    number: int
    title: str
    merged_at: str
    html_url: str


_cache: tuple[float, MergedPullRequest | None] | None = None


def _fetch_latest_merged_pr() -> MergedPullRequest | None:
    headers: dict[str, str] = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = settings.github_token.strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"https://api.github.com/repos/{settings.github_repo}/pulls"
    params = {"state": "closed", "sort": "updated", "direction": "desc", "per_page": 15}

    try:
        with httpx.Client(timeout=8.0) as client:
            response = client.get(url, params=params, headers=headers)
            response.raise_for_status()
            pulls = response.json()
    except Exception:
        logger.exception("Could not fetch latest merged PR from GitHub")
        return None

    for pull in pulls:
        if pull.get("merged_at"):
            return MergedPullRequest(
                number=int(pull["number"]),
                title=str(pull["title"]).strip(),
                merged_at=str(pull["merged_at"]),
                html_url=str(pull["html_url"]),
            )
    return None


def get_latest_merged_pr(*, force_refresh: bool = False) -> MergedPullRequest | None:
    """Return latest merged PR, cached for a few minutes."""
    global _cache
    now = time.monotonic()
    if not force_refresh and _cache is not None:
        cached_at, cached = _cache
        if now - cached_at < _CACHE_TTL_SECONDS:
            return cached

    latest = _fetch_latest_merged_pr()
    _cache = (now, latest)
    return latest


def format_latest_pr_line() -> str:
    """One-line PR summary for Telegram /ping."""
    latest = get_latest_merged_pr()
    if latest:
        return f"Última PR: #{latest.number} — {latest.title}"

    if LAST_PR_NUMBER and LAST_PR_TITLE:
        return f"Última PR: #{LAST_PR_NUMBER} — {LAST_PR_TITLE}"

    return "Última PR: (no disponible)"
